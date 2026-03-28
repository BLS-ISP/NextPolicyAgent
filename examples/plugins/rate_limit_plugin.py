"""NPA Plugin-Beispiel 2: Rate-Limiting Plugin

Dieses Beispiel zeigt ein Plugin, das Policy-Anfragen pro Client
rate-limited und bei Überschreitung ablehnt.

Anwendungsfall:
  - API-Gateway-Integration
  - Schutz vor Brute-Force-Angriffen
  - Fair-Use-Enforcement
  - DoS-Prävention für den Policy-Endpunkt
"""

import asyncio
import time
from collections import defaultdict
from typing import Any

from npa.plugins.manager import (
    Plugin,
    PluginManager,
    PluginState,
    PluginStatus,
)


class RateLimitPlugin(Plugin):
    """Rate-Limiting für Policy-Anfragen basierend auf Client-ID.

    Verwendet einen Sliding-Window-Algorithmus.

    Konfiguration:
        rate_limit:
          max_requests_per_minute: 100
          max_requests_per_second: 20
          cleanup_interval: 60
          deny_message: "Rate limit exceeded"
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._status = PluginStatus()
        self._running = False
        self._cleanup_task: asyncio.Task | None = None

        # Sliding window: client_id -> list of timestamps
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._denied_count = 0
        self._allowed_count = 0

    @property
    def name(self) -> str:
        return "rate_limit"

    async def start(self, manager: PluginManager) -> None:
        self._running = True
        self._status = PluginStatus(state=PluginState.OK, message="Rate limiting active")

        interval = self._config.get("cleanup_interval", 60)
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup(interval))

        rpm = self._config.get("max_requests_per_minute", 100)
        rps = self._config.get("max_requests_per_second", 20)
        print(f"  [RateLimit] Active: {rpm} req/min, {rps} req/sec per client")

    async def stop(self) -> None:
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
        self._status = PluginStatus(state=PluginState.NOT_READY)
        print(f"  [RateLimit] Stopped. Allowed: {self._allowed_count}, Denied: {self._denied_count}")

    async def reconfigure(self, config: dict[str, Any]) -> None:
        self._config = config
        rpm = config.get("max_requests_per_minute", 100)
        rps = config.get("max_requests_per_second", 20)
        print(f"  [RateLimit] Reconfigured: {rpm} req/min, {rps} req/sec")

    def status(self) -> PluginStatus:
        return self._status

    def check_rate_limit(self, client_id: str) -> tuple[bool, str]:
        """Prüft, ob ein Client eine Anfrage stellen darf.

        Returns:
            (allowed, message) — True wenn erlaubt, sonst Ablehnungsgrund
        """
        now = time.time()
        window = self._windows[client_id]

        # Alte Einträge entfernen (älter als 60s)
        cutoff_minute = now - 60
        window[:] = [t for t in window if t > cutoff_minute]

        # Prüfe per-Minute-Limit
        rpm_limit = self._config.get("max_requests_per_minute", 100)
        if len(window) >= rpm_limit:
            self._denied_count += 1
            msg = self._config.get("deny_message", "Rate limit exceeded")
            return False, f"{msg}: {len(window)}/{rpm_limit} requests/minute"

        # Prüfe per-Sekunde-Limit
        rps_limit = self._config.get("max_requests_per_second", 20)
        cutoff_second = now - 1
        recent = sum(1 for t in window if t > cutoff_second)
        if recent >= rps_limit:
            self._denied_count += 1
            msg = self._config.get("deny_message", "Rate limit exceeded")
            return False, f"{msg}: {recent}/{rps_limit} requests/second"

        # Erlaubt
        window.append(now)
        self._allowed_count += 1
        return True, "OK"

    def get_client_stats(self, client_id: str) -> dict[str, Any]:
        """Gibt Rate-Limit-Statistiken für einen Client zurück."""
        now = time.time()
        window = self._windows.get(client_id, [])
        recent = [t for t in window if t > now - 60]
        last_second = sum(1 for t in recent if t > now - 1)

        return {
            "client_id": client_id,
            "requests_last_minute": len(recent),
            "requests_last_second": last_second,
            "limit_per_minute": self._config.get("max_requests_per_minute", 100),
            "limit_per_second": self._config.get("max_requests_per_second", 20),
        }

    async def _periodic_cleanup(self, interval: float) -> None:
        """Entfernt abgelaufene Einträge aus dem Sliding Window."""
        while self._running:
            await asyncio.sleep(interval)
            now = time.time()
            cutoff = now - 120  # 2 Minuten Buffer
            empty_clients = []
            for client_id, window in self._windows.items():
                window[:] = [t for t in window if t > cutoff]
                if not window:
                    empty_clients.append(client_id)
            for c in empty_clients:
                del self._windows[c]


# ─────────────────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────────────────

async def demo():
    """Demonstriert das Rate-Limiting Plugin."""
    print("=" * 60)
    print("NPA Plugin-Beispiel: Rate Limiting")
    print("=" * 60)

    # 1. Plugin-Manager aufsetzen
    manager = PluginManager()

    # 2. Rate-Limit-Plugin konfigurieren (niedrige Limits für Demo)
    rl_config = {
        "max_requests_per_minute": 10,
        "max_requests_per_second": 3,
        "cleanup_interval": 30,
        "deny_message": "Zu viele Anfragen",
    }
    rl_plugin = RateLimitPlugin(config=rl_config)
    manager.register(rl_plugin)

    # 3. Plugin starten
    await manager.start_all()

    # 4. Anfragen simulieren
    print("\n  --- Anfragen von Client 'service-a' ---")
    for i in range(15):
        allowed, msg = rl_plugin.check_rate_limit("service-a")
        status = "OK" if allowed else "DENIED"
        print(f"  Request {i+1:2d}: {status} {msg}")

        # Kurze Pause nach jedem 3. Request
        if (i + 1) % 3 == 0:
            await asyncio.sleep(0.01)

    # 5. Client-Statistiken
    print("\n  --- Client-Statistiken ---")
    stats = rl_plugin.get_client_stats("service-a")
    for key, value in stats.items():
        print(f"    {key}: {value}")

    # 6. Zweiter Client ist unbetroffem
    print("\n  --- Anfragen von Client 'service-b' ---")
    for i in range(3):
        allowed, msg = rl_plugin.check_rate_limit("service-b")
        status = "OK" if allowed else "DENIED"
        print(f"  Request {i+1}: {status} {msg}")

    # 7. Plugin-Status
    print(f"\n  Plugin-Status: {rl_plugin.status()}")
    print(f"  Gesamt erlaubt: {rl_plugin._allowed_count}")
    print(f"  Gesamt abgelehnt: {rl_plugin._denied_count}")

    # 8. Stoppen
    await manager.stop_all()


if __name__ == "__main__":
    asyncio.run(demo())
