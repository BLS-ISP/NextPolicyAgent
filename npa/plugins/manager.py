"""Plugin manager for NPA.

Implements OPA-compatible plugin lifecycle:
- Registration, configuration, start, stop, reconfigure
- Built-in plugins: bundle, decision_log, status, discovery
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class PluginState(Enum):
    NOT_READY = auto()
    OK = auto()
    ERROR = auto()


@dataclass
class PluginStatus:
    state: PluginState = PluginState.NOT_READY
    message: str = ""


class Plugin(ABC):
    """Base class for NPA plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def start(self, manager: PluginManager) -> None:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    async def reconfigure(self, config: dict[str, Any]) -> None:
        ...

    @abstractmethod
    def status(self) -> PluginStatus:
        ...


class PluginManager:
    """Manages plugin lifecycle and inter-plugin communication."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._config: dict[str, Any] = {}
        self._store: Any = None
        self._compiler: Any = None
        self._info: dict[str, Any] = {}  # runtime info (version, id, etc.)

    def register(self, plugin: Plugin) -> None:
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    @property
    def store(self) -> Any:
        return self._store

    @store.setter
    def store(self, value: Any) -> None:
        self._store = value

    @property
    def compiler(self) -> Any:
        return self._compiler

    @compiler.setter
    def compiler(self, value: Any) -> None:
        self._compiler = value

    @property
    def info(self) -> dict[str, Any]:
        return self._info

    @info.setter
    def info(self, value: dict[str, Any]) -> None:
        self._info = value

    async def start_all(self) -> None:
        for name, plugin in self._plugins.items():
            try:
                await plugin.start(self)
                logger.info("Plugin started", extra={"plugin": name})
            except Exception:
                logger.exception("Plugin failed to start", extra={"plugin": name})

    async def stop_all(self) -> None:
        for name, plugin in reversed(list(self._plugins.items())):
            try:
                await plugin.stop()
                logger.info("Plugin stopped", extra={"plugin": name})
            except Exception:
                logger.exception("Plugin failed to stop", extra={"plugin": name})

    def statuses(self) -> dict[str, PluginStatus]:
        return {name: plugin.status() for name, plugin in self._plugins.items()}


# ---------------------------------------------------------------------------
# Built-in plugins
# ---------------------------------------------------------------------------


class BundlePlugin(Plugin):
    """Plugin that polls for bundle updates and applies them.

    OPA-compatible configuration::

        bundles:
          authz:
            url: https://bundle-server/bundles/authz
            polling:
              min_delay_seconds: 10
              max_delay_seconds: 30
            signing:
              keyid: my_key
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._status = PluginStatus()
        self._tasks: list[asyncio.Task[None]] = []
        self._manager: PluginManager | None = None
        self._running = False

    @property
    def name(self) -> str:
        return "bundle"

    async def start(self, manager: PluginManager) -> None:
        self._manager = manager
        self._running = True
        self._status = PluginStatus(state=PluginState.OK, message="Running")

        # Start a polling task per configured bundle
        bundles_cfg = self._config.get("bundles", {})
        for bundle_name, bcfg in bundles_cfg.items():
            task = asyncio.create_task(
                self._poll_bundle(bundle_name, bcfg),
                name=f"bundle-{bundle_name}",
            )
            self._tasks.append(task)

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        self._status = PluginStatus(state=PluginState.NOT_READY)

    async def reconfigure(self, config: dict[str, Any]) -> None:
        await self.stop()
        self._config = config
        if self._manager:
            await self.start(self._manager)

    def status(self) -> PluginStatus:
        return self._status

    async def _poll_bundle(self, name: str, cfg: dict[str, Any]) -> None:
        """Poll a single bundle source for updates."""
        from npa.bundle.loader import BundleLoader
        from npa.config.config import BundleSourceConfig

        url = cfg.get("url", cfg.get("resource", ""))
        polling = cfg.get("polling", {})
        interval = polling.get("min_delay_seconds", 60)
        auth_token = cfg.get("credentials", {}).get("bearer", {}).get("token", "")

        source_cfg = BundleSourceConfig(
            name=name,
            url=url,
            polling_interval=interval,
            auth_token=auth_token,
        )
        loader = BundleLoader(config=source_cfg)

        while self._running:
            try:
                bundle = await loader.fetch()
                if bundle and self._manager:
                    # Apply bundle to store + compiler
                    self._apply_bundle(bundle)
                    logger.info("Bundle updated",
                                extra={"name": name, "revision": bundle.manifest.revision})

                    # Notify status plugin
                    status_plugin = self._manager.get("status")
                    if status_plugin and isinstance(status_plugin, StatusPlugin):
                        status_plugin.record_bundle(name, bundle.manifest.revision)
            except Exception:
                logger.exception("Bundle fetch failed", extra={"name": name})
                self._status = PluginStatus(state=PluginState.ERROR, message=f"Fetch failed for {name}")

            await asyncio.sleep(interval)

    def _apply_bundle(self, bundle: Any) -> None:
        """Apply bundle policies and data to the manager's store/compiler."""
        if not self._manager:
            return
        store = self._manager.store
        if store is None:
            return

        from npa.ast.parser import parse_module
        from npa.ast.compiler import Compiler

        # Load policies
        policies = bundle.get_policies()
        data = bundle.get_data()

        if data:
            store.patch_data([], data)

        # Recompile if we have policies
        if policies:
            modules = {}
            for path, source in policies.items():
                try:
                    modules[path] = parse_module(source, path)
                except Exception:
                    logger.exception("Failed to parse policy from bundle", extra={"path": path})

            if modules:
                compiler = Compiler()
                # Include any existing modules
                existing = getattr(self._manager.compiler, 'modules', {})
                all_modules = {**existing, **modules}
                compiler.compile(all_modules)
                self._manager.compiler = compiler


class DecisionLogPlugin(Plugin):
    """Plugin that records and ships decision logs to a remote endpoint.

    OPA-compatible configuration::

        decision_logs:
          reporting:
            url: https://my-opa-logging/logs
            min_delay_seconds: 5
            max_delay_seconds: 30
          console: false
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._status = PluginStatus()
        self._buffer: list[dict[str, Any]] = []
        self._max_buffer: int = 10000
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._manager: PluginManager | None = None

    @property
    def name(self) -> str:
        return "decision_log"

    async def start(self, manager: PluginManager) -> None:
        self._manager = manager
        self._running = True
        self._status = PluginStatus(state=PluginState.OK)

        # Start periodic flush task
        reporting = self._config.get("reporting", {})
        if reporting.get("url"):
            interval = reporting.get("min_delay_seconds", 10)
            self._task = asyncio.create_task(self._periodic_flush(interval))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        await self._flush()
        self._status = PluginStatus(state=PluginState.NOT_READY)

    async def reconfigure(self, config: dict[str, Any]) -> None:
        await self.stop()
        self._config = config
        if self._manager:
            await self.start(self._manager)

    def status(self) -> PluginStatus:
        return self._status

    def record(self, decision: dict[str, Any]) -> None:
        """Record a decision event."""
        entry = {
            "decision_id": decision.get("decision_id", str(uuid.uuid4())),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "query": decision.get("query", ""),
            "input": decision.get("input"),
            "result": decision.get("result"),
            "metrics": decision.get("metrics"),
        }

        # Console log if enabled
        if self._config.get("console"):
            logger.info("Decision", extra=entry)

        if len(self._buffer) < self._max_buffer:
            self._buffer.append(entry)

    async def _periodic_flush(self, interval: float) -> None:
        while self._running:
            await asyncio.sleep(interval)
            await self._flush()

    async def _flush(self) -> None:
        """Flush buffered decisions to the configured endpoint."""
        if not self._buffer:
            return
        url = self._config.get("reporting", {}).get("url")
        if not url:
            self._buffer.clear()
            return

        import httpx
        batch = list(self._buffer)
        self._buffer.clear()

        async with httpx.AsyncClient(verify=True, timeout=10.0) as client:
            try:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                auth_token = self._config.get("reporting", {}).get("credentials", {}).get("bearer", {}).get("token", "")
                if auth_token:
                    headers["Authorization"] = f"Bearer {auth_token}"
                await client.post(url, json=batch, headers=headers)
            except Exception:
                logger.exception("Failed to flush decision logs")
                # Re-buffer failed entries (up to limit)
                remaining = self._max_buffer - len(self._buffer)
                self._buffer.extend(batch[:remaining])


class StatusPlugin(Plugin):
    """Plugin that reports agent status to a remote endpoint.

    OPA-compatible configuration::

        status:
          url: https://my-opa-status/status
          min_delay_seconds: 10
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._status = PluginStatus()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._manager: PluginManager | None = None
        self._bundle_statuses: dict[str, dict[str, Any]] = {}

    @property
    def name(self) -> str:
        return "status"

    async def start(self, manager: PluginManager) -> None:
        self._manager = manager
        self._running = True
        self._status = PluginStatus(state=PluginState.OK)

        url = self._config.get("url")
        if url:
            interval = self._config.get("min_delay_seconds", 30)
            self._task = asyncio.create_task(self._periodic_report(interval))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self._status = PluginStatus(state=PluginState.NOT_READY)

    async def reconfigure(self, config: dict[str, Any]) -> None:
        await self.stop()
        self._config = config
        if self._manager:
            await self.start(self._manager)

    def status(self) -> PluginStatus:
        return self._status

    def record_bundle(self, name: str, revision: str) -> None:
        """Record that a bundle was loaded/updated."""
        self._bundle_statuses[name] = {
            "name": name,
            "active_revision": revision,
            "last_successful_activation": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _build_status_report(self) -> dict[str, Any]:
        """Build OPA-compatible status report."""
        report: dict[str, Any] = {
            "labels": self._manager.info.get("labels", {}) if self._manager else {},
        }

        # Plugin statuses
        if self._manager:
            plugins: dict[str, Any] = {}
            for pname, plugin in self._manager._plugins.items():
                ps = plugin.status()
                plugins[pname] = {"state": ps.state.name.lower(), "message": ps.message}
            report["plugins"] = plugins

        # Bundle statuses
        if self._bundle_statuses:
            report["bundles"] = dict(self._bundle_statuses)

        return report

    async def _periodic_report(self, interval: float) -> None:
        while self._running:
            await asyncio.sleep(interval)
            await self._send_report()

    async def _send_report(self) -> None:
        url = self._config.get("url")
        if not url:
            return

        import httpx
        report = self._build_status_report()

        async with httpx.AsyncClient(verify=True, timeout=10.0) as client:
            try:
                headers: dict[str, str] = {"Content-Type": "application/json"}
                auth_token = self._config.get("credentials", {}).get("bearer", {}).get("token", "")
                if auth_token:
                    headers["Authorization"] = f"Bearer {auth_token}"
                await client.post(url, json=report, headers=headers)
            except Exception:
                logger.exception("Failed to send status report")


class DiscoveryPlugin(Plugin):
    """Plugin that fetches configuration from a remote discovery endpoint.

    OPA-compatible configuration::

        discovery:
          url: https://config-server/config
          polling:
            min_delay_seconds: 60
          decision: /config/result
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._status = PluginStatus()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._manager: PluginManager | None = None
        self._etag: str = ""

    @property
    def name(self) -> str:
        return "discovery"

    async def start(self, manager: PluginManager) -> None:
        self._manager = manager
        self._running = True
        self._status = PluginStatus(state=PluginState.OK)

        url = self._config.get("url")
        if url:
            interval = self._config.get("polling", {}).get("min_delay_seconds", 60)
            self._task = asyncio.create_task(self._poll_config(interval))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self._status = PluginStatus(state=PluginState.NOT_READY)

    async def reconfigure(self, config: dict[str, Any]) -> None:
        await self.stop()
        self._config = config
        if self._manager:
            await self.start(self._manager)

    def status(self) -> PluginStatus:
        return self._status

    async def _poll_config(self, interval: float) -> None:
        while self._running:
            try:
                await self._fetch_and_apply()
            except Exception:
                logger.exception("Discovery fetch failed")
                self._status = PluginStatus(state=PluginState.ERROR, message="Discovery fetch failed")
            await asyncio.sleep(interval)

    async def _fetch_and_apply(self) -> None:
        """Fetch discovery bundle and reconfigure plugins."""
        url = self._config.get("url")
        if not url:
            return

        import httpx
        headers: dict[str, str] = {}
        if self._etag:
            headers["If-None-Match"] = self._etag

        auth_token = self._config.get("credentials", {}).get("bearer", {}).get("token", "")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        async with httpx.AsyncClient(verify=True, timeout=30.0) as client:
            resp = await client.get(url, headers=headers)

            if resp.status_code == 304:
                return  # Not modified

            resp.raise_for_status()
            self._etag = resp.headers.get("ETag", "")

            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                new_config = resp.json()
            else:
                # Assume it's a bundle — use bundle loader
                from npa.bundle.bundle import load_bundle_from_bytes
                bundle = load_bundle_from_bytes(resp.content)
                new_config = bundle.get_data()

            # Extract the configuration at the decision path
            decision_path = self._config.get("decision", "")
            if decision_path:
                parts = [p for p in decision_path.strip("/").split("/") if p]
                for part in parts:
                    if isinstance(new_config, dict) and part in new_config:
                        new_config = new_config[part]
                    else:
                        logger.warning(
                            "Discovery decision path not found",
                            extra={"path": decision_path},
                        )
                        return

            # Reconfigure other plugins
            if self._manager and isinstance(new_config, dict):
                for plugin_name, plugin_cfg in new_config.items():
                    plugin = self._manager.get(plugin_name)
                    if plugin and isinstance(plugin_cfg, dict):
                        await plugin.reconfigure(plugin_cfg)
                        logger.info("Plugin reconfigured via discovery",
                                    extra={"plugin": plugin_name})
