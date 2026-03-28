"""NPA Plugin-Beispiel 1: Custom Audit-Trail Plugin

Dieses Beispiel zeigt, wie man ein eigenes NPA-Plugin schreibt,
das jede Policy-Entscheidung in eine lokale Audit-Log-Datei schreibt.

Anwendungsfall:
  - Compliance-Anforderungen (z.B. SOX, GDPR)
  - Forensische Nachverfolgung von Autorisierungsentscheidungen
  - Offline-Audit ohne externe Log-Infrastruktur
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from npa.plugins.manager import (
    Plugin,
    PluginManager,
    PluginState,
    PluginStatus,
)


class AuditTrailPlugin(Plugin):
    """Schreibt jede Policy-Entscheidung als JSON-Zeile in eine Audit-Datei.

    Konfiguration:
        audit_trail:
          log_file: "/var/log/npa/audit.jsonl"
          include_input: true       # Input-Daten mitloggen
          include_result: true      # Ergebnis mitloggen
          flush_interval: 5         # Sekunden zwischen Disk-Flushes
          max_file_size_mb: 100     # Rotation bei dieser Größe
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._status = PluginStatus()
        self._log_path: Path | None = None
        self._file = None
        self._buffer: list[str] = []
        self._running = False
        self._flush_task: asyncio.Task | None = None
        self._entry_count = 0

    @property
    def name(self) -> str:
        return "audit_trail"

    async def start(self, manager: PluginManager) -> None:
        log_file = self._config.get("log_file", "npa_audit.jsonl")
        self._log_path = Path(log_file)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._log_path, "a", encoding="utf-8")
        self._running = True
        self._status = PluginStatus(state=PluginState.OK, message="Auditing active")

        interval = self._config.get("flush_interval", 5)
        self._flush_task = asyncio.create_task(self._periodic_flush(interval))

        print(f"  [AuditTrail] Logging to {self._log_path}")

    async def stop(self) -> None:
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
        self._flush()
        if self._file:
            self._file.close()
            self._file = None
        self._status = PluginStatus(state=PluginState.NOT_READY)
        print(f"  [AuditTrail] Stopped. {self._entry_count} entries written.")

    async def reconfigure(self, config: dict[str, Any]) -> None:
        await self.stop()
        self._config = config
        # Re-start would require the manager reference
        self._status = PluginStatus(state=PluginState.NOT_READY, message="Reconfigured, needs restart")

    def status(self) -> PluginStatus:
        return self._status

    def record_decision(self, decision: dict[str, Any]) -> None:
        """Eine Entscheidung aufzeichnen."""
        entry: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "decision_id": decision.get("decision_id", "unknown"),
            "query": decision.get("query", ""),
        }

        if self._config.get("include_input", True):
            entry["input"] = decision.get("input")

        if self._config.get("include_result", True):
            entry["result"] = decision.get("result")
            entry["allowed"] = bool(decision.get("result"))

        self._buffer.append(json.dumps(entry, default=str))

    def _flush(self) -> None:
        if self._file and self._buffer:
            for line in self._buffer:
                self._file.write(line + "\n")
            self._file.flush()
            self._entry_count += len(self._buffer)
            self._buffer.clear()

            # Check rotation
            max_mb = self._config.get("max_file_size_mb", 100)
            if self._log_path and self._log_path.stat().st_size > max_mb * 1024 * 1024:
                self._rotate()

    def _rotate(self) -> None:
        """Einfache Log-Rotation."""
        if self._file:
            self._file.close()
        if self._log_path:
            rotated = self._log_path.with_suffix(
                f".{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
            )
            self._log_path.rename(rotated)
            self._file = open(self._log_path, "a", encoding="utf-8")
            print(f"  [AuditTrail] Rotated to {rotated}")

    async def _periodic_flush(self, interval: float) -> None:
        while self._running:
            await asyncio.sleep(interval)
            self._flush()


# ─────────────────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────────────────

async def demo():
    """Demonstriert das Audit-Trail-Plugin."""
    print("=" * 60)
    print("NPA Plugin-Beispiel: Audit Trail")
    print("=" * 60)

    # 1. Plugin-Manager aufsetzen
    manager = PluginManager()

    # 2. Audit-Trail-Plugin konfigurieren und registrieren
    audit_config = {
        "log_file": "demo_audit.jsonl",
        "include_input": True,
        "include_result": True,
        "flush_interval": 2,
        "max_file_size_mb": 10,
    }
    audit_plugin = AuditTrailPlugin(config=audit_config)
    manager.register(audit_plugin)

    # 3. Alle Plugins starten
    await manager.start_all()

    # 4. Einige Entscheidungen simulieren
    decisions = [
        {"decision_id": "d-001", "query": "data.rbac.allow", "input": {"user": "alice", "action": "read"}, "result": True},
        {"decision_id": "d-002", "query": "data.rbac.allow", "input": {"user": "bob", "action": "delete"}, "result": False},
        {"decision_id": "d-003", "query": "data.rbac.allow", "input": {"user": "admin", "action": "write"}, "result": True},
        {"decision_id": "d-004", "query": "data.network.allow", "input": {"src_ip": "10.0.1.5", "dst_port": 443}, "result": True},
        {"decision_id": "d-005", "query": "data.network.allow", "input": {"src_ip": "192.168.1.100", "dst_port": 22}, "result": False},
    ]

    for d in decisions:
        audit_plugin.record_decision(d)
        allowed = "ERLAUBT" if d["result"] else "VERWEIGERT"
        print(f"  {d['decision_id']}: {d['query']} -> {allowed}")

    # 5. Flush und Status prüfen
    audit_plugin._flush()

    print(f"\n  Plugin-Status: {audit_plugin.status()}")
    print(f"  Einträge geschrieben: {audit_plugin._entry_count}")

    # 6. Audit-Datei anzeigen
    log_file = Path("demo_audit.jsonl")
    if log_file.exists():
        print(f"\n  Audit-Datei ({log_file}):")
        print("  " + "-" * 56)
        for line in log_file.read_text(encoding="utf-8").strip().split("\n"):
            entry = json.loads(line)
            print(f"  {entry['timestamp']} | {entry['decision_id']} | "
                  f"{'ALLOW' if entry['allowed'] else 'DENY':>5} | {entry['query']}")

    # 7. Aufräumen
    await manager.stop_all()

    # Status aller Plugins
    print(f"\n  Plugin-Statuses nach Stop:")
    for name, status in manager.statuses().items():
        print(f"    {name}: {status.state.name}")

    # Demo-Datei aufräumen
    if log_file.exists():
        log_file.unlink()
        print(f"\n  Demo-Datei {log_file} entfernt.")


if __name__ == "__main__":
    asyncio.run(demo())
