# Next Policy Agent (NPA)

**High-performance, secure policy engine — Python/FastAPI rewrite of Open Policy Agent (OPA)**

## Features

- **Rego-kompatible Policy-Sprache** mit optimiertem Parser und Evaluator
- **HTTPS by Default** — TLS 1.2+ als Standard, nicht optional
- **Async-First Architecture** — FastAPI + uvicorn für maximale Performance
- **Multi-Layer Caching** — BaseCache, InterQueryCache, PreparedQueryCache
- **Modulares Plugin-System** — Bundles, Decision Logs, Status, Discovery
- **Dual Storage** — In-Memory (Default) + SQLite (Persistenz, statt BadgerDB)
- **Bundle-System** — Signierung (JWT), Delta-Updates, OCI-Registry
- **Vollständige Observability** — OpenTelemetry, Prometheus, Structured Logging
- **Modern CLI** — Typer-basiert mit Rich-Output

## Schnellstart

```bash
# Installation
pip install -e ".[dev]"

# Server starten (HTTPS)
npa run --addr :8443 --tls-cert cert.pem --tls-key key.pem

# Policy evaluieren
npa eval "data.authz.allow" --input input.json --data policy.rego

# Tests ausführen
npa test ./policies/

# Code formatieren
npa fmt ./policies/
```

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
| HTTPS | Optional | **Default** |
| Storage | BadgerDB (instabil) | **SQLite** (bewährt) |
| I/O | Synchron (Go) | **Async** (asyncio) |
| Serialisierung | encoding/json | **orjson** (10x schneller) |
| CLI | cobra | **Typer + Rich** |
| Logging | logrus | **structlog** |
| Config Validation | Manuell | **Pydantic** |
| Rate Limiting | Keins | **Eingebaut** |
| CORS | Manuell | **Middleware** |

## Projektstruktur

```
npa/
├── __init__.py               # Version
├── ast/
│   ├── types.py              # AST-Knotentypen (frozen dataclasses)
│   ├── lexer.py              # Rego Tokenizer
│   ├── parser.py             # Recursive-Descent Parser
│   ├── compiler.py           # RuleTree/ModuleTree Compiler
│   └── builtins.py           # 100+ Built-in-Funktionen
├── eval/
│   ├── topdown.py            # Top-Down Evaluator mit Backtracking
│   ├── cache.py              # Intra-Query + Inter-Query Cache (LRU/TTL)
│   └── unify.py              # Unification Engine
├── server/
│   ├── app.py                # FastAPI App Factory (HTTPS-first)
│   ├── auth.py               # JWT/API-Key Auth Middleware
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
├── config/
│   └── config.py             # Pydantic Settings (TLS, Server, Auth, ...)
├── sdk/
│   └── sdk.py                # Embeddable SDK (NPA Klasse)
└── cli/
    └── main.py               # Typer CLI (run/eval/build/check/parse/sign/inspect)
```

## SDK-Nutzung (Embedded)

```python
from npa.sdk.sdk import NPA

engine = NPA()
engine.load_policy("authz.rego", """
    package authz
    default allow = false
    allow { input.role == "admin" }
""")

result = engine.decide_bool("data.authz.allow", {"role": "admin"})
# True
```

