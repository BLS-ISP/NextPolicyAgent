"""Bundle loader — fetches bundles from HTTP(S) endpoints or disk.

Supports polling, ETags for conditional fetching, and retry logic.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

from npa.bundle.bundle import Bundle, load_bundle_from_bytes, load_bundle_from_dir
from npa.bundle.sign import verify_bundle, VerificationError
from npa.config.config import BundleSourceConfig

logger = logging.getLogger(__name__)


@dataclass
class BundleLoader:
    """Async bundle loader with polling support."""

    config: BundleSourceConfig
    verification_key: str | None = None
    _etag: str = ""
    _last_bundle: Bundle | None = None
    _on_update: Callable[[Bundle], Any] | None = None
    _running: bool = False

    async def fetch(self) -> Bundle | None:
        """Fetch the bundle from the configured source.

        Returns None if the bundle hasn't changed (304 Not Modified).
        """
        url = self.config.url

        if not url or url.startswith("file://") or Path(url).exists():
            # Load from disk
            path = url.removeprefix("file://") if url.startswith("file://") else url
            bundle = load_bundle_from_dir(path)
            if self._last_bundle and bundle.content_hash() == self._last_bundle.content_hash():
                return None
            self._verify(bundle)
            self._last_bundle = bundle
            return bundle

        # HTTP(S) fetch
        headers: dict[str, str] = {}
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"

        async with httpx.AsyncClient(verify=True, timeout=30.0) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code == 304:
                return None

            resp.raise_for_status()
            self._etag = resp.headers.get("ETag", "")

            bundle = load_bundle_from_bytes(resp.content)
            self._verify(bundle)
            self._last_bundle = bundle
            return bundle

    def _verify(self, bundle: Bundle) -> None:
        """Verify bundle signature if verification key is configured."""
        if not self.verification_key or not bundle.signature:
            return

        try:
            verify_bundle(
                bundle.signature,
                self.verification_key,
                expected_hash=bundle.content_hash(),
            )
        except VerificationError as e:
            raise VerificationError(f"Bundle signature verification failed: {e}") from e

    async def poll(self, on_update: Callable[[Bundle], Any]) -> None:
        """Start polling for bundle updates."""
        self._on_update = on_update
        self._running = True

        while self._running:
            try:
                bundle = await self.fetch()
                if bundle and self._on_update:
                    self._on_update(bundle)
                    logger.info(
                        "Bundle updated",
                        extra={"name": self.config.name, "revision": bundle.manifest.revision},
                    )
            except Exception:
                logger.exception("Bundle fetch failed", extra={"name": self.config.name})

            await asyncio.sleep(self.config.polling_interval)

    def stop(self) -> None:
        self._running = False
