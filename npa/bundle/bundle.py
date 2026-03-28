"""Bundle format and loading for NPA.

Compatible with OPA bundle format:
- .tar.gz archive containing Rego files and data.json
- Optional bundle signing (JWT-based)
- Revision tracking
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any


@dataclass(frozen=True)
class BundleFile:
    """A single file within a bundle."""
    path: str
    content: bytes

    @property
    def is_rego(self) -> bool:
        return self.path.endswith(".rego")

    @property
    def is_data(self) -> bool:
        name = PurePosixPath(self.path).name
        return name in ("data.json", "data.yaml", "data.yml")

    @property
    def is_wasm(self) -> bool:
        return self.path.endswith(".wasm")


@dataclass
class BundleManifest:
    """Bundle manifest (/.manifest)."""
    revision: str = ""
    roots: list[str] = field(default_factory=lambda: [""])
    metadata: dict[str, Any] = field(default_factory=dict)
    # Delta bundle support
    delta: bool = False

    def to_dict(self) -> dict:
        d = {
            "revision": self.revision,
            "roots": self.roots,
            "metadata": self.metadata,
        }
        if self.delta:
            d["delta"] = True
        return d

    @staticmethod
    def from_dict(d: dict) -> BundleManifest:
        return BundleManifest(
            revision=d.get("revision", ""),
            roots=d.get("roots", [""]),
            metadata=d.get("metadata", {}),
            delta=d.get("delta", False),
        )


@dataclass
class Bundle:
    """A policy bundle containing Rego modules and data."""
    files: list[BundleFile] = field(default_factory=list)
    manifest: BundleManifest = field(default_factory=BundleManifest)
    signature: str | None = None

    @property
    def rego_files(self) -> list[BundleFile]:
        return [f for f in self.files if f.is_rego]

    @property
    def data_files(self) -> list[BundleFile]:
        return [f for f in self.files if f.is_data]

    def content_hash(self) -> str:
        """SHA-256 hash of all file contents for integrity verification."""
        h = hashlib.sha256()
        for f in sorted(self.files, key=lambda x: x.path):
            h.update(f.path.encode())
            h.update(f.content)
        return h.hexdigest()

    def get_policies(self) -> dict[str, str]:
        """Extract all Rego policies as {path: source}."""
        return {f.path: f.content.decode("utf-8") for f in self.rego_files}

    def get_data(self) -> dict[str, Any]:
        """Merge all data files into a single data document."""
        merged: dict[str, Any] = {}
        for f in self.data_files:
            path = PurePosixPath(f.path)
            content = json.loads(f.content)
            # Place data at its directory path
            parts = [p for p in path.parent.parts if p not in (".", "/")]
            current = merged
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
            if isinstance(content, dict):
                current.update(content)
            else:
                current[path.stem] = content
        return merged


def load_bundle_from_bytes(data: bytes) -> Bundle:
    """Load a bundle from a .tar.gz byte stream."""
    files: list[BundleFile] = []
    manifest = BundleManifest()
    signature: str | None = None

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue

            # Security: prevent path traversal
            name = member.name.lstrip("./")
            if ".." in name:
                continue

            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            content = extracted.read()

            if name == ".manifest":
                manifest = BundleManifest.from_dict(json.loads(content))
            elif name == ".signatures.json":
                sig_data = json.loads(content)
                if isinstance(sig_data, dict) and "signatures" in sig_data:
                    signature = sig_data["signatures"][0] if sig_data["signatures"] else None
            else:
                files.append(BundleFile(path=name, content=content))

    return Bundle(files=files, manifest=manifest, signature=signature)


def load_bundle_from_dir(directory: str | Path) -> Bundle:
    """Load a bundle from a directory on disk."""
    root = Path(directory)
    files: list[BundleFile] = []
    manifest = BundleManifest()

    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue
        rel = filepath.relative_to(root).as_posix()

        if ".." in rel:
            continue

        content = filepath.read_bytes()

        if rel == ".manifest":
            manifest = BundleManifest.from_dict(json.loads(content))
        else:
            files.append(BundleFile(path=rel, content=content))

    return Bundle(files=files, manifest=manifest)


def build_bundle(
    policies: dict[str, str],
    data: dict[str, Any] | None = None,
    manifest: BundleManifest | None = None,
) -> bytes:
    """Build a .tar.gz bundle from policies and data.

    Args:
        policies: {path: rego_source} mapping
        data: Optional data document
        manifest: Optional manifest

    Returns:
        .tar.gz bytes
    """
    buf = io.BytesIO()
    manifest = manifest or BundleManifest()

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Add manifest
        manifest_bytes = json.dumps(manifest.to_dict()).encode()
        _add_to_tar(tar, ".manifest", manifest_bytes)

        # Add policies
        for path, source in sorted(policies.items()):
            _add_to_tar(tar, path, source.encode())

        # Add data
        if data:
            data_bytes = json.dumps(data).encode()
            _add_to_tar(tar, "data.json", data_bytes)

    return buf.getvalue()


def _add_to_tar(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


# ---------------------------------------------------------------------------
# Delta bundle support — OPA-compatible incremental bundle patches
# ---------------------------------------------------------------------------

@dataclass
class DeltaPatch:
    """A single operation in a delta bundle."""
    op: str       # "add", "remove", "replace"
    path: str     # e.g. "/data/roles" or "/policy/authz.rego"
    value: Any = None

    @staticmethod
    def from_dict(d: dict) -> DeltaPatch:
        return DeltaPatch(op=d["op"], path=d["path"], value=d.get("value"))


def apply_delta_bundle(
    delta: Bundle,
    store: Any,
    policies: dict[str, str],
) -> dict[str, str]:
    """Apply a delta bundle to an existing store and policy set.

    Delta bundles carry a ``delta.json`` file at their root that lists
    add/remove/replace operations (similar to JSON Patch but operating
    on the bundle's data and policy namespaces).

    Returns the updated policies dict.
    """
    patches: list[DeltaPatch] = []
    for f in delta.files:
        if PurePosixPath(f.path).name == "delta.json":
            raw = json.loads(f.content)
            patches = [DeltaPatch.from_dict(p) for p in raw]
            break

    updated_policies = dict(policies)

    for patch in patches:
        parts = [p for p in patch.path.strip("/").split("/") if p]
        if not parts:
            continue

        ns = parts[0]  # "data" or "policy"
        remainder = parts[1:]

        if ns == "data":
            if patch.op in ("add", "replace"):
                store.patch_data(remainder, patch.value)
            elif patch.op == "remove":
                try:
                    store.remove_data(remainder)
                except Exception:
                    pass
        elif ns == "policy":
            policy_path = "/".join(remainder)
            if patch.op in ("add", "replace") and isinstance(patch.value, str):
                updated_policies[policy_path] = patch.value
            elif patch.op == "remove":
                updated_policies.pop(policy_path, None)

    # Also merge any regular rego / data files present in the bundle
    for f in delta.rego_files:
        updated_policies[f.path] = f.content.decode("utf-8")

    data = delta.get_data()
    if data:
        store.patch_data([], data)

    return updated_policies
