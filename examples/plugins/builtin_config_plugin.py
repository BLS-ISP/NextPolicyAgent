"""NPA Plugin-Beispiel 5: Built-in Plugin Konfiguration

Dieses Beispiel zeigt, wie die mitgelieferten NPA-Plugins konfiguriert
und gestartet werden — per Python-Code und per Konfigurationsdatei.

Built-in Plugins:
  1. BundlePlugin     — Lädt Policies und Daten aus Bundle-Quellen
  2. DecisionLogPlugin — Protokolliert Entscheidungen an Remote-Endpoint
  3. StatusPlugin     — Meldet Agent-Status an Steuerungsserver
  4. DiscoveryPlugin  — Lädt Konfiguration dynamisch von einem Endpoint

Dieses Beispiel startet keinen echten Server, sondern zeigt die
Konfigurationsmuster und demonstriert den Lifecycle.
"""

import asyncio
from typing import Any

from npa.plugins.manager import (
    BundlePlugin,
    DecisionLogPlugin,
    StatusPlugin,
    DiscoveryPlugin,
    PluginManager,
    PluginState,
)


# ─────────────────────────────────────────────────────────
# Beispiel 1: BundlePlugin
# ─────────────────────────────────────────────────────────

def bundle_plugin_example() -> dict[str, Any]:
    """Konfiguration für das Bundle-Plugin.

    Das BundlePlugin lädt Rego-Policies und Daten von einem Bundle-Server.
    Es unterstützt Polling, ETag-Caching und mehrere Bundle-Quellen.
    """
    return {
        "bundles": {
            "authz": {
                "url": "https://bundle-server.example.com/bundles/authz",
                "polling_interval": 30,
                "auth_token": "Bearer my-bundle-token",
            },
            "compliance": {
                "url": "https://bundle-server.example.com/bundles/compliance",
                "polling_interval": 120,
                "auth_token": "Bearer my-bundle-token",
            }
        }
    }


# ─────────────────────────────────────────────────────────
# Beispiel 2: DecisionLogPlugin
# ─────────────────────────────────────────────────────────

def decision_log_plugin_example() -> dict[str, Any]:
    """Konfiguration für das Decision-Log-Plugin.

    Das DecisionLogPlugin protokolliert jede Policy-Entscheidung und
    sendet sie periodisch an einen zentralen Log-Collector.
    """
    return {
        "decision_logs": {
            "url": "https://log-collector.example.com/logs",
            "auth_token": "Bearer my-log-token",
            "buffer_size": 100,
            "flush_interval": 5,
            "console": True,  # Zusätzlich auf Konsole ausgeben
        }
    }


# ─────────────────────────────────────────────────────────
# Beispiel 3: StatusPlugin
# ─────────────────────────────────────────────────────────

def status_plugin_example() -> dict[str, Any]:
    """Konfiguration für das Status-Plugin.

    Das StatusPlugin meldet den Health-Status des Agents zurück
    an einen zentralen Steuerungsserver.
    """
    return {
        "status": {
            "url": "https://control-plane.example.com/status",
            "auth_token": "Bearer my-status-token",
            "report_interval": 30,
        }
    }


# ─────────────────────────────────────────────────────────
# Beispiel 4: DiscoveryPlugin
# ─────────────────────────────────────────────────────────

def discovery_plugin_example() -> dict[str, Any]:
    """Konfiguration für das Discovery-Plugin.

    Das DiscoveryPlugin holt dynamisch die Konfiguration der anderen
    Plugins von einem zentralen Endpoint. Damit kann die Konfiguration
    zentral gemanagt werden, ohne Agents neu starten zu müssen.
    """
    return {
        "discovery": {
            "url": "https://control-plane.example.com/config",
            "auth_token": "Bearer my-discovery-token",
            "polling_interval": 60,
        }
    }


# ─────────────────────────────────────────────────────────
# Vollständige Konfigurationsdatei (YAML-Kommentare)
# ─────────────────────────────────────────────────────────

EXAMPLE_YAML_CONFIG = """
# NPA Konfiguration mit allen Built-in Plugins
# Datei: npa.yaml

server:
  addr: "0.0.0.0"
  port: 8443
  workers: 1

tls:
  enabled: true
  cert_file: "/etc/npa/certs/server.crt"
  key_file: "/etc/npa/certs/server.key"

auth:
  enabled: true
  token_type: "bearer"
  jwt_secret: "my-secure-secret-key"

storage:
  backend: "memory"

logging:
  level: "INFO"
  format: "json"
  decision_log: true

# Bundle-Quellen
bundles:
  - name: "authz"
    url: "https://bundle-server.example.com/bundles/authz"
    polling_interval: 30
    auth_token: "Bearer my-token"

  - name: "compliance"
    url: "https://bundle-server.example.com/bundles/compliance"
    polling_interval: 120
    auth_token: "Bearer my-token"

labels:
  environment: "production"
  region: "eu-west-1"
  version: "v1.0.0"
"""


# ─────────────────────────────────────────────────────────
# Demo: Plugin-Lifecycle
# ─────────────────────────────────────────────────────────

async def demo():
    """Demonstriert den Lifecycle der built-in Plugins."""
    print("=" * 60)
    print("NPA Plugin-Beispiel: Built-in Plugin Konfiguration")
    print("=" * 60)

    # 1. PluginManager erstellen
    manager = PluginManager()

    # 2. Plugins registrieren
    print("\n  --- Plugins registrieren ---")

    bundle_config = bundle_plugin_example()
    bundle_plugin = BundlePlugin(config=bundle_config)
    manager.register(bundle_plugin)
    print(f"  + {bundle_plugin.name} registriert")

    log_config = decision_log_plugin_example()
    log_plugin = DecisionLogPlugin(config=log_config)
    manager.register(log_plugin)
    print(f"  + {log_plugin.name} registriert")

    status_config = status_plugin_example()
    status_plugin = StatusPlugin(config=status_config)
    manager.register(status_plugin)
    print(f"  + {status_plugin.name} registriert")

    discovery_config = discovery_plugin_example()
    discovery_plugin = DiscoveryPlugin(config=discovery_config)
    manager.register(discovery_plugin)
    print(f"  + {discovery_plugin.name} registriert")

    # 3. Alle Plugins starten
    print("\n  --- Plugins starten ---")
    await manager.start_all()

    # 4. Status abfragen
    print("\n  --- Plugin-Status ---")
    for name, status in manager.statuses().items():
        state_icon = "+" if status.state == PluginState.OK else "x"
        print(f"  {state_icon} {name}: {status.state.name} — {status.message}")

    # 5. Reconfigure demonstrieren
    print("\n  --- Reconfigure-Beispiel ---")
    new_log_config = {
        "decision_logs": {
            "url": "https://new-collector.example.com/logs",
            "flush_interval": 10,
            "console": False,
        }
    }
    await log_plugin.reconfigure(new_log_config)
    print(f"  + {log_plugin.name} reconfigured")

    # 6. YAML-Konfigurationsbeispiel ausgeben
    print("\n  --- Beispiel YAML-Konfiguration ---")
    for line in EXAMPLE_YAML_CONFIG.strip().split("\n"):
        print(f"  {line}")

    # 7. Alle Plugins stoppen
    print("\n  --- Plugins stoppen ---")
    await manager.stop_all()
    print("  Alle Plugins gestoppt.")


if __name__ == "__main__":
    asyncio.run(demo())
