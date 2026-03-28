"""NPA Plugin-Beispiel 3: Webhook-Notification Plugin

Dieses Beispiel zeigt ein Plugin, das bei bestimmten Policy-Entscheidungen
Benachrichtigungen per Webhook versendet (z.B. Slack, Teams, Discord).

Anwendungsfall:
  - Echtzeit-Benachrichtigungen bei Deny-Entscheidungen
  - Sicherheits-Alerting
  - Compliance-Monitoring
  - Integration mit Incident-Management-Systemen
"""

import asyncio
import json
import time
from collections import deque
from typing import Any

from npa.plugins.manager import (
    Plugin,
    PluginManager,
    PluginState,
    PluginStatus,
)


class WebhookNotificationPlugin(Plugin):
    """Sendet Benachrichtigungen per Webhook bei Policy-Entscheidungen.

    Unterstützt Batching und konfigurierbare Filter.

    Konfiguration:
        webhook_notification:
          url: "https://hooks.slack.com/services/..."
          format: "slack"           # slack | teams | generic
          notify_on: ["deny"]       # deny | allow | error
          min_severity: "medium"    # low | medium | high | critical
          batch_size: 10
          flush_interval: 5
          include_input: false
          max_retries: 3
    """

    FORMATS = {"slack", "teams", "generic"}
    SEVERITIES = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._status = PluginStatus()
        self._running = False
        self._flush_task: asyncio.Task | None = None
        self._buffer: deque[dict[str, Any]] = deque(maxlen=1000)
        self._sent_count = 0
        self._error_count = 0

    @property
    def name(self) -> str:
        return "webhook_notification"

    async def start(self, manager: PluginManager) -> None:
        self._running = True
        self._status = PluginStatus(state=PluginState.OK, message="Webhook active")

        interval = self._config.get("flush_interval", 5)
        self._flush_task = asyncio.create_task(self._periodic_flush(interval))

        fmt = self._config.get("format", "generic")
        triggers = self._config.get("notify_on", ["deny"])
        print(f"  [Webhook] Active: format={fmt}, triggers={triggers}")

    async def stop(self) -> None:
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
        # Restliche Events noch flushen
        if self._buffer:
            await self._flush()
        self._status = PluginStatus(state=PluginState.NOT_READY)
        print(f"  [Webhook] Stopped. Sent: {self._sent_count}, Errors: {self._error_count}")

    async def reconfigure(self, config: dict[str, Any]) -> None:
        self._config = config
        print(f"  [Webhook] Reconfigured: format={config.get('format', 'generic')}")

    def status(self) -> PluginStatus:
        return self._status

    def notify(self, event: dict[str, Any]) -> None:
        """Fügt ein Event zur Notification-Queue hinzu.

        Args:
            event: Dict mit mindestens:
                - decision: "allow" | "deny" | "error"
                - path: Policy-Pfad
                Optional:
                - severity: "low" | "medium" | "high" | "critical"
                - input: Eingabedaten
                - message: Freitext
        """
        # Filter: Nur gewünschte Entscheidungstypen
        triggers = self._config.get("notify_on", ["deny"])
        decision = event.get("decision", "unknown")
        if decision not in triggers:
            return

        # Filter: Mindest-Severity
        min_sev = self._config.get("min_severity", "low")
        event_sev = event.get("severity", "medium")
        if self.SEVERITIES.get(event_sev, 0) < self.SEVERITIES.get(min_sev, 0):
            return

        # Input entfernen wenn nicht gewünscht
        if not self._config.get("include_input", False):
            event = {k: v for k, v in event.items() if k != "input"}

        event["timestamp"] = time.time()
        self._buffer.append(event)

    def _format_payload(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Formatiert Events je nach Zielplattform."""
        fmt = self._config.get("format", "generic")

        if fmt == "slack":
            return self._format_slack(events)
        elif fmt == "teams":
            return self._format_teams(events)
        else:
            return self._format_generic(events)

    def _format_slack(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Slack-kompatibles Payload-Format."""
        blocks = []
        for e in events:
            icon = "[X]" if e.get("decision") == "deny" else "[!]"
            severity = e.get("severity", "medium").upper()
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{icon} *Policy Alert* [{severity}]\n"
                        f"• Decision: `{e.get('decision', 'unknown')}`\n"
                        f"• Path: `{e.get('path', 'N/A')}`\n"
                        f"• Message: {e.get('message', '-')}"
                    ),
                },
            })
        return {"blocks": blocks}

    def _format_teams(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Microsoft Teams Adaptive Card Format."""
        facts = []
        for e in events:
            facts.append({
                "title": f"[{e.get('severity', 'medium').upper()}] {e.get('decision', 'unknown')}",
                "value": f"Path: {e.get('path', 'N/A')} — {e.get('message', '-')}",
            })
        return {
            "@type": "MessageCard",
            "summary": f"NPA Policy Alerts ({len(events)})",
            "sections": [{"facts": facts}],
        }

    def _format_generic(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """Generisches JSON-Payload."""
        return {
            "source": "npa",
            "event_count": len(events),
            "events": events,
        }

    async def _flush(self) -> None:
        """Sendet gebufferte Events als Webhook."""
        if not self._buffer:
            return

        batch_size = self._config.get("batch_size", 10)
        batch: list[dict[str, Any]] = []
        while self._buffer and len(batch) < batch_size:
            batch.append(self._buffer.popleft())

        payload = self._format_payload(batch)
        url = self._config.get("url", "")

        if url:
            # In einem echten Setup: httpx.AsyncClient POST
            # Hier simuliert für das Beispiel
            max_retries = self._config.get("max_retries", 3)
            for attempt in range(max_retries):
                try:
                    # Simulierter HTTP-Call:
                    # async with httpx.AsyncClient() as client:
                    #     resp = await client.post(url, json=payload)
                    #     resp.raise_for_status()
                    self._sent_count += len(batch)
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        self._error_count += len(batch)
                        self._status = PluginStatus(
                            state=PluginState.ERROR,
                            message=f"Webhook failed: {e}",
                        )
        else:
            # Kein URL konfiguriert -> nur loggen
            print(f"  [Webhook] Would send {len(batch)} events: {json.dumps(payload, indent=2)}")
            self._sent_count += len(batch)

    async def _periodic_flush(self, interval: float) -> None:
        while self._running:
            await asyncio.sleep(interval)
            await self._flush()


# ─────────────────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────────────────

async def demo():
    """Demonstriert das Webhook-Notification Plugin."""
    print("=" * 60)
    print("NPA Plugin-Beispiel: Webhook Notifications")
    print("=" * 60)

    # 1. Plugin-Manager
    manager = PluginManager()

    # 2. Webhook-Plugin konfigurieren (Slack-Format, kein echter URL)
    wh_config = {
        "url": "",  # Leer -> nur Konsolenausgabe
        "format": "slack",
        "notify_on": ["deny", "error"],
        "min_severity": "medium",
        "batch_size": 5,
        "flush_interval": 2,
        "include_input": False,
    }
    wh_plugin = WebhookNotificationPlugin(config=wh_config)
    manager.register(wh_plugin)

    await manager.start_all()

    # 3. Verschiedene Events simulieren
    print("\n  --- Events simulieren ---")

    # Deny-Event (medium) -> wird gesendet
    wh_plugin.notify({
        "decision": "deny",
        "path": "authz/allow",
        "severity": "high",
        "message": "Unautorisierter Zugriff auf /admin",
        "input": {"user": "attacker", "path": "/admin"},
    })
    print("  Event 1: deny (high)     -> wird gesendet")

    # Allow-Event -> wird ignoriert (nur deny/error konfiguriert)
    wh_plugin.notify({
        "decision": "allow",
        "path": "authz/allow",
        "message": "Normaler Zugriff erlaubt",
    })
    print("  Event 2: allow           -> wird ignoriert")

    # Deny-Event (low) -> wird ignoriert (min_severity=medium)
    wh_plugin.notify({
        "decision": "deny",
        "path": "log/level",
        "severity": "low",
        "message": "Debug-Zugriff verweigert",
    })
    print("  Event 3: deny (low)      -> wird ignoriert (severity)")

    # Error-Event (critical) -> wird gesendet
    wh_plugin.notify({
        "decision": "error",
        "path": "data/compliance/check",
        "severity": "critical",
        "message": "Policy-Evaluation fehlgeschlagen",
    })
    print("  Event 4: error (critical) -> wird gesendet")

    # Manueller Flush
    print("\n  --- Flush ---")
    await wh_plugin._flush()

    # 4. Verschiedene Formate zeigen
    print("\n  --- Format-Beispiele ---")
    test_events = [{
        "decision": "deny",
        "path": "authz/allow",
        "severity": "high",
        "message": "Zugriff verweigert",
        "timestamp": time.time(),
    }]

    for fmt in ["slack", "teams", "generic"]:
        wh_plugin._config["format"] = fmt
        payload = wh_plugin._format_payload(test_events)
        print(f"\n  Format '{fmt}':")
        print(f"  {json.dumps(payload, indent=4, ensure_ascii=False)}")

    # 5. Status & Stoppen
    print(f"\n  Plugin-Status: {wh_plugin.status()}")
    print(f"  Gesendet: {wh_plugin._sent_count}, Fehler: {wh_plugin._error_count}")

    await manager.stop_all()


if __name__ == "__main__":
    asyncio.run(demo())
