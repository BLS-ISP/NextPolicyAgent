# Next Policy Agent (NPA)

**High-performance, secure policy engine — Python/FastAPI rewrite of Open Policy Agent (OPA)**

[![Python](https://img.shields.io/badge/Python-≥3.12-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue)](LICENSE)
[![OPA Compatible](https://img.shields.io/badge/OPA-kompatibel-orange)](https://www.openpolicyagent.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-blue)](Documentation/Docker-Anleitung.md)
[![CVE-Free](https://img.shields.io/badge/CVE--Scan-0_critical_|_0_high-brightgreen)](https://osv.dev/)
[![pip-audit](https://img.shields.io/badge/pip--audit-verified-brightgreen)](https://github.com/pypa/pip-audit)

---

## Features

- **Rego-kompatible Policy-Sprache** — optimierter Parser und Evaluator, Rego v1 Syntax
- **HTTPS by Default** — TLS 1.2+ als Standard, automatische Zertifikatsgenerierung
- **OPA-kompatible REST-API** — Drop-in-Replacement für `/v1/data`, `/v1/policies`, `/v1/query`
- **Docker-Ready** — Fedora 41 basiertes Container-Image (~300 MB)
- **Web-Dashboard** — integrierte Verwaltungsoberfläche mit Live-Metriken
- **Async-First Architecture** — FastAPI + uvicorn für maximale Performance
- **Multi-Layer Caching** — BaseCache, InterQueryCache, PreparedQueryCache
- **Modulares Plugin-System** — Bundles, Decision Logs, Status, Discovery
- **Dual Storage** — In-Memory (Default) + SQLite (Persistenz)
- **Bundle-System** — Signierung (JWT), Delta-Updates, OCI-Registry
- **Vollständige Observability** — OpenTelemetry, Prometheus, Structured Logging
- **Modern CLI** — Typer-basiert mit Rich-Output
- **Embeddable SDK** — NPA als Library in Python-Anwendungen einbetten

---

## Schnellstart

### Lokal (Python)

```bash
# venv erstellen und aktivieren
python -m venv .venv
.venv\Scripts\activate      # Windows (PowerShell)
source .venv/bin/activate    # Linux/macOS

# Dependencies installieren
pip install -e ".[dev]"
# Oder aus Lockfile (exakte Versionen):
pip install -r requirements.txt && pip install -e .

# Server starten (HTTPS mit Auto-TLS)
npa run

# Mit eigenem Zertifikat
npa run --addr 0.0.0.0:8443 --tls-cert-file cert.pem --tls-private-key-file key.pem

# Ohne TLS (nur Entwicklung)
npa run --no-tls
```

> **Hinweis:** Die Start-Skripte (`start-npa.ps1` / `start-npa.sh`) erkennen das `.venv` automatisch.

### Docker

```bash
# Image bauen und starten
docker build -t npa:latest .
docker run -d -p 8443:8443 --name npa npa:latest

# Oder mit Docker Compose
docker compose up -d
```

### Policy evaluieren

```bash
# Über CLI
npa eval "data.authz.allow" --input input.json --data policy.rego

# Über REST-API
curl -sk -X POST https://localhost:8443/v1/data/authz/allow \
  -H "Content-Type: application/json" \
  -d '{"input": {"role": "admin"}}'
```

### Weitere CLI-Befehle

```bash
npa test ./policies/     # Tests ausführen
npa fmt ./policies/      # Code formatieren
npa check policy.rego    # Syntax prüfen
npa parse policy.rego    # AST anzeigen
npa build -b bundle/     # Bundle erstellen
npa sign bundle.tar.gz   # Bundle signieren
npa version              # Version anzeigen
```

---

## Docker

NPA läuft als Docker-Container auf Basis von **Fedora 41** (~300 MB Image).

```bash
# Schnellstart
docker build -t npa:latest .
docker run -d -p 8443:8443 npa:latest

# Mit Policies und Daten
docker run -d -p 8443:8443 \
  -v ./policies:/policies:ro \
  -v ./data:/data:ro \
  npa:latest

# Health-Check
curl -sk https://localhost:8443/health
```

**Vollständige Anleitung:** [Documentation/Docker-Anleitung.md](Documentation/Docker-Anleitung.md)

### Docker Compose

```bash
docker compose up -d          # Starten
docker compose up -d --build  # Neu bauen + starten
docker compose logs -f npa    # Logs verfolgen
docker compose down           # Stoppen
```

---

## REST-API (OPA-kompatibel)

NPA implementiert die OPA REST-API für direkten Austausch:

| Endpoint | Methode | Beschreibung |
|----------|---------|-------------|
| `/v1/data/{path}` | GET, POST | Daten abfragen / Policy evaluieren |
| `/v1/data/{path}` | PUT, PATCH, DELETE | Daten verwalten |
| `/v1/policies/{id}` | GET, PUT, DELETE | Policies verwalten |
| `/v1/policies` | GET | Alle Policies auflisten |
| `/v1/query` | POST | Ad-hoc Rego-Query ausführen |
| `/v1/compile` | POST | Partial Evaluation |
| `/health` | GET | Health-Check |
| `/` | GET | Web-Dashboard |

### Beispiele

```bash
# Policy hochladen
curl -sk -X PUT https://localhost:8443/v1/policies/authz \
  -H "Content-Type: text/plain" \
  -d 'package authz
default allow = false
allow if { input.role == "admin" }'

# Policy evaluieren
curl -sk -X POST https://localhost:8443/v1/data/authz/allow \
  -H "Content-Type: application/json" \
  -d '{"input": {"role": "admin"}}'
# → {"result": true}

# Daten setzen
curl -sk -X PUT https://localhost:8443/v1/data/users \
  -H "Content-Type: application/json" \
  -d '{"admins": ["alice", "bob"]}'

# Alle Policies auflisten
curl -sk https://localhost:8443/v1/policies
```

---

## Konfiguration

Alle Einstellungen über **Umgebungsvariablen** (Prefix `NPA_`), **Config-Datei** (YAML/JSON) oder **CLI-Flags**.

| Bereich | Variablen | Beschreibung |
|---------|-----------|-------------|
| Server | `NPA_SERVER_ADDR`, `NPA_SERVER_PORT` | Bind-Adresse/Port (Default: `0.0.0.0:8443`) |
| TLS | `NPA_TLS_ENABLED`, `NPA_TLS_CERT_FILE`, `NPA_TLS_KEY_FILE` | HTTPS-Konfiguration |
| Auth | `NPA_AUTH_ENABLED`, `NPA_AUTH_JWT_SECRET`, `NPA_AUTH_UI_PASSWORD` | Authentifizierung |
| Logging | `NPA_LOGGING_LEVEL`, `NPA_LOG_FORMAT` | Log-Level und Format |
| Storage | `NPA_STORAGE_BACKEND`, `NPA_STORAGE_DISK_PATH` | Backend-Auswahl |

Vollständige Referenz: [Documentation/Docker-Anleitung.md – Konfiguration](Documentation/Docker-Anleitung.md#konfiguration)

---

## Policy-Beispiele

6 praxisnahe, OPA-verifizierte Rego-Policies unter [`examples/`](examples/):

| Beispiel | Package | Beschreibung |
|----------|---------|-------------|
| `rbac/` | `rbac.authz` | Rollenbasierte Zugriffskontrolle |
| `http-api-authz/` | `httpapi.authz` | REST-API Endpunktschutz |
| `kubernetes-admission/` | `kubernetes.admission` | K8s Pod-Validierung |
| `network-firewall/` | `network.firewall` | IP/Port Firewall-Regeln |
| `jwt-validation/` | `jwt.validation` | JWT Token-Prüfung |
| `data-filtering/` | `filtering` | Daten-Filterung & Aggregation |

Alle Beispiele sind mit `opa check` validiert und liefern identische Ergebnisse in NPA und OPA.

```bash
# Beispiel lokal
npa eval -d examples/rbac/ -i examples/rbac/input.json "data.rbac.authz"

# Beispiel im Docker-Container
docker exec -it npa python3 -m npa eval \
  -d /examples/rbac/ -i /examples/rbac/input.json "data.rbac.authz"
```

Detaillierte Beschreibung: [examples/README.md](examples/README.md)

---

## Plugin-Beispiele

5 Beispiele unter [`examples/plugins/`](examples/plugins/) demonstrieren das NPA-Plugin-System:

| Beispiel | Beschreibung |
|----------|--------------|
| `audit_trail_plugin.py` | Lokales JSONL Audit-Logging mit Rotation |
| `rate_limit_plugin.py` | Sliding-Window Rate-Limiting pro Client |
| `webhook_notification_plugin.py` | Webhook-Alerts (Slack, Teams, Generic JSON) |
| `metrics_plugin.py` | Prometheus-kompatible Metriken-Sammlung |
| `builtin_config_plugin.py` | Konfiguration der 4 Built-in Plugins + YAML-Template |

```bash
# Plugin-Beispiel ausführen
python -m examples.plugins.audit_trail_plugin
python -m examples.plugins.rate_limit_plugin
python -m examples.plugins.metrics_plugin
```

Detaillierte Beschreibung: [examples/plugins/README.md](examples/plugins/README.md)

---

## Architektur

```
┌──────────────────────────────────────────────────────┐
│                    CLI (Typer)                        │
├──────────────────────────────────────────────────────┤
│              FastAPI Server (HTTPS)                   │
│  ┌──────┐ ┌───────┐ ┌────────┐ ┌─────────────────┐  │
│  │ Data │ │ Query │ │ Policy │ │ Health/Metrics   │  │
│  └──────┘ └───────┘ └────────┘ └─────────────────┘  │
├──────────────────────────────────────────────────────┤
│             Web-Dashboard (HTML/JS)                   │
├──────────────────────────────────────────────────────┤
│                 Plugin Manager                        │
│  ┌────────┐ ┌──────┐ ┌────────┐ ┌───────────────┐   │
│  │ Bundle │ │ Logs │ │ Status │ │   Discovery   │   │
│  └────────┘ └──────┘ └────────┘ └───────────────┘   │
├──────────────────────────────────────────────────────┤
│                  Rego Engine                          │
│  ┌────────┐ ┌──────────┐ ┌────────┐ ┌───────────┐   │
│  │ Parser │→│ Compiler │→│TypeChk │→│ Evaluator │   │
│  └────────┘ └──────────┘ └────────┘ └───────────┘   │
├──────────────────────────────────────────────────────┤
│   Storage (Memory/SQLite)  │   Cache (Multi-Layer)   │
└──────────────────────────────────────────────────────┘
```

## Verbesserungen gegenüber OPA

| Bereich | OPA | NPA |
|---------|-----|-----|
| HTTPS | Optional | **Default (Auto-TLS)** |
| Container | Scratch (Go binary) | **Fedora 41 (~300 MB)** |
| Storage | BadgerDB (instabil) | **SQLite** (bewährt) |
| I/O | Synchron (Go) | **Async** (asyncio) |
| Serialisierung | encoding/json | **orjson** (10x schneller) |
| CLI | cobra | **Typer + Rich** |
| Logging | logrus | **structlog** |
| Config Validation | Manuell | **Pydantic** |
| Rate Limiting | Keins | **Eingebaut** |
| Web UI | Basic Status | **Dashboard mit Live-Metriken** |

---

## Sicherheit & CVE-Status

NPA wird regelmäßig mit [pip-audit](https://github.com/pypa/pip-audit) gegen die [OSV-Datenbank](https://osv.dev/) auf bekannte Sicherheitslücken geprüft.

### Letzter Scan (März 2026)

| Metrik | Ergebnis |
|--------|----------|
| Direkte Abhängigkeiten | 19 Pakete |
| Transitive Abhängigkeiten | 40 Pakete (gesamt) |
| Bekannte CVEs | **0 kritisch, 0 hoch** |
| Status | ✅ **Keine ausnutzbaren Schwachstellen** |

<details>
<summary>Details zum Scan-Ergebnis</summary>

**Alle direkten Abhängigkeiten sind CVE-frei:**

| Paket | Version | Status |
|-------|---------|--------|
| FastAPI | 0.135.1 | ✅ Clean |
| uvicorn | 0.41.0 | ✅ Clean |
| cryptography | ≥46.0.6 | ✅ Clean |
| PyJWT | 2.12.0 | ✅ Clean |
| pydantic | 2.12.5 | ✅ Clean |
| httpx | 0.28.1 | ✅ Clean |
| orjson | 3.11.7 | ✅ Clean |
| aiosqlite | 0.22.1 | ✅ Clean |
| structlog | 25.5.0 | ✅ Clean |
| OpenTelemetry | 1.40.0 | ✅ Clean |
| Starlette | 1.0.0 | ✅ Clean |

**Hinweis:** Pygments (transitive Dep via Rich, CLI-Output) hat einen offenen Low-Severity-CVE (CVE-2026-4539, lokaler ReDoS im AdlLexer). Dieser Lexer wird von NPA nicht verwendet und ist nur mit lokalem Zugriff ausnutzbar.

**Scan reproduzieren:**
```bash
pip install pip-audit
pip-audit -r <(pip freeze | grep -E "fastapi|uvicorn|orjson|cryptography|PyJWT|pydantic|httpx|aiosqlite|typer|rich|structlog|prometheus|opentelemetry|cachetools|xxhash|psutil|pyyaml")
```

</details>

### Sicherheitsmaßnahmen

- **HTTPS by Default** — TLS 1.2+ mit automatischer Zertifikatsgenerierung
- **Dependency Pinning** — Alle Abhängigkeiten mit Mindestversionen gesichert
- **Regelmäßige CVE-Scans** — Automatisierte Prüfung gegen OSV-Datenbank
- **Kein C-Code** — Pure Python, keine nativen Exploits durch Buffer Overflows
- **Pydantic Validation** — Strikte Input-Validierung auf allen API-Endpunkten
- **JWT Authentication** — Optionale API-Absicherung mit Token-basierter Auth
- **Rate Limiting** — Eingebauter Schutz gegen Brute-Force und DoS

---

## Projektstruktur

```
NextPolicyAgent/
├── Dockerfile                    # Multi-Stage Fedora 41 Build
├── docker-compose.yml            # Docker Compose Konfiguration
├── .dockerignore                 # Docker Build-Ausschlüsse
├── pyproject.toml                # Python-Projektdefinition
├── start-npa.ps1 / .sh          # Start-Skripte (Windows/Linux)
├── stop-npa.ps1                  # Stop-Skript (Windows)
├── examples/                     # 6 Policy-Beispiele + 5 Plugin-Beispiele
├── Documentation/                # Anleitungen
│   └── Docker-Anleitung.md      # Vollständige Docker-Anleitung
└── npa/                          # Quellcode
    ├── __init__.py               # Version (1.0.0)
    ├── ast/
    │   ├── types.py              # AST-Knotentypen (frozen dataclasses)
    │   ├── lexer.py              # Rego Tokenizer
    │   ├── parser.py             # Recursive-Descent Parser (Rego v1)
    │   ├── compiler.py           # RuleTree/ModuleTree Compiler
    │   └── builtins.py           # 100+ Built-in-Funktionen
    ├── eval/
    │   ├── topdown.py            # Top-Down Evaluator mit Backtracking
    │   ├── cache.py              # Intra-Query + Inter-Query Cache (LRU/TTL)
    │   ├── partial.py            # Partial Evaluation
    │   └── unify.py              # Unification Engine
    ├── server/
    │   ├── app.py                # FastAPI App Factory (HTTPS-first)
    │   ├── auth.py               # JWT/API-Key Auth Middleware
    │   ├── static/               # Web-Dashboard (HTML/CSS/JS)
    │   └── routes/
    │       ├── data.py           # /v1/data/* (GET/POST/PUT/PATCH/DELETE)
    │       ├── policy.py         # /v1/policies/* (CRUD)
    │       ├── query.py          # /v1/query + /v1/compile
    │       └── health.py         # /health, /health/live, /health/ready
    ├── storage/
    │   ├── base.py               # Abstract Storage + Transaction Interface
    │   ├── inmemory.py           # Thread-safe In-Memory Store
    │   └── disk.py               # SQLite-backed Persistent Store (WAL)
    ├── bundle/
    │   ├── bundle.py             # Bundle Format (.tar.gz), Load/Build
    │   ├── sign.py               # JWT-basierte Bundle-Signierung
    │   └── loader.py             # Async HTTP/Disk Loader mit Polling
    ├── plugins/
    │   └── manager.py            # Plugin Lifecycle + Bundle/Log/Status Plugins
    ├── format/
    │   └── formatter.py          # Rego Code Formatter
    ├── config/
    │   └── config.py             # Pydantic Settings (TLS, Server, Auth, ...)
    ├── sdk/
    │   └── sdk.py                # Embeddable SDK (NPA Klasse)
    └── cli/
        └── main.py               # Typer CLI (run/eval/build/check/parse/sign/inspect)
```

---

## SDK-Nutzung (Embedded)

NPA kann als Library direkt in Python-Anwendungen eingebettet werden:

```python
from npa.sdk.sdk import NPA

engine = NPA()
engine.load_policy("authz.rego", """
    package authz
    default allow = false
    allow if { input.role == "admin" }
""")

result = engine.decide_bool("data.authz.allow", {"role": "admin"})
# True

result = engine.decide("data.authz", {"role": "admin"})
# {"result": [{"allow": True, ...}]}
```

---

## Dokumentation

### Einstieg

| Dokument | Beschreibung |
|----------|-------------|
| [Schnellstart](Documentation/Schnellstart.md) | In 10 Minuten von Installation bis erste Policy |
| [Web-Dashboard](Documentation/Web_Dashboard.md) | Benutzerhandbuch für das integrierte Web-UI (7 Seiten) |
| [CLI-Referenz](Documentation/CLI_Referenz.md) | Alle 13 Kommandozeilen-Befehle im Detail |
| [REST-API-Referenz](Documentation/REST_API_Referenz.md) | Vollständige HTTP-Endpunkt-Dokumentation |
| [Rego-Sprachreferenz](Documentation/Rego_Sprachreferenz.md) | Rego-Syntax und 192+ Built-in Funktionen |
| [SDK-Referenz](Documentation/SDK_Referenz.md) | Python SDK zum Einbetten in eigene Apps |
| [Konfigurationsreferenz](Documentation/Konfigurationsreferenz.md) | Alle Config-Optionen mit Umgebungsvariablen |

### Beispiele & Betrieb

| Dokument | Beschreibung |
|----------|-------------|
| [Docker-Anleitung](Documentation/Docker-Anleitung.md) | Container-Setup, Konfiguration, Produktion |
| [Policy-Beispiele](examples/README.md) | 6 praxisnahe Rego-Policies mit Erklärung |
| [Plugin-Beispiele](examples/plugins/README.md) | 5 Plugin-Beispiele mit Architektur-Übersicht |
| [Performance-Vergleich](Documentation/Performance_Vergleich_OPA_vs_NPA.md) | Benchmark OPA vs. NPA (8 Tests) |

### Hintergrund

| Dokument | Beschreibung |
|----------|-------------|
| [OPA Gap-Analyse](Documentation/OPA_vs_NPA_Gap_Analysis.md) | Kompatibilitätsvergleich NPA vs. OPA |
| [Anforderungsprofil](Documentation/OPA_Analyse_und_Anforderungsprofil.md) | Ursprüngliche Analyse und Designziele |

---

## Lizenz

Dieses Projekt steht unter der **GNU General Public License v3.0** (GPL-3.0).  
Siehe [LICENSE](LICENSE) für den vollständigen Lizenztext.

