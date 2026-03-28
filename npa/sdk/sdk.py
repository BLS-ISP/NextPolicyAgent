"""High-level SDK for embedding NPA in Python applications.

Provides a simple API for policy evaluation without running the full server.

Usage:
    npa = NPA()
    npa.load_policy("example.rego", '''
        package example
        default allow = false
        allow { input.user == "admin" }
    ''')
    result = npa.decide("data.example.allow", {"user": "admin"})
    assert result is True
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from npa.ast.compiler import Compiler
from npa.ast.parser import parse_module
from npa.bundle.bundle import Bundle, load_bundle_from_bytes, load_bundle_from_dir
from npa.eval.cache import InterQueryCache
from npa.eval.topdown import TopdownEvaluator, UndefinedError
from npa.storage.inmemory import InMemoryStorage


class NPAError(Exception):
    pass


class NPA:
    """Embeddable policy engine — the primary SDK entry point.

    Thread-safe for concurrent evaluations after setup.
    """

    def __init__(self, cache_size: int = 10_000, cache_ttl: float = 300.0) -> None:
        self._storage = InMemoryStorage()
        self._compiler = Compiler()
        self._cache = InterQueryCache(max_size=cache_size, ttl_seconds=cache_ttl)
        self._evaluator: TopdownEvaluator | None = None
        self._modules: dict[str, str] = {}

    def load_policy(self, policy_id: str, raw_rego: str) -> None:
        """Load or update a Rego policy."""
        self._modules[policy_id] = raw_rego
        self._rebuild()

    def load_policies(self, policies: dict[str, str]) -> None:
        """Load multiple policies at once."""
        self._modules.update(policies)
        self._rebuild()

    def remove_policy(self, policy_id: str) -> None:
        """Remove a policy."""
        self._modules.pop(policy_id, None)
        self._rebuild()

    def load_data(self, path: list[str], data: Any) -> None:
        """Load data at the given path."""
        self._storage.patch_data(path, data)

    def set_data(self, data: dict[str, Any]) -> None:
        """Replace the entire data document."""
        self._storage.patch_data([], data)

    def load_bundle(self, bundle: Bundle) -> None:
        """Load policies and data from a bundle."""
        for path, source in bundle.get_policies().items():
            self._modules[path] = source
        data = bundle.get_data()
        if data:
            self._storage.patch_data([], data)
        self._rebuild()

    def load_bundle_from_file(self, path: str | Path) -> None:
        """Load a bundle from a .tar.gz file."""
        data = Path(path).read_bytes()
        bundle = load_bundle_from_bytes(data)
        self.load_bundle(bundle)

    def load_bundle_from_dir(self, directory: str | Path) -> None:
        """Load a bundle from a directory."""
        bundle = load_bundle_from_dir(directory)
        self.load_bundle(bundle)

    def decide(self, query: str, input_data: Any = None) -> Any:
        """Evaluate a policy query and return the result.

        Args:
            query: Dot-separated path (e.g. "data.example.allow")
            input_data: Input document for the evaluation

        Returns:
            The evaluation result

        Raises:
            NPAError: On evaluation errors
        """
        if not self._evaluator:
            raise NPAError("No policies loaded")

        try:
            return self._evaluator.eval_query(query, input_data=input_data)
        except UndefinedError:
            return None
        except Exception as e:
            raise NPAError(f"Evaluation error: {e}") from e

    def decide_bool(self, query: str, input_data: Any = None) -> bool:
        """Evaluate a query and return a boolean result.

        Convenience method — returns False for undefined/falsy results.
        """
        result = self.decide(query, input_data)
        if result is None:
            return False
        if isinstance(result, bool):
            return result
        return bool(result)

    @property
    def cache_stats(self) -> dict[str, int]:
        return self._cache.stats

    def clear_cache(self) -> None:
        self._cache.clear()

    def _rebuild(self) -> None:
        """Recompile all policies and rebuild the evaluator."""
        modules = []
        for pid, raw in self._modules.items():
            try:
                mod = parse_module(pid, raw)
                modules.append(mod)
            except Exception as e:
                raise NPAError(f"Parse error in {pid}: {e}") from e

        self._compiler = Compiler()
        self._compiler.compile(modules)
        self._evaluator = TopdownEvaluator(
            compiler=self._compiler,
            store=self._storage,
            inter_cache=self._cache,
        )
