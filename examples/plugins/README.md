# NPA Plugin-Beispiele

Dieses Verzeichnis enthält Beispiele für das NPA-Plugin-System. NPA unterstützt
ein modulares Plugin-Framework, mit dem Funktionalität zur Laufzeit erweitert
werden kann — ohne den Kern-Code zu ändern.

## Plugin-Architektur

Jedes Plugin implementiert die abstrakte Basisklasse `Plugin`:

```python
from npa.plugins.manager import Plugin, PluginManager, PluginStatus, PluginState

class MeinPlugin(Plugin):
    @property
    def name(self) -> str:
        return "mein_plugin"

    async def start(self, manager: PluginManager) -> None:
        """Wird beim Start des Agent aufgerufen."""
        ...

    async def stop(self) -> None:
        """Wird beim Stoppen des Agent aufgerufen."""
        ...

    async def reconfigure(self, config: dict) -> None:
        """Wird bei Konfigurationsänderungen aufgerufen."""
        ...

    def status(self) -> PluginStatus:
        """Gibt den aktuellen Status des Plugins zurück."""
        return PluginStatus(state=PluginState.OK, message="Aktiv")
```

## Übersicht der Beispiele

| # | Datei | Beschreibung |
|---|-------|-------------|
| 1 | `audit_trail_plugin.py` | Lokales Audit-Logging im JSONL-Format mit Rotation |
| 2 | `rate_limit_plugin.py` | Sliding-Window Rate-Limiting pro Client |
| 3 | `webhook_notification_plugin.py` | Webhook-Benachrichtigungen (Slack, Teams, Generic) |
| 4 | `metrics_plugin.py` | Prometheus-kompatible Metriken-Sammlung |
| 5 | `builtin_config_plugin.py` | Konfigurationsbeispiele für alle Built-in Plugins |

## Custom Plugins (1–4)

### 1. Audit Trail Plugin
Schreibt jede Policy-Entscheidung als JSON-Line in eine lokale Datei.
Unterstützt Log-Rotation, periodisches Flushing und konfigurierbare Felder.

```bash
python -m examples.plugins.audit_trail_plugin
```

### 2. Rate Limit Plugin
Begrenzt Anfragen pro Client mit einem Sliding-Window-Algorithmus.
Unterstützt separate Limits pro Sekunde und pro Minute.

```bash
python -m examples.plugins.rate_limit_plugin
```

### 3. Webhook Notification Plugin
Sendet Alerts bei bestimmten Policy-Entscheidungen per Webhook.
Unterstützt Slack, Microsoft Teams und generisches JSON-Format.

```bash
python -m examples.plugins.webhook_notification_plugin
```

### 4. Metrics Plugin
Sammelt Policy-Metriken (Counter, Histogramme, Gauges) und gibt sie
im Prometheus-Exposition-Format aus.

```bash
python -m examples.plugins.metrics_plugin
```

## Built-in Plugins (5)

### 5. Built-in Plugin Konfiguration
Zeigt die Konfiguration und den Lifecycle der vier mitgelieferten Plugins:

- **BundlePlugin** — Lädt Policies/Daten von Bundle-Servern
- **DecisionLogPlugin** — Sendet Entscheidungs-Logs an Remote-Endpoint
- **StatusPlugin** — Meldet Agent-Status an Steuerungsserver
- **DiscoveryPlugin** — Holt Konfiguration dynamisch von zentralem Endpoint

```bash
python -m examples.plugins.builtin_config_plugin
```

## Plugin registrieren

```python
from npa.plugins.manager import PluginManager
from examples.plugins.rate_limit_plugin import RateLimitPlugin

manager = PluginManager()

plugin = RateLimitPlugin(config={
    "max_requests_per_minute": 100,
    "max_requests_per_second": 20,
})
manager.register(plugin)

await manager.start_all()
```

## Plugin-Status

Jedes Plugin meldet seinen Status über `PluginState`:

| State | Bedeutung |
|-------|-----------|
| `NOT_READY` | Plugin noch nicht gestartet oder gestoppt |
| `OK` | Plugin läuft normal |
| `ERROR` | Plugin hat einen Fehler |

```python
statuses = manager.statuses()
for name, status in statuses.items():
    print(f"{name}: {status.state.name} — {status.message}")
```
