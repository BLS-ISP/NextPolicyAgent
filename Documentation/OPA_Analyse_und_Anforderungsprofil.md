# Open Policy Agent (OPA) — Detaillierte Analyse & Anforderungsprofil

**Erstellt:** 27. März 2026  
**Zweck:** Grundlage für einen vollständigen Rewrite der OPA Policy Engine  
**Quellcode-Version:** OPA v1.x (Go 1.25.0, CNCF Graduated Project)

---

## Inhaltsverzeichnis

1. [Executive Summary](#1-executive-summary)
2. [Architektur-Übersicht](#2-architektur-übersicht)
3. [Detailliertes Feature-Set](#3-detailliertes-feature-set)
   - 3.1 [Rego-Sprach-Engine](#31-rego-sprach-engine)
   - 3.2 [Topdown-Evaluierung](#32-topdown-evaluierung)
   - 3.3 [REST-API / HTTP-Server](#33-rest-api--http-server)
   - 3.4 [Plugin-System](#34-plugin-system)
   - 3.5 [Bundle-System](#35-bundle-system)
   - 3.6 [Storage-System](#36-storage-system)
   - 3.7 [SDK / Embedding API](#37-sdk--embedding-api)
   - 3.8 [CLI / Kommandozeile](#38-cli--kommandozeile)
   - 3.9 [WASM-Kompilierung](#39-wasm-kompilierung)
   - 3.10 [Test-Framework](#310-test-framework)
   - 3.11 [Debugging](#311-debugging)
   - 3.12 [Profiling & Code Coverage](#312-profiling--code-coverage)
   - 3.13 [Formatierung](#313-formatierung)
   - 3.14 [Tracing & Observability](#314-tracing--observability)
   - 3.15 [REPL](#315-repl)
   - 3.16 [Konfigurationssystem](#316-konfigurationssystem)
4. [Built-in-Funktionen (Vollständiger Katalog)](#4-built-in-funktionen-vollständiger-katalog)
5. [Abhängigkeiten & Technologie-Stack](#5-abhängigkeiten--technologie-stack)
6. [Design Patterns & Architektur-Entscheidungen](#6-design-patterns--architektur-entscheidungen)
7. [Vor- und Nachteile der OPA-Architektur](#7-vor--und-nachteile-der-opa-architektur)
8. [Anforderungsprofil für den Rewrite](#8-anforderungsprofil-für-den-rewrite)
9. [Empfehlungen für den Rewrite](#9-empfehlungen-für-den-rewrite)

---

## 1. Executive Summary

OPA ist eine universelle, open-source Policy-Engine (CNCF Graduated), die eine deklarative Sprache namens **Rego** bereitstellt, um Policies über den gesamten Software-Stack hinweg zu definieren und durchzusetzen. OPA entkoppelt Policy-Entscheidungen von der Anwendungslogik und stellt diese über eine REST-API, ein Go-SDK oder als eingebettete Library bereit.

**Kernkomponenten:**
- **Rego Language Engine** — Parser, Compiler, Typ-System
- **Topdown Evaluator** — Policy-Auswertung mittels modifiziertem Datalog
- **REST API Server** — HTTP-basierte Policy-Entscheidungen
- **Plugin-System** — Erweiterbare Architektur (Bundles, Decision Logs, Status, Discovery)
- **Bundle-System** — Verteilung und Signierung von Policies
- **Storage Layer** — In-Memory und Disk-basierte Datenhaltung
- **WASM Compiler** — Kompilierung nach WebAssembly für Edge-Deployment

**Codebasis:** ~30.000+ Zeilen Go-Code über ~25 Module, geschrieben in Go 1.25.0.

---

## 2. Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI / REPL                               │
├─────────────────────────────────────────────────────────────────┤
│                     REST API Server                             │
│  ┌──────────┐  ┌─────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ Data API │  │Query API│  │Policy API│  │ Compile API    │  │
│  └──────────┘  └─────────┘  └──────────┘  └────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                     Plugin Manager                              │
│  ┌────────┐  ┌──────────┐  ┌────────┐  ┌──────────┐          │
│  │ Bundle │  │ Decision │  │ Status │  │Discovery │          │
│  │ Plugin │  │   Logs   │  │ Plugin │  │  Plugin  │          │
│  └────────┘  └──────────┘  └────────┘  └──────────┘          │
├─────────────────────────────────────────────────────────────────┤
│                     Rego Engine                                 │
│  ┌────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ Parser │→ │ Compiler │→ │Type Check│→ │Topdown Evaluator│ │
│  └────────┘  └──────────┘  └──────────┘  └────────────────┘  │
├──────────────────────────────┬──────────────────────────────────┤
│       Storage Layer          │        WASM / IR Compiler       │
│  ┌─────────┐  ┌──────────┐  │  ┌────┐  ┌──────┐  ┌──────┐   │
│  │In-Memory│  │   Disk   │  │  │ IR │→ │ Plan │→ │ WASM │   │
│  │  Store  │  │ (Badger) │  │  └────┘  └──────┘  └──────┘   │
│  └─────────┘  └──────────┘  │                                  │
└──────────────────────────────┴──────────────────────────────────┘
```

**Datenfluss:**
1. Client sendet Policy-Entscheidungsanfrage (HTTP oder Go SDK)
2. Server routet an den Topdown Evaluator
3. Evaluator lädt Rego-Module aus dem Compiler, Daten aus dem Storage
4. Input-Dokument wird gegen die kompilierten Rules evaluiert
5. Ergebnis wird als JSON zurückgegeben

---

## 3. Detailliertes Feature-Set

### 3.1 Rego-Sprach-Engine

#### 3.1.1 Parser
| Eigenschaft | Detail |
|---|---|
| **Typ** | Recursive Descent Parser |
| **Token-System** | Scanner/Token-basiert (intern) |
| **Max. Rekursionstiefe** | 100.000 (konfigurierbar) |
| **Eingabeformate** | Rego, JSON, YAML |
| **Rego-Versionen** | RegoV0, RegoV1, RegoV0CompatV1 |
| **Lazy Loading** | Ja, für große Bundles |
| **Fehlerbehandlung** | Akkumulierend (max 10 Fehler Standard) |

#### 3.1.2 AST (Abstract Syntax Tree)
```
Module
├── Package (Reference)
├── Imports (Pfade zu externen Daten)
├── Annotations (Metadaten, Schemas)
└── Rules
    ├── Head (Name, Key, Value, Assign)
    ├── Body (Expressions/Queries)
    └── Else-Clauses
```

**Term-Typen:**
- Primitive: `Null`, `Boolean`, `Number` (big.Float), `String`
- Komplexe: `Object`, `Array`, `Set`
- Variablen: `Var`, `Ref` (Referenzen auf verschachtelte Daten)
- Comprehensions: Array/Set/Object Comprehensions
- Calls: Funktionsaufrufe
- Every: Universeller Quantor

**Interning:** Automatische Deduplizierung häufiger Terms via xxHash v2 für Speichereffizienz.

#### 3.1.3 Compiler Pipeline
| Phase | Beschreibung |
|---|---|
| 1. Parsing | Quelltext → AST |
| 2. Module Processing | Imports auflösen, Package-Struktur |
| 3. Rule Indexing | ModuleTree, RuleTree aufbauen |
| 4. Safety Analysis | Ungebundene Variablen, Zirkelreferenzen |
| 5. Type Checking | Schema-basierte Typrüfung |
| 6. Comprehension Indexing | Optimierung von Comprehensions |
| 7. Graph Analysis | Dependency-Auflösung |

**Compiler Output:** `ModuleTree` + `RuleTree` für effizientes Querying.

#### 3.1.4 Typ-System
- Typen: `Null`, `Boolean`, `Number`, `String`, `Array`, `Object`, `Set`, `Function`, `Any`
- **Capabilities-System:** Definiert verfügbare Built-ins pro OPA-Version
- **JSON-Schema-Integration:** Schema-basierte Input-Validierung
- **Netzwerk-Policies:** `AllowNet` kontrolliert erlaubte Netzwerkzugriffe

#### 3.1.5 Rego-Versionen & Kompatibilität
| Version | Merkmale |
|---|---|
| **RegoV0** | Legacy-Syntax, implizite Regeln |
| **RegoV1** | `if`/`contains` Pflicht in Rule Heads, `future.keywords` Standard, strikte Checks |
| **RegoV0CompatV1** | Übergangs-Modus, akzeptiert beides |

Migrationsunterstützung via `rego.v1` und `future.keywords` Imports.

---

### 3.2 Topdown-Evaluierung

#### 3.2.1 Evaluierungsstrategie
| Eigenschaft | Detail |
|---|---|
| **Algorithmus** | Modifizierter Top-Down Datalog-Evaluator |
| **Referenz-Evaluation** | Eager (sofortige Auflösung) |
| **Term-Evaluation** | Lazy |
| **Comprehensions** | Eager mit optionalem Indexing |
| **Partial Evaluation** | Ja — erlaubt Pre-Compilation von Teilergebnissen |

#### 3.2.2 Query-System
```go
type Query struct {
    compiler    *ast.Compiler
    store       storage.Store
    input       *ast.Term
    unknowns    []*ast.Term     // Für Partial Evaluation
    tracers     []QueryTracer
    metrics     metrics.Metrics
    indexing    IndexingMode
    earlyExit  bool
}
```

**Output:** `QueryResultSet` = Liste von Variable → Value Mappings.

#### 3.2.3 Cache-Hierarchie
| Cache-Typ | Scope | Zweck |
|---|---|---|
| **BaseCache** | Innerhalb einer Query | Lokale Zwischen-Ergebnisse |
| **NDBuiltinCache** | Innerhalb einer Query | Non-deterministische Built-ins (z.B. regex) |
| **InterQueryCache** | Zwischen Queries | Geteilter Cache mit TTL |
| **InterQueryValueCache** | Zwischen Queries | Große Werte (z.B. HTTP-Antworten) |

#### 3.2.4 Unifikation & Pattern Matching
- Vollständiges Unification-System
- Variable Substitution
- Ground-Checks (Prüfung auf Variable-freie Terme)
- Copy Propagation (Optimierung)

---

### 3.3 REST-API / HTTP-Server

#### 3.3.1 API-Endpunkte
| Endpunkt | Methoden | Beschreibung |
|---|---|---|
| `/health` | GET | Liveness/Readiness Probe |
| `/v1/data/{path}` | GET, POST, PUT, DELETE, PATCH | Daten-API (lesen, schreiben, patchen) |
| `/v1/query` | POST | Ad-hoc Query-Auswertung |
| `/v1/policies` | GET, PUT, DELETE | Policy-Management (CRUD) |
| `/v1/compile` | POST | Partial Evaluation / Compilation |
| `/v1/config` | GET, PUT | Dynamische Konfiguration zur Laufzeit |
| `/v1/status` | GET | Plugin-Status |
| `/v0/data/{path}` | GET, POST, PUT, DELETE, PATCH | Legacy-API |
| `/metrics` | GET | Prometheus Metriken |

#### 3.3.2 Authentifizierung
| Schema | Beschreibung |
|---|---|
| `Off` | Keine Authentifizierung |
| `Token` | Bearer Token |
| `TLS` | mTLS / Client Zertifikate |

#### 3.3.3 Autorisierung
| Schema | Beschreibung |
|---|---|
| `Off` | Keine Autorisierung |
| `Basic` | ACL via Rego Policies (OPA autorisiert sich selbst) |

#### 3.3.4 Server-Features
- **TLS** mit Hot-Reload für Zertifikate
- **HTTP/2** Support
- **GZIP-Komprimierung**
- **Decision ID Tracking** (eindeutige Request-IDs)
- **Prepared Query Cache** (LRU, max 100 Einträge)
- **Prometheus Metrics** nativ integriert
- **Encoding-Plugins** (JSON, YAML)

---

### 3.4 Plugin-System

#### 3.4.1 Plugin-Architektur
```go
type Factory interface {
    Validate(manager *Manager, config []byte) (any, error)
    New(manager *Manager, config any) Plugin
}

type Plugin interface {
    Start(ctx context.Context) error
    Stop(ctx context.Context) error
    Reconfigure(ctx context.Context, config any) error
}
```

#### 3.4.2 Integrierte Plugins
| Plugin | Beschreibung |
|---|---|
| **Bundle** | Automatischer Download und Update von Policy/Daten-Bundles |
| **Decision Logs** | Logging aller Policy-Entscheidungen an einen konfigurierten Service |
| **Status** | Regelmäßige Status-Reports an einen konfigurierten Service |
| **Discovery** | Dynamisches Laden der OPA-Konfiguration von einem Service |

#### 3.4.3 Plugin-Lebenszyklus
| Status | Bedeutung |
|---|---|
| `NotReady` | Initialisierung |
| `OK` | Läuft |
| `Ready` | Bereit für Entscheidungen |
| `Warn` | Degradierter Betrieb |
| `Error` | Fataler Fehler |

**Plugin Manager:**
- Zentrales Orchestrierungssystem
- Dependency-Management zwischen Plugins
- Konfigurationsvalidierung und -injektion
- Status-Updates via `UpdatePluginStatus`

---

### 3.5 Bundle-System

#### 3.5.1 Bundle-Struktur
```
bundle.tar.gz/
├── .manifest          # Metadaten: Revision, Roots, Builtins
├── .signatures.json   # Optional: JWT-basierte Signaturen
├── data.json          # Basisdokumente (oder data.yaml)
├── *.rego             # Rego Policy-Module
├── policy.wasm        # Optional: Vorkompilierte WASM-Policies
├── plan.json          # Optional: Query-Pläne
└── patch.json         # Optional: Delta-Operationen
```

#### 3.5.2 Bundle-Typen
| Typ | Beschreibung |
|---|---|
| **Snapshot Bundle** | Vollständiger Policy + Data Set |
| **Delta Bundle** | Inkrementelle Updates via JSON Patch (RFC 6902) |

#### 3.5.3 Signierung & Verifikation
- **JWS/JWT-basiert** mit konfigurierbaren Signing Keys
- **Digest-Algorithmen:** SHA-256 (Standard)
- Automatische Verifikation beim Laden
- Extensible via `SignaturesConfig`

#### 3.5.4 Manifest
```go
type Manifest struct {
    Revision string            // Versionskontrolle
    Roots    []string          // Policy-Namensraum-Roots
    Builtins []string          // Benötigte Built-ins
    Metadata map[string]any    // Benutzerdefinierte Metadaten
}
```

#### 3.5.5 Bundle-Download
- HTTP-basierter Download mit Polling-Intervall
- Unterstützung für OCI-Registry (via `oras.land/oras-go`)
- Long Polling optional
- E-Tag-basierte Caching-Strategie
- Retry mit Backoff

---

### 3.6 Storage-System

#### 3.6.1 Storage-Interface
```go
type Store interface {
    NewTransaction(ctx, params) (Transaction, error)
    Read(ctx, txn, path) (any, error)
    Write(ctx, txn, op, path, value) error
    Commit(ctx, txn) error
    Abort(ctx, txn)
    Truncate(ctx, txn, params, iterator) error
}
```

#### 3.6.2 In-Memory Store
| Eigenschaft | Detail |
|---|---|
| **Implementierung** | Default-Storage |
| **Konsistenz** | Multi-Reader / Single-Writer |
| **Isolierung** | Snapshot Isolation via Transaction IDs |
| **Kopien** | Keine — Data wird shared für Performance |
| **Rollback** | Vollständig unterstützt |

#### 3.6.3 Disk Store (BadgerDB)
| Eigenschaft | Detail |
|---|---|
| **Backend** | BadgerDB v4 (dgraph-io) |
| **Partitionierung** | Konfigurierbares Splitting des `/data`-Namespace |
| **Wildcards** | `/foo/*` für Pattern-basiertes Splitting |
| **Schema** | `/<schema_v>/<partition_v>/<type>` |
| **Objekte** | Implizite Hierarchie-Erstellung |

#### 3.6.4 Trigger-System
- Change Notifications auf Policy/Data Events
- Register/Unregister Pattern für Event Listener
- Wird von der Runtime genutzt um auf Änderungen zu reagieren

---

### 3.7 SDK / Embedding API

#### 3.7.1 High-Level Go SDK
```go
opa, err := sdk.New(ctx, sdk.Options{
    Config: configBytes,
    Store:  customStore,
    Logger: customLogger,
    Hooks:  customHooks,
})

result, err := opa.Decision(ctx, sdk.DecisionOptions{
    Path:  "authz/allow",
    Input: inputMap,
})
```

#### 3.7.2 Low-Level Rego API
```go
r := rego.New(
    rego.Query("data.authz.allow"),
    rego.Module("policy.rego", policySource),
    rego.Input(inputData),
)
rs, err := r.Eval(ctx)
```

#### 3.7.3 Partial Evaluation API
```go
r := rego.New(
    rego.Query("data.authz.allow"),
    rego.Unknowns([]string{"input"}),
)
pq, err := r.Partial(ctx)
// pq enthält vereinfachte Queries
```

---

### 3.8 CLI / Kommandozeile

| Befehl | Beschreibung |
|---|---|
| `opa run` | Startet OPA als Server oder REPL |
| `opa eval` | Ad-hoc Evaluation einer Query |
| `opa build` | Bundle-Kompilierung mit Optimierung |
| `opa test` | Rego-Test-Ausführung |
| `opa fmt` | Rego-Code-Formatierung |
| `opa check` | Statische Analyse (Typen, Safety) |
| `opa parse` | AST-Inspektion (Debugging) |
| `opa sign` | Bundle-Signierung |
| `opa inspect` | Bundle-Inhalte anzeigen |
| `opa deps` | Abhängigkeitsanalyse |
| `opa version` | Versionsinformationen |
| `opa capabilities` | Verfügbare Features/Built-ins listen |

**Globale Flags:** Profiling Output, Metriken, Tracing, Custom Data/Bundles, Output-Formate (JSON, Table, Pretty, Source, Raw).

---

### 3.9 WASM-Kompilierung

#### 3.9.1 Compilation Targets
| Target | Output | Use Case |
|---|---|---|
| `rego` | Optimierter Rego-Code | Standard |
| `wasm` | WebAssembly Binary | High-Performance Edge |
| `plan` | Query Plan (JSON) | Weitere Transpilierung |

#### 3.9.2 IR (Intermediate Representation)
```
Policy → Plans → Funcs → Blocks → Stmts
```
- **Lokale Variablen:** Input (0), Data (1), Unused (2)
- Imperatives Statement-Modell
- Statisches Datensegment

#### 3.9.3 WASM-Features
- Reproduzierbare Builds (Docker)
- Debug-Symbol-Support
- Inline Built-ins
- String Processing, Array/Object Manipulation, Regex im WASM

---

### 3.10 Test-Framework

| Feature | Detail |
|---|---|
| **Namenskonvention** | `test_*` für Tests, `skip_test_*` für übersprungene |
| **Discovery** | Dateibasierte automatische Erkennung |
| **Filter** | Regex-basiert |
| **Benchmarking** | Count, Time Limit, Memory Limit |
| **Ergebnis-Tracking** | Pass / Fail / Skip / Error |
| **Integration** | `opa test` CLI-Befehl |

---

### 3.11 Debugging

| Feature | Detail |
|---|---|
| **Status** | EXPERIMENTELL |
| **Architektur** | DAP-inspiriert (Debug Adapter Protocol) |
| **Breakpoints** | Ja |
| **Step Execution** | Ja |
| **Variable Inspection** | Ja |
| **Call Stack** | Ja |
| **Modi** | Eval-Debugging, Test-Debugging |

---

### 3.12 Profiling & Code Coverage

#### Profiling
```go
type ExprStats struct {
    Location  *ast.Location
    Count     int64
    Duration  time.Duration
}
```
- Expression-Level Profiling
- Aggregation über mehrere Runs
- Integration in CLI (`--profile`)

#### Code Coverage
- Tracking welche Rego-Zeilen evaluiert wurden
- Threshold-Enforcement (Mindest-Coverage)
- Report-Generierung
- Integration: `opa test --coverage`

---

### 3.13 Formatierung

```go
func Source(filename string, src []byte) ([]byte, error)
```
- AST-basierte Formatierung
- Comment Preservation
- Rego-Version-Targeting (V0 → V1 Migration)
- Location Preservation
- Integration: `opa fmt`

---

### 3.14 Tracing & Observability

#### Distributed Tracing
- **OpenTelemetry** Integration
- OTLP Export (gRPC und HTTP)
- Span-Emission für HTTP-Handler und Queries
- Custom Header Propagation

#### Metriken
| Metrik | Beschreibung |
|---|---|
| `bundle_request` | Bundle-Download-Zeiten |
| `server_handler` | HTTP-Handler-Dauer |
| `server_query_cache_hit` | Cache-Hit-Rate |
| `rego_query_eval` | Query-Auswertungszeit |
| `rego_module_compile` | Kompilierungszeit |
| `rego_partial_eval` | Partial-Evaluation-Zeit |

**Prometheus:** Nativer Exporter auf `/metrics`.

#### Decision Logging
- Alle Policy-Entscheidungen werden geloggt
- Konfigurierbare Log-Level und Felder
- Remote Shipping an konfigurierte Services

---

### 3.15 REPL

| Feature | Detail |
|---|---|
| **History** | Persistente Eingabehistorie |
| **Multi-line** | Mehrzeilige Queries |
| **Commands** | `:help`, `:exit`, etc. |
| **Output** | JSON, Pretty-Print |
| **State** | Module Imports, Data Binding |

---

### 3.16 Konfigurationssystem

```yaml
services:
  bundle_service:
    url: https://policy.example.com
    credentials:
      bearer:
        token: "secret"

labels:
  app: myapp
  env: production

bundles:
  app:
    service: bundle_service
    resource: /bundles/my-app
    polling:
      min_delay_seconds: 10
      max_delay_seconds: 120

decision_logs:
  service: log_service

status:
  service: status_service

discovery:
  name: config
  service: config_service

storage:
  disk:
    directory: /var/opa/data
    auto_create: true
    partitions:
      - /users/*
      - /tenants/*
```

**Features:**
- YAML-basierte Konfiguration
- Dynamische Rekonfiguration zur Laufzeit
- Discovery-Plugin für Remote-Config
- Service-Definitionen mit Auth (Bearer, mTLS, OAuth2)
- Label-System für Instanz-Identifikation

---

## 4. Built-in-Funktionen (Vollständiger Katalog)

### 4.1 Vergleich & Logik
`equal`, `not_equal`, `lt`, `lte`, `gt`, `gte`, `and`, `or`

### 4.2 Arithmetik
`plus`, `minus`, `mul`, `div`, `rem`, `abs`, `ceil`, `floor`, `round`, `pow`, `sqrt`

### 4.3 Bitweise Operationen
`bits.and`, `bits.or`, `bits.xor`, `bits.negate`, `bits.lsh`, `bits.rsh`

### 4.4 Aggregate
`count`, `sum`, `product`, `max`, `min`, `any`, `all`, `sort`

### 4.5 Arrays
`array.concat`, `array.slice`, `array.reverse`

### 4.6 Sets
`and` (Intersection), `or` (Union), `minus` (Difference)

### 4.7 Strings
`concat`, `contains`, `startswith`, `endswith`, `lower`, `upper`, `split`, `join`, `trim`, `trim_left`, `trim_right`, `trim_prefix`, `trim_suffix`, `trim_space`, `replace`, `indexof`, `indexof_n`, `substring`, `sprintf`, `format_int`, `strings.reverse`, `strings.any_prefix_match`, `strings.any_suffix_match`, `strings.count`, `strings.render_template`

### 4.8 Regex
`regex.match`, `regex.is_valid`, `regex.split`, `regex.find_n`, `regex.find_all_string_submatch_n`, `regex.globs_match`, `regex.template_match`

### 4.9 Objekte
`object.get`, `object.keys`, `object.values`, `object.union`, `object.union_n`, `object.remove`, `object.filter`, `object.subset`

### 4.10 Type Checks
`is_null`, `is_boolean`, `is_number`, `is_string`, `is_array`, `is_set`, `is_object`, `type_name`

### 4.11 Encoding / Decoding
`base64.encode`, `base64.decode`, `base64url.encode`, `base64url.decode`, `json.marshal`, `json.unmarshal`, `json.is_valid`, `json.filter`, `json.remove`, `json.patch`, `yaml.marshal`, `yaml.unmarshal`, `yaml.is_valid`, `urlquery.encode`, `urlquery.decode`, `urlquery.encode_object`, `hex.encode`, `hex.decode`

### 4.12 Kryptographie
`crypto.sha256`, `crypto.md5`, `crypto.sha1`, `crypto.hmac.sha256`, `crypto.hmac.sha512`, `crypto.x509.parse_certificates`, `crypto.x509.parse_certificate_request`, `crypto.x509.parse_rsa_private_key`, `crypto.x509.parse_keypair`, `crypto.parse_private_keys`

### 4.13 Token & Signaturen
`io.jwt.encode_sign`, `io.jwt.encode_sign_raw`, `io.jwt.decode`, `io.jwt.decode_verify`, `io.jwt.verify_rs256`, `io.jwt.verify_rs384`, `io.jwt.verify_rs512`, `io.jwt.verify_ps256`, `io.jwt.verify_ps384`, `io.jwt.verify_ps512`, `io.jwt.verify_es256`, `io.jwt.verify_es384`, `io.jwt.verify_es512`, `io.jwt.verify_hs256`, `io.jwt.verify_hs384`, `io.jwt.verify_hs512`

### 4.14 HTTP
`http.send` — Vollständiger HTTP-Client mit TLS, Auth, Caching, Timeouts

### 4.15 Zeit
`time.now_ns`, `time.parse_ns`, `time.parse_rfc3339_ns`, `time.parse_duration_ns`, `time.date`, `time.clock`, `time.weekday`, `time.add_date`, `time.diff`, `time.format`

### 4.16 Netzwerk
`net.cidr_contains`, `net.cidr_contains_matches`, `net.cidr_intersects`, `net.cidr_merge`, `net.cidr_expand`, `net.cidr_is_valid`, `net.lookup_ip_addr`

### 4.17 Rego-Meta
`rego.metadata.chain`, `rego.metadata.rule`, `rego.parse_module`

### 4.18 OPA-Intern
`opa.runtime` — Laufzeitinformationen (Version, Config, etc.)

### 4.19 GraphQL
`graphql.is_valid`, `graphql.parse`, `graphql.schema_is_valid`

### 4.20 Sonstiges
`uuid.rfc4122`, `uuid.parse`, `semver.is_valid`, `semver.compare`, `glob.match`, `glob.quote_meta`, `print`, `trace`, `walk`, `numbers.range`, `numbers.range_step`

---

## 5. Abhängigkeiten & Technologie-Stack

### 5.1 Direkte Abhängigkeiten (Kern)
| Bibliothek | Zweck | Kritikalität |
|---|---|---|
| `wasmtime-go/v39` | WASM-Runtime | Hoch (WASM-Feature) |
| `badger/v4` (dgraph-io) | Embedded Key-Value Store | Hoch (Disk-Storage) |
| `prometheus/client_golang` | Prometheus Metrics | Mittel |
| `cobra` (spf13) | CLI Framework | Mittel |
| `viper` (spf13) | Konfigurationsmanagement | Mittel |
| `lestrrat-go/jwx/v3` | JWT/JWS Signierung & Verifikation | Hoch (Bundle-Signing) |
| `golang.org/x/net` | HTTP/2, Netzwerk | Hoch |
| `go.opentelemetry.io/*` | OpenTelemetry Tracing | Mittel |
| `sirupsen/logrus` | Structured Logging | Niedrig |
| `gobwas/glob` | Glob Pattern Matching | Niedrig |
| `hashicorp/golang-lru/v2` | LRU Cache | Niedrig |
| `xxhash/v2` | Schnelles Hashing (Interning) | Niedrig |
| `containerd/containerd/v2` | Container/OCI Integration | Mittel |
| `oras-go/v2` | OCI Registry Support | Mittel |
| `gqlparser/v2` | GraphQL Parsing | Niedrig |
| `go-sqlbuilder` | SQL Query Building Built-in | Niedrig |
| `peterh/liner` | REPL Line Editing | Niedrig |
| `fsnotify` | Dateisystem-Überwachung | Niedrig |

### 5.2 Indirekte Abhängigkeiten (Auswahl)
| Bibliothek | Zweck |
|---|---|
| `flatbuffers` | Serialisierung (BadgerDB intern) |
| `klauspost/compress` | Komprimierung |
| `secp256k1` | Kryptographische Kurven |
| `go-mockdns` | DNS-Mocking für Tests |
| `automaxprocs` | CPU-Erkennung in Containern |
| `lumberjack` | Log-Rotation |

### 5.3 Go-Version & Build
- **Go 1.25.0**
- **Build:** Makefile-basiert
- **Container:** Dockerfile vorhanden
- **Plattformen:** Linux, macOS, Windows (mit `main_windows.go`)

---

## 6. Design Patterns & Architektur-Entscheidungen

### 6.1 Patterns
| Pattern | Einsatz | Beschreibung |
|---|---|---|
| **Builder** | `rego.New()`, Query | Fluent API für komplexe Konfiguration |
| **Factory** | Plugin-System | `Factory.New()` erstellt Plugin-Instanzen |
| **Strategy** | Storage | In-Memory vs. Disk austauschbar |
| **Visitor** | AST | `visit.Walk()` für Baum-Traversierung |
| **Observer** | Trigger-System | Event Listener für Datenänderungen |
| **Decorator** | Hooks, Middleware | Config-Manipulation, HTTP-Handler-Kette |
| **Middleware** | Server-Handler | Auth, Compression, Logging, Metrics |
| **Iterator** | Built-in Functions | `BuiltinFunc` produziert Ergebnisse via Iterator |

### 6.2 Concurrency-Modell
- **Multi-Reader / Single-Writer** im Storage Layer
- **Thread-Safe Metrics** via Atomic Operations
- **Goroutine-basiertes** Plugin Management
- **Signal Handling** für Graceful Shutdown (SIGTERM, SIGINT)
- **Context-basierte** Cancellation durchgängig

### 6.3 Performance-Optimierungen
| Optimierung | Beschreibung |
|---|---|
| **Interning** | String/Value-Deduplizierung via Hash |
| **Multi-Layer Caching** | BaseCache → NDBuiltinCache → InterQueryCache |
| **Rule/Module Indexing** | Tree-basierte Strukturen für schnelles Lookup |
| **Lazy Evaluation** | Terms lazy, Refs/Comprehensions eager |
| **LRU Cache** | Prepared Queries (max 100) |
| **Sync Pools** | Objekt-Wiederverwendung |
| **Copy Propagation** | Eliminierung unnötiger Kopien in Queries |

### 6.4 Error Handling
| Error-Typ | Kontext |
|---|---|
| `CompileError` | Statische Analyse-Fehler |
| `EvalError` | Laufzeit-Evaluierungsfehler |
| `StorageError` | Datenzugriffsprobleme |
| `BundleError` | Ungültiges Bundle-Format |
| `AuthError` | Authentifizierung/Autorisierung |

Error-Akkumulation: Bis zu 10 Fehler vor Abbruch (konfigurierbar).

---

## 7. Vor- und Nachteile der OPA-Architektur

### 7.1 Vorteile

| # | Vorteil | Beschreibung |
|---|---|---|
| V1 | **CNCF Graduated** | Reifes, bewährtes Projekt mit breiter Industrie-Adoptierung |
| V2 | **Universelle Policy Engine** | Nicht an ein spezifisches Ökosystem gebunden — einsetzbar für K8s, Terraform, APIs, Microservices |
| V3 | **Deklarative Sprache (Rego)** | Policies als Code, versionierbar, testbar, wiederverwendbar |
| V4 | **Plugin-Architektur** | Erweiterbar ohne Kernänderungen — neue Plugins für Bundles, Logs, Status |
| V5 | **Partial Evaluation** | Policies können vorkompiliert werden → schnellere Laufzeit-Entscheidungen |
| V6 | **WASM-Support** | Edge-Deployment ohne vollständige OPA-Instanz, hohe Performance |
| V7 | **Bundle-System** | Skalierbare Policy-Verteilung mit Signierung, Delta-Updates und OCI-Registry |
| V8 | **Eingebettetes Testing** | First-Class Testing direkt in der Rego-Sprache (`test_*`) |
| V9 | **Umfangreiche Built-ins** | 100+ eingebaute Funktionen für Crypto, HTTP, JWT, Time, Regex, etc. |
| V10 | **Dual-Mode** | Server-Modus (Daemon) und Library-Modus (Go SDK) |
| V11 | **Observability** | OpenTelemetry, Prometheus, Decision Logs — Enterprise-ready |
| V12 | **Schema-Validierung** | JSON-Schema-basierte Input-Typrüfung |
| V13 | **Transaktionales Storage** | ACID-ähnliche Garantien im Storage Layer |
| V14 | **Performante Evaluierung** | Multi-Layer Caching, Interning, indexierte Rule Trees |
| V15 | **Dynamische Konfiguration** | Discovery-Plugin ermöglicht Runtime-Konfigurationsänderungen |

### 7.2 Nachteile

| # | Nachteil | Beschreibung | Schwere |
|---|---|---|---|
| N1 | **Lernkurve von Rego** | Rego ist eine eigene Sprache — Entwickler müssen sie erlernen, Datalog-Semantik ist ungewohnt | Hoch |
| N2 | **Single Language (Go)** | Nur Go als Implementierungssprache → SDKs für andere Sprachen nur via REST oder WASM | Mittel |
| N3 | **Gewachsene Codebasis** | v0 zu v1 Migration-Ballast, Deprecation-Schichten, doppelte Module (top-level + v1/) | Hoch |
| N4 | **BadgerDB als Disk-Store** | BadgerDB hatte historisch Stabilitätsprobleme, hoher Memory-Footprint, GC-Druck | Mittel |
| N5 | **WASM-Einschränkungen** | Nicht alle Built-ins in WASM verfügbar, wasmtime-go bindet an C-Runtime | Mittel |
| N6 | **Keine native horizontale Skalierung** | Jede OPA-Instanz ist standalone — kein eingebautes Clustering oder Konsensus | Mittel |
| N7 | **Debugging nur experimentell** | DAP-inspiriertes Debugging ist noch nicht produktionsreif | Niedrig |
| N8 | **Schwere Dependencies** | wasmtime-go, BadgerDB, containerd, etc. erhöhen Binary-Größe und Build-Komplexität | Mittel |
| N9 | **Kein nativer Event-Stream** | Keine WebSocket/SSE-API für Live-Updates von Policy-Entscheidungen | Niedrig |
| N10 | **Monolithische Architektur** | Alle Features in einem Binary — schwer einzelne Komponenten zu isolieren oder auszuwechseln | Mittel |
| N11 | **Rego-Versions-Fragmentierung** | Drei Rego-Versionen (V0, V1, V0CompatV1) erzeugen Komplexität in Parser und Compiler | Mittel |
| N12 | **Limited Query Optimization** | Kein vollständiger Query Planner wie in Datenbanken — Topdown kann bei komplexen Policies langsam sein | Mittel |
| N13 | **Single-Writer Storage** | Nur ein Writer gleichzeitig → Bottleneck bei hohen Schreiblasten | Niedrig |
| N14 | **Keine native Policy-Versionierung** | Bundles haben Revision, aber kein eingebautes Rollback oder A/B-Testing | Niedrig |
| N15 | **HTTP-basiertes Bundle-Polling** | Push-basierte Verteilung nicht nativ, nur Polling mit Long-Poll-Option | Niedrig |

---

## 8. Anforderungsprofil für den Rewrite

### 8.1 Funktionale Anforderungen (MUST HAVE)

#### F-CORE: Policy-Sprache & Evaluation
| ID | Anforderung | Priorität |
|---|---|---|
| F-CORE-01 | Deklarative Policy-Sprache (Rego-kompatibel oder verbessert) | P0 |
| F-CORE-02 | Recursive Descent Parser mit konfigurierbarer Tiefe | P0 |
| F-CORE-03 | AST-Repräsentation (Module, Rules, Bodies, Terms) | P0 |
| F-CORE-04 | Compiler Pipeline (Parse → Compile → Type Check → Optimize) | P0 |
| F-CORE-05 | Top-Down Evaluation mit Unifikation | P0 |
| F-CORE-06 | Partial Evaluation für Pre-Compilation | P1 |
| F-CORE-07 | Mindestens 100 Built-in-Funktionen (siehe Katalog Sektion 4) | P0 |
| F-CORE-08 | Typ-System mit Schema-Validierung (JSON Schema) | P1 |
| F-CORE-09 | Comprehensions (Array, Set, Object) | P0 |
| F-CORE-10 | Every-Quantor (universeller Quantor) | P1 |

#### F-API: Server & REST-API
| ID | Anforderung | Priorität |
|---|---|---|
| F-API-01 | REST API für Policy-Entscheidungen (`/v1/data/`) | P0 |
| F-API-02 | Policy-Management-API (CRUD) | P0 |
| F-API-03 | Query-API für Ad-hoc-Evaluierung | P0 |
| F-API-04 | Compile-API für Partial Evaluation | P1 |
| F-API-05 | Health-Endpoint | P0 |
| F-API-06 | Prometheus Metrics Endpoint | P1 |
| F-API-07 | TLS Support mit Certificate Hot-Reload | P1 |
| F-API-08 | HTTP/2 Support | P2 |
| F-API-09 | Authentifizierung (Token, mTLS) | P1 |
| F-API-10 | Autorisierung via eigene Policies | P1 |
| F-API-11 | GZIP-Komprimierung | P2 |
| F-API-12 | Decision ID Tracking | P1 |

#### F-BUNDLE: Bundle-System
| ID | Anforderung | Priorität |
|---|---|---|
| F-BUNDLE-01 | Bundle-Format (tar.gz mit Manifest, Policies, Data) | P0 |
| F-BUNDLE-02 | Snapshot Bundles (vollständiger Policy-Set) | P0 |
| F-BUNDLE-03 | Delta Bundles (inkrementelle Updates) | P1 |
| F-BUNDLE-04 | Bundle-Signierung (JWT/JWS) | P1 |
| F-BUNDLE-05 | Bundle-Verifikation beim Laden | P1 |
| F-BUNDLE-06 | HTTP-basierter Download mit Polling | P0 |
| F-BUNDLE-07 | OCI-Registry Support | P2 |
| F-BUNDLE-08 | E-Tag Caching | P2 |

#### F-STORAGE: Datenhaltung
| ID | Anforderung | Priorität |
|---|---|---|
| F-STORAGE-01 | In-Memory Storage (Default) | P0 |
| F-STORAGE-02 | Transaktionen (Read/Write, Commit, Abort) | P0 |
| F-STORAGE-03 | Multi-Reader / Single-Writer | P0 |
| F-STORAGE-04 | Disk-basierte Persistenz | P1 |
| F-STORAGE-05 | Trigger/Event-System für Datenänderungen | P1 |
| F-STORAGE-06 | Konfigurierbares Partitionierung | P2 |

#### F-PLUGIN: Plugin-System
| ID | Anforderung | Priorität |
|---|---|---|
| F-PLUGIN-01 | Plugin-Architektur (Factory + Lifecycle) | P0 |
| F-PLUGIN-02 | Bundle Plugin | P0 |
| F-PLUGIN-03 | Decision Logs Plugin | P1 |
| F-PLUGIN-04 | Status Plugin | P1 |
| F-PLUGIN-05 | Discovery Plugin (Remote Config) | P2 |
| F-PLUGIN-06 | Custom Plugin Registration | P1 |
| F-PLUGIN-07 | Plugin Status Tracking & Reporting | P1 |

#### F-CLI: Kommandozeile
| ID | Anforderung | Priorität |
|---|---|---|
| F-CLI-01 | `run` (Server / REPL) | P0 |
| F-CLI-02 | `eval` (Query-Auswertung) | P0 |
| F-CLI-03 | `build` (Bundle-Erstellung) | P0 |
| F-CLI-04 | `test` (Test-Ausführung) | P0 |
| F-CLI-05 | `fmt` (Code-Formatierung) | P1 |
| F-CLI-06 | `check` (Statische Analyse) | P1 |
| F-CLI-07 | `parse` (AST-Inspektion) | P2 |
| F-CLI-08 | `sign` (Bundle-Signierung) | P2 |
| F-CLI-09 | `inspect` (Bundle-Inspektion) | P2 |
| F-CLI-10 | `deps` (Dependency-Analyse) | P2 |

#### F-TEST: Test-Framework
| ID | Anforderung | Priorität |
|---|---|---|
| F-TEST-01 | Rego-native Tests (`test_*` Konvention) | P0 |
| F-TEST-02 | Test-Discovery und -Filter | P0 |
| F-TEST-03 | Benchmarking | P1 |
| F-TEST-04 | Code Coverage Reporting | P1 |
| F-TEST-05 | Coverage Threshold Enforcement | P2 |

### 8.2 Funktionale Anforderungen (SHOULD HAVE)

#### F-WASM: WebAssembly
| ID | Anforderung | Priorität |
|---|---|---|
| F-WASM-01 | WASM-Compilation Target | P2 |
| F-WASM-02 | Intermediate Representation (IR) | P2 |
| F-WASM-03 | Query Plan Generation | P2 |

#### F-OBS: Observability
| ID | Anforderung | Priorität |
|---|---|---|
| F-OBS-01 | OpenTelemetry Integration | P2 |
| F-OBS-02 | Prometheus Metrics | P1 |
| F-OBS-03 | Strukturiertes Logging | P0 |
| F-OBS-04 | Profiling (Expression-Level) | P2 |
| F-OBS-05 | Decision Logging | P1 |

#### F-DEBUG: Debugging
| ID | Anforderung | Priorität |
|---|---|---|
| F-DEBUG-01 | DAP-kompatibles Debugging | P2 |
| F-DEBUG-02 | Breakpoints & Step Execution | P2 |
| F-DEBUG-03 | Variable Inspection | P2 |

#### F-SDK: Embedding
| ID | Anforderung | Priorität |
|---|---|---|
| F-SDK-01 | High-Level SDK (einfache Integration) | P0 |
| F-SDK-02 | Low-Level Rego API | P1 |
| F-SDK-03 | Partial Evaluation API | P1 |

#### F-MISC: Sonstiges
| ID | Anforderung | Priorität |
|---|---|---|
| F-MISC-01 | REPL (interaktive Shell) | P2 |
| F-MISC-02 | Rego-Code-Formatierung | P1 |
| F-MISC-03 | Capability-Versioning | P1 |

### 8.3 Nicht-funktionale Anforderungen

| ID | Kategorie | Anforderung | Priorität |
|---|---|---|---|
| NF-01 | **Performance** | Query-Evaluierung < 1ms für typische Policies | P0 |
| NF-02 | **Performance** | Multi-Layer Caching (mindestens BaseCache + InterQueryCache) | P1 |
| NF-03 | **Performance** | Interning für häufige Terme | P1 |
| NF-04 | **Skalierbarkeit** | Tausende Policies gleichzeitig laden | P0 |
| NF-05 | **Skalierbarkeit** | Tausende Requests/Sekunde bei Policy-Entscheidungen | P0 |
| NF-06 | **Verfügbarkeit** | Graceful Shutdown mit Signal Handling | P0 |
| NF-07 | **Sicherheit** | TLS/mTLS für alle Netzwerkkommunikation | P1 |
| NF-08 | **Sicherheit** | Bundle-Signierung & Verifikation | P1 |
| NF-09 | **Sicherheit** | Input-Validierung | P0 |
| NF-10 | **Portabilität** | Linux, macOS, Windows Support | P0 |
| NF-11 | **Portabilität** | Container-Image (Docker) | P0 |
| NF-12 | **Wartbarkeit** | Modularer Aufbau — Komponenten austauschbar | P0 |
| NF-13 | **Wartbarkeit** | Klare API-Grenzen zwischen Modulen | P0 |
| NF-14 | **Erweiterbarkeit** | Custom Built-in Registration | P1 |
| NF-15 | **Erweiterbarkeit** | Custom Storage Backends | P1 |
| NF-16 | **Kompatibilität** | Rego V1 Kompatibilität (Mindestanforderung) | P0 |
| NF-17 | **Dokumentation** | API-Dokumentation für alle öffentlichen Interfaces | P1 |

---

## 9. Empfehlungen für den Rewrite

### 9.1 Architektur-Empfehlungen

| # | Empfehlung | Begründung |
|---|---|---|
| E1 | **Modulare Micro-Kernel-Architektur** | OPA ist monolithisch — ein modularer Ansatz erlaubt Feature-Isolation und unabhängige Skalierung |
| E2 | **Interface-First Design** | Klare Interfaces zwischen Parser, Compiler, Evaluator, Storage — erleichtert Austausch |
| E3 | **Kein Legacy-Ballast** | Nur RegoV1 unterstützen, keine V0-Kompatibilitätsschichten |
| E4 | **Besseres Storage-Backend** | Alternativen zu BadgerDB evaluieren (SQLite, Pebble, oder Custom) |
| E5 | **Event-basierte Architektur** | WebSocket/SSE für Push-basierte Entscheidungen und Live-Updates |
| E6 | **Query Planner** | Vollständiger Query Optimizer wie in Datenbanken für bessere Performance |
| E7 | **Multi-Writer Storage** | MVCC statt Single-Writer für bessere Concurrent-Write-Performance |
| E8 | **Native SDK-Generierung** | SDKs für multiple Sprachen via Code-Generierung (nicht nur Go) |
| E9 | **Horizontale Skalierung** | Eingebautes Clustering oder Leader-Follower für High-Availability |
| E10 | **Policy-Versionierung** | Eingebautes Rollback, A/B-Testing, Canary Deployments |

### 9.2 Technologie-Empfehlungen

| Bereich | OPA aktuell | Empfehlung für Rewrite |
|---|---|---|
| Sprache | Go | Je nach Anforderung: Go (Performance), Rust (Safety + WASM), oder Hybrid |
| CLI Framework | cobra/viper | Moderne Alternative je nach Zielsprache |
| Logging | logrus | Structured Logging (slog in Go, tracing in Rust) |
| Metriken | prometheus/client | OpenTelemetry Metrics (vereinheitlicht mit Tracing) |
| Storage | BadgerDB | SQLite/Pebble/Custom je nach Anforderungen |
| WASM | wasmtime-go | wasmtime oder wasmer, je nach Plattformstrategie |
| Serialisierung | encoding/json | High-Performance JSON (sonic, simd-json) |

### 9.3 Priorisierte Implementierungsreihenfolge

| Phase | Module | Begründung |
|---|---|---|
| **Phase 1** | Parser, AST, Compiler, Typ-System | Kern-Fundamentals — alles andere baut darauf auf |
| **Phase 2** | Topdown Evaluator, Built-ins (Kern) | Ermöglicht erste Policy-Evaluierung |
| **Phase 3** | In-Memory Storage, SDK | Einbettbar in Anwendungen |
| **Phase 4** | REST API Server, CLI (`run`, `eval`) | Standalone-Betrieb möglich |
| **Phase 5** | Bundle-System, Plugin-System | Verteilung und Erweiterbarkeit |
| **Phase 6** | Test-Framework, Formatierung | Entwickler-Experience |
| **Phase 7** | Decision Logs, Status, Discovery | Enterprise-Features |
| **Phase 8** | WASM, Debugging, Profiling | Advanced Features |
| **Phase 9** | REPL, OCI Registry, Advanced Caching | Nice-to-have |

---

*Dieses Dokument dient als Grundlage für die Planung und Umsetzung des NPA (Next Policy Agent) Rewrites. Alle Anforderungen basieren auf der Analyse des OPA-Quellcodes (Commit-Stand März 2026).*
