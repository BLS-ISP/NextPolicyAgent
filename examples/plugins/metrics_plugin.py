"""NPA Plugin-Beispiel 4: Metrics / Prometheus Plugin

Dieses Beispiel zeigt ein Plugin, das Policy-Metriken sammelt und als
Prometheus-kompatible Metriken bereitstellt.

Anwendungsfall:
  - Monitoring von Policy-Entscheidungen
  - Grafana-Dashboards für Policy-Performance
  - SLA-Tracking (Latenz, Fehlerrate)
  - Kapazitätsplanung
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


class MetricsPlugin(Plugin):
    """Sammelt Policy-Metriken im Prometheus-Format.

    Konfiguration:
        metrics:
          path: "/metrics"
          enable_latency_histogram: true
          enable_decision_counter: true
          histogram_buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.5, 1.0]
          labels: ["path", "decision"]
    """

    DEFAULT_BUCKETS = [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._status = PluginStatus()
        self._running = False
        self._start_time: float = 0

        # Counter: {labels_tuple: count}
        self._decision_counter: dict[tuple, int] = defaultdict(int)
        # Histogram: {labels_tuple: list of durations}
        self._latency_samples: dict[tuple, list[float]] = defaultdict(list)
        # Gauge: Aktive Evaluations
        self._active_evaluations = 0
        # Errors
        self._error_counter: dict[str, int] = defaultdict(int)

    @property
    def name(self) -> str:
        return "metrics"

    async def start(self, manager: PluginManager) -> None:
        self._running = True
        self._start_time = time.time()
        self._status = PluginStatus(state=PluginState.OK, message="Metrics collection active")
        print(f"  [Metrics] Active. Endpoint: {self._config.get('path', '/metrics')}")

    async def stop(self) -> None:
        self._running = False
        self._status = PluginStatus(state=PluginState.NOT_READY)
        total = sum(self._decision_counter.values())
        print(f"  [Metrics] Stopped. Total decisions recorded: {total}")

    async def reconfigure(self, config: dict[str, Any]) -> None:
        self._config = config

    def status(self) -> PluginStatus:
        return self._status

    def record_decision(
        self,
        path: str,
        decision: str,
        duration_seconds: float,
        error: str | None = None,
    ) -> None:
        """Zeichnet eine Policy-Entscheidung auf.

        Args:
            path: Policy-Pfad (z.B. "authz/allow")
            decision: Ergebnis ("allow", "deny", "error")
            duration_seconds: Evaluationszeit in Sekunden
            error: Optionale Fehlermeldung
        """
        labels = self._make_labels(path=path, decision=decision)

        if self._config.get("enable_decision_counter", True):
            self._decision_counter[labels] += 1

        if self._config.get("enable_latency_histogram", True):
            self._latency_samples[labels].append(duration_seconds)

        if error:
            self._error_counter[error] += 1

    def _make_labels(self, **kwargs: str) -> tuple:
        """Erstellt ein Label-Tupel aus den konfigurierten Labels."""
        configured = self._config.get("labels", ["path", "decision"])
        return tuple((k, kwargs.get(k, "")) for k in configured)

    def render_prometheus(self) -> str:
        """Rendert alle Metriken im Prometheus-Exposition-Format."""
        lines: list[str] = []
        uptime = time.time() - self._start_time if self._start_time else 0

        # Uptime Gauge
        lines.append("# HELP npa_uptime_seconds NPA uptime in seconds")
        lines.append("# TYPE npa_uptime_seconds gauge")
        lines.append(f"npa_uptime_seconds {uptime:.3f}")
        lines.append("")

        # Decision Counter
        if self._config.get("enable_decision_counter", True):
            lines.append("# HELP npa_decisions_total Total policy decisions")
            lines.append("# TYPE npa_decisions_total counter")
            for labels, count in sorted(self._decision_counter.items()):
                label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                lines.append(f"npa_decisions_total{{{label_str}}} {count}")
            lines.append("")

        # Latency Histogram
        if self._config.get("enable_latency_histogram", True):
            buckets = self._config.get("histogram_buckets", self.DEFAULT_BUCKETS)
            lines.append("# HELP npa_decision_duration_seconds Policy decision latency")
            lines.append("# TYPE npa_decision_duration_seconds histogram")

            for labels, samples in sorted(self._latency_samples.items()):
                label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                prefix = f"npa_decision_duration_seconds{{{label_str}"

                # Bucket-Werte
                for bucket in buckets:
                    count = sum(1 for s in samples if s <= bucket)
                    lines.append(f'{prefix},le="{bucket}"}} {count}')
                lines.append(f'{prefix},le="+Inf"}} {len(samples)}')

                # Sum & Count
                total = sum(samples)
                lines.append(f"npa_decision_duration_seconds_sum{{{label_str}}} {total:.6f}")
                lines.append(f"npa_decision_duration_seconds_count{{{label_str}}} {len(samples)}")
            lines.append("")

        # Error Counter
        if self._error_counter:
            lines.append("# HELP npa_errors_total Total evaluation errors")
            lines.append("# TYPE npa_errors_total counter")
            for error_type, count in sorted(self._error_counter.items()):
                lines.append(f'npa_errors_total{{error="{error_type}"}} {count}')
            lines.append("")

        return "\n".join(lines)

    def get_summary(self) -> dict[str, Any]:
        """Gibt eine Zusammenfassung der Metriken als Dict zurück."""
        total_decisions = sum(self._decision_counter.values())
        all_latencies = [s for samples in self._latency_samples.values() for s in samples]
        avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0

        decisions_by_result: dict[str, int] = defaultdict(int)
        for labels, count in self._decision_counter.items():
            label_dict = dict(labels)
            decisions_by_result[label_dict.get("decision", "unknown")] += count

        return {
            "total_decisions": total_decisions,
            "decisions_by_result": dict(decisions_by_result),
            "avg_latency_ms": avg_latency * 1000,
            "p99_latency_ms": (sorted(all_latencies)[int(len(all_latencies) * 0.99)] * 1000)
            if all_latencies
            else 0,
            "total_errors": sum(self._error_counter.values()),
        }


# ─────────────────────────────────────────────────────────
# Demo
# ─────────────────────────────────────────────────────────

async def demo():
    """Demonstriert das Metrics Plugin."""
    import random

    print("=" * 60)
    print("NPA Plugin-Beispiel: Prometheus Metrics")
    print("=" * 60)

    # 1. Setup
    manager = PluginManager()

    metrics_config = {
        "path": "/metrics",
        "enable_latency_histogram": True,
        "enable_decision_counter": True,
        "histogram_buckets": [0.001, 0.005, 0.01, 0.05, 0.1, 0.5],
        "labels": ["path", "decision"],
    }
    metrics_plugin = MetricsPlugin(config=metrics_config)
    manager.register(metrics_plugin)

    await manager.start_all()

    # 2. Entscheidungen simulieren
    print("\n  --- 100 Policy-Entscheidungen simulieren ---")
    paths = ["authz/allow", "rbac/user_role", "data/filter", "network/egress"]
    decisions = ["allow", "deny"]

    for i in range(100):
        path = random.choice(paths)
        decision = random.choices(decisions, weights=[80, 20])[0]
        # Simulierte Latenz: 1-50ms
        latency = random.uniform(0.001, 0.05)
        error = "timeout" if random.random() < 0.02 else None
        if error:
            decision = "error"
        metrics_plugin.record_decision(path, decision, latency, error)

    # 3. Zusammenfassung
    print("\n  --- Metriken-Zusammenfassung ---")
    summary = metrics_plugin.get_summary()
    for key, value in summary.items():
        if isinstance(value, float):
            print(f"    {key}: {value:.3f}")
        else:
            print(f"    {key}: {value}")

    # 4. Prometheus-Format
    print("\n  --- Prometheus-Exposition-Format ---")
    output = metrics_plugin.render_prometheus()
    # Nur die ersten 30 Zeilen zeigen
    lines = output.split("\n")
    for line in lines[:30]:
        print(f"  {line}")
    if len(lines) > 30:
        print(f"  ... ({len(lines) - 30} weitere Zeilen)")

    # 5. Status & Stoppen
    print(f"\n  Plugin-Status: {metrics_plugin.status()}")
    await manager.stop_all()


if __name__ == "__main__":
    asyncio.run(demo())
