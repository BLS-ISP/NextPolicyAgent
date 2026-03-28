# OPA vs NPA — Vollständige Gap-Analyse

> Erstellt am 27. März 2026 durch Quellcode-Inspektion beider Codebases.

**Bewertungsskala:**
- 🔴 **Critical** — Kernfunktionalität, ohne die OPA-Kompatibilität bricht
- 🟡 **Important** — Produktionsfeature, das in realen Deployments erwartet wird
- 🟢 **Nice-to-have** — Hilfreich, aber nicht für grundlegende Kompatibilität nötig

---

## 1. REST API Vollständigkeit

### Was OPA hat (v1/server/server.go, Zeilen 882–910)

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| POST | `/v0/data/{path}` | v0 Data API (Legacy) |
| GET | `/v1/data/{path}` | Daten lesen / Policy evaluieren |
| POST | `/v1/data/{path}` | Policy mit Input evaluieren |
| PUT | `/v1/data/{path}` | Dokument schreiben |
| PATCH | `/v1/data/{path}` | JSON Patch |
| DELETE | `/v1/data/{path}` | Dokument löschen |
| GET | `/v1/policies` | Alle Policies auflisten |
| GET | `/v1/policies/{id}` | Policy abrufen |
| PUT | `/v1/policies/{id}` | Policy erstellen/aktualisieren |
| DELETE | `/v1/policies/{id}` | Policy löschen |
| GET | `/v1/query` | Ad-hoc Query (GET) |
| POST | `/v1/query` | Ad-hoc Query (POST) |
| POST | `/v1/compile` | Partial Evaluation / Compile |
| POST/GET | `/v1/compile/{path}` | Compile mit Filtern |
| GET | `/v1/config` | Konfiguration abrufen |
| GET | `/v1/status` | Status abrufen |
| GET | `/health` | Health Check |
| GET | `/health/{path}` | Health mit Policy-Evaluation |
| POST | `/` (root) | Query ohne Versionsprefix |
| GET | `/` (root) | Index |

### Was NPA hat (server/routes/*.py)

| Methode | Pfad | Status |
|---------|------|--------|
| GET | `/v1/data/{path}` | ✅ Implementiert |
| POST | `/v1/data/{path}` | ✅ Implementiert |
| PUT | `/v1/data/{path}` | ✅ Implementiert |
| PATCH | `/v1/data/{path}` | ✅ Implementiert (via json.patch) |
| DELETE | `/v1/data/{path}` | ✅ Implementiert |
| GET | `/v1/policies` | ✅ Implementiert |
| GET | `/v1/policies/{id}` | ✅ Implementiert |
| PUT | `/v1/policies/{id}` | ✅ Implementiert |
| DELETE | `/v1/policies/{id}` | ✅ Implementiert |
| GET | `/v1/query` | ✅ Implementiert |
| POST | `/v1/query` | ✅ Implementiert |
| POST | `/v1/compile` | ⚠️ Stub — gibt nur volles Evaluierungsergebnis zurück, keine echte Partial Evaluation |
| GET | `/v1/config` | ✅ Implementiert |
| GET | `/v1/status` | ✅ Implementiert |
| GET | `/health` | ✅ Implementiert |
| GET | `/health/live` | ✅ Implementiert |
| GET | `/health/ready` | ✅ Implementiert |
| GET | `/metrics` | ✅ Implementiert (Prometheus-Format) |
| * | `/v1/ui/*` | ✅ NPA-eigenes Web-Dashboard |

### Fehlend

| Feature | Bewertung |
|---------|-----------|
| **`POST /v0/data/{path}` (v0 API)** — Legacy-Clients nutzen v0 | 🟡 Important |
| **`POST+GET /v1/compile/{path}` (Compile mit Filtern)** — OPA's Partial Eval mit Path-Filtern | 🟡 Important |
| **`/v1/compile` echte Partial Evaluation** — Derzeit nur Full Eval, keine echten teilausgewerteten Queries zurück | 🔴 Critical |
| **`GET /health/{path}` mit Policy-Evaluation** — OPA evaluiert `system.health`-Policies | 🟢 Nice-to-have |
| **`POST /` (root)** — Query ohne Versionsprefix | 🟢 Nice-to-have |
| **Response-Format `decision_id` bei Policies-API** — OPA gibt AST im Policy-Response zurück | 🟢 Nice-to-have |
| **Query-Parameter `explain`, `instrument`** — OPA unterstützt Debugging-Parameter | 🟡 Important |

---

## 2. Rego-Sprachfeatures

### Parser (ast/lexer.py + ast/parser.py + ast/types.py)

| Feature | OPA | NPA | Status |
|---------|-----|-----|--------|
| Package-Deklaration | ✅ | ✅ | ✅ |
| Import-Statements | ✅ | ✅ | ✅ |
| Import mit `as` Alias | ✅ | ✅ | ✅ |
| `import future.keywords` | ✅ | ✅ (Lexer erkennt `if`, `contains`, `in`, `every`) | ✅ |
| `import rego.v1` | ✅ | ✅ (Parser ignoriert sicher) | ⚠️ Nicht explizit enforced |
| Complete Rules | ✅ | ✅ | ✅ |
| Default Rules | ✅ | ✅ | ✅ |
| Else-Chains | ✅ | ✅ | ✅ |
| Partial Set Rules | ✅ | ✅ | ✅ |
| Partial Object Rules | ✅ | ✅ | ✅ |
| Functions (mit Args) | ✅ | ✅ | ✅ |
| `not` Negation | ✅ | ✅ | ✅ |
| `with` Modifier | ✅ | ✅ | ✅ |
| `some` Keyword | ✅ | ✅ (mit `in`) | ✅ |
| `every` Keyword | ✅ | ✅ | ✅ |
| `in` Operator | ✅ | ✅ | ✅ |
| `if` Keyword | ✅ | ✅ | ✅ |
| `contains` Keyword | ✅ | ✅ | ✅ |
| Unification (`=`) | ✅ | ✅ | ✅ |
| Assignment (`:=`) | ✅ | ✅ | ✅ |
| Comparison (`==`, `!=`, `<`, `>`, `<=`, `>=`) | ✅ | ✅ | ✅ |
| Arithmetik (`+`, `-`, `*`, `/`, `%`) | ✅ | ✅ | ✅ |
| Set/And (`&`), Or (`\|`) | ✅ | ✅ | ✅ |
| Array Comprehensions `[x \| ...]` | ✅ | ✅ | ✅ |
| Set Comprehensions `{x \| ...}` | ✅ | ✅ | ✅ |
| Object Comprehensions `{k: v \| ...}` | ✅ | ✅ | ✅ |
| Metadata Annotations (`# METADATA`) | ✅ | ✅ (title, description, scope, schemas, entrypoint, custom) | ✅ |
| Raw Strings `` `...` `` | ✅ | ✅ (RAW_STRING Token) | ✅ |
| Ref Head Rules (v0.46+) | ✅ | ❓ Nicht bestätigt | 🟡 Important |

### Evaluator (eval/topdown.py)

| Feature | OPA | NPA | Status |
|---------|-----|-----|--------|
| Top-down Evaluation | ✅ | ✅ | ✅ |
| Backtracking | ✅ | ✅ (`_iter_body` mit Generator) | ✅ |
| Unification | ✅ | ✅ (`eval/unify.py`) | ✅ |
| With-Modifier Evaluation | ✅ | ✅ (input-Modifikation) | ⚠️ Nur `input.`-Pfade; `data.`-Override fehlt |
| `some x in coll` Iteration | ✅ | ✅ (`internal.member_2/3` Erkennung) | ✅ |
| `every` Evaluation | ✅ | ✅ | ✅ |
| Else-Chain Evaluation | ✅ | ✅ | ✅ |
| Default-Rule Fallback | ✅ | ✅ | ✅ |
| User-defined Functions | ✅ | ✅ (Package-relative + absolute Suche) | ✅ |
| Comprehension Evaluation | ✅ | ✅ | ✅ |
| `rego.metadata.rule` | ✅ | ✅ | ✅ |
| `rego.metadata.chain` | ✅ | ✅ | ✅ |
| Intra-Query Cache | ✅ | ✅ | ✅ |
| Inter-Query Cache | ✅ | ✅ (TTL-basiertes LRU in eval/cache.py) | ✅ |
| Max Depth Protection | ✅ | ✅ (default 1000) | ✅ |
| Trace/Instrumentation | ✅ | ⚠️ Flag vorhanden, kaum genutzt | 🟡 Important |

### Fehlend im Parser/Evaluator

| Feature | Bewertung |
|---------|-----------|
| **`with` auf `data.`-Pfade** — OPA erlaubt `x with data.foo as bar` | 🔴 Critical |
| **Partial Evaluation Engine** — Echte PE mit Unknowns-Propagation für Compile-API | 🔴 Critical |
| **Rule Indexing** — OPA indiziert Rules nach erstem Argument für O(1)-Lookup | 🟡 Important |
| **Comprehension Indexing** — OPA cached Comprehension-Ergebnisse | 🟡 Important |
| **Ref Head Rules** (`a.b.c.d := ...`) — OPA v0.46+ erlaubt Dots in Rule-Heads | 🟡 Important |
| **`rego.v1` Enforcement** — Strict-Modus wenn `import rego.v1` aktiv | 🟢 Nice-to-have |
| **Explain/Instrumentation** — Evaluation-Trace für Debugging | 🟡 Important |

---

## 3. Builtin-Funktionen

NPA hat **192+ registrierte Builtins** (gezählt via `@register_builtin`).  
OPA hat ca. **170 Builtins** im `DefaultBuiltins`-Array.

### Vergleich nach Kategorie

| Kategorie | OPA | NPA | Status |
|-----------|-----|-----|--------|
| **Comparison** (equal, neq, lt, lte, gt, gte) | ✅ | ✅ | ✅ |
| **Arithmetic** (plus, minus, mul, div, rem, abs, ceil, floor, round) | ✅ | ✅ | ✅ |
| **Bitwise** (and, or, xor, negate, lsh, rsh) | ✅ | ✅ | ✅ |
| **Aggregates** (count, sum, product, max, min, any, all, sort) | ✅ | ✅ | ✅ |
| **Arrays** (concat, flatten, slice, reverse) | ✅ | ✅ | ✅ |
| **Sets** (set_diff, intersection, union, and, or) | ✅ | ✅ | ✅ |
| **Strings** (alle 25+ String-Builtins) | ✅ | ✅ (contains, startswith, endswith, lower, upper, split, replace, replace_n, trim*, indexof, indexof_n, substring, sprintf, reverse, count, any_prefix_match, any_suffix_match, render_template) | ✅ |
| **Regex** (match, is_valid, split, find_n, find_all_string_submatch_n, replace, template_match, globs_match) | ✅ | ✅ | ✅ |
| **Object** (get, keys, values, union, union_n, remove, filter, subset) | ✅ | ✅ | ✅ |
| **Type checks** (is_null, is_boolean, is_number, is_string, is_array, is_set, is_object, type_name) | ✅ | ✅ | ✅ |
| **Encoding: JSON** (marshal, unmarshal, is_valid, filter, remove, patch, marshal_with_options) | ✅ | ✅ | ✅ |
| **Encoding: YAML** (marshal, unmarshal, is_valid) | ✅ | ✅ | ✅ |
| **Encoding: Base64** (encode, decode, is_valid, url.encode, url.decode, url.encode_no_pad) | ✅ | ✅ | ✅ |
| **Encoding: Hex** (encode, decode) | ✅ | ✅ | ✅ |
| **Encoding: URL** (encode, decode, encode_object, decode_object) | ✅ | ✅ | ✅ |
| **JSON Schema** (json.verify_schema, json.match_schema) | ✅ | ✅ | ✅ |
| **Crypto: Hash** (sha256, md5, sha1, sha512) | ✅ | ✅ | ✅ |
| **Crypto: HMAC** (md5, sha1, sha256, sha512, equal) | ✅ | ✅ | ✅ |
| **Crypto: x509** (parse_certificates, parse_and_verify, parse_certificate_request, parse_keypair, parse_rsa_private_key, parse_private_keys) | ✅ | ✅ | ✅ |
| **Time** (now_ns, parse_ns, parse_rfc3339_ns, parse_duration_ns, date, clock, weekday, add_date, diff, format) | ✅ | ✅ | ✅ |
| **Net/CIDR** (cidr_contains, cidr_intersects, cidr_is_valid, cidr_expand, cidr_merge, cidr_contains_matches, cidr_overlap, lookup_ip_addr) | ✅ | ✅ | ✅ |
| **UUID** (rfc4122, parse) | ✅ | ✅ | ✅ |
| **SemVer** (is_valid, compare) | ✅ | ✅ | ✅ |
| **Glob** (match, quote_meta) | ✅ | ✅ | ✅ |
| **Units** (parse, parse_bytes) | ✅ | ✅ | ✅ |
| **Graph** (reachable, reachable_paths) | ✅ | ✅ | ✅ |
| **Walk** | ✅ | ✅ | ✅ |
| **Conversions** (to_number, format_int) | ✅ | ✅ | ✅ |
| **Internal** (member_2, member_3, print) | ✅ | ✅ | ✅ |
| **Rego** (parse_module, metadata.rule, metadata.chain) | ✅ | ✅ | ✅ |
| **HTTP** (http.send) | ✅ | ✅ | ✅ |
| **JWT** (decode, decode_verify, encode_sign, encode_sign_raw) | ✅ | ✅ | ✅ |
| **GraphQL** (is_valid, parse, parse_and_verify, parse_query, parse_schema, schema_is_valid) | ✅ | ✅ | ✅ |
| **OPA** (opa.runtime) | ✅ | ✅ | ✅ |
| **Print/Trace** | ✅ | ✅ | ✅ |
| **Deprecated Casts** (cast_array, cast_set, cast_string, cast_boolean, cast_null, cast_object, re_match) | ✅ | ✅ | ✅ |
| **rand.intn** | ✅ | ✅ | ✅ |
| **numbers.range / numbers.range_step** | ✅ | ✅ | ✅ |

### Fehlende Builtins

| Builtin | OPA | NPA | Bewertung |
|---------|-----|-----|-----------|
| `crypto.x509.parse_and_verify_certificates_with_options` | ✅ | ❌ | 🟢 Nice-to-have |
| `providers.aws.sign_req_obj` | ✅ | ❌ | 🟢 Nice-to-have |
| `internal.test_case` | ✅ | ❌ | 🟢 Nice-to-have (nur Test-Tooling) |
| `io.jwt.verify_*` (RS256/384/512, PS256/384/512, ES256/384/512, EdDSA, HS256/384/512 — 13 separate Verifier) | ✅ | ❌ (nur `decode_verify`, keine einzelnen `verify_*`) | 🟡 Important |

**Fazit Builtins:** NPA deckt ~98% der OPA-Builtins ab. Die Abdeckung ist beeindruckend — fast alle OPA-Builtins sind vorhanden, inklusive exotischer wie GraphQL und x509. Die fehlenden JWT-Einzelverifier sind der größte Gap.

---

## 4. Bundle-System

| Feature | OPA | NPA | Status |
|---------|-----|-----|--------|
| Bundle laden (tar.gz) | ✅ | ✅ (`bundle/bundle.py`) | ✅ |
| Bundle laden (Verzeichnis) | ✅ | ✅ | ✅ |
| Bundle bauen | ✅ | ✅ (`build_bundle()`) | ✅ |
| Manifest (.manifest) | ✅ | ✅ (revision, roots, metadata) | ✅ |
| Bundle-Signierung (JWT) | ✅ | ✅ (`bundle/sign.py`) | ✅ |
| Bundle-Verifikation | ✅ | ✅ (`verify_bundle()`) | ✅ |
| .signatures.json | ✅ | ✅ (gelesen beim Laden) | ✅ |
| Content Hash (SHA-256) | ✅ | ✅ | ✅ |
| data.json + data.yaml | ✅ | ✅ | ✅ |
| HTTP(S) Bundle Polling | ✅ | ✅ (`bundle/loader.py` mit httpx, ETag, Polling) | ✅ |
| Path Traversal Schutz | ✅ | ✅ (`..` wird gefiltert) | ✅ |
| **Delta Bundles** | ✅ | ❌ | 🟡 Important |
| **Multi-Bundle Support** | ✅ | ⚠️ Config erlaubt `bundles: list`, Loader behandelt einzeln | 🟡 Important |
| **Bundle Discovery Service** | ✅ | ❌ (nur statische URL-Config) | 🟡 Important |
| **Wasm-Module in Bundles** | ✅ | ❌ (`.is_wasm` Property existiert, wird aber nicht genutzt) | 🟢 Nice-to-have |
| **Bundle Persistence** | ✅ | ❌ (kein Caching auf Disk bei Restart) | 🟡 Important |

---

## 5. Plugin-System

### Was OPA hat
OPA hat ein vollständiges Plugin-Framework mit:
- **Bundle Plugin** — Automatisches Laden von Bundles
- **Decision Log Plugin** — Sendet Entscheidungsprotokolle an Remote-Dienste
- **Status Plugin** — Meldet Status an Management-API
- **Discovery Plugin** — Dynamische Konfiguration über OPA-Bundles
- **Plugin-Manager** mit Lifecycle (Start, Stop, Reconfigure)
- Custom Plugins via Go-Interface

### Was NPA hat
- ✅ **Plugin ABC** — Abstrakte Basisklasse mit `start()`, `stop()`, `reconfigure()`, `status()`
- ✅ **PluginManager** — Registrierung, Start/Stop aller Plugins
- ✅ **Plugin States** (NOT_READY, OK, ERROR)
- ⚠️ **Keine konkreten Plugin-Implementierungen** — Bundle/Status/DecisionLog existieren nur als Stub-Status in der Status-API

### Fehlend

| Feature | Bewertung |
|---------|-----------|
| **Bundle Plugin Implementierung** — Automatisches Polling in Plugin-Lifecycle | 🔴 Critical |
| **Decision Log Plugin** — Remote-Upload von Entscheidungsprotokollen | 🟡 Important |
| **Status Plugin** — Remote-Status-Reporting | 🟡 Important |
| **Discovery Plugin** — Dynamische Konfiguration | 🟡 Important |

---

## 6. CLI-Befehle

| Befehl | OPA | NPA | Status |
|--------|-----|-----|--------|
| `run` | ✅ | ✅ (mit TLS, Config, Bundle-Flags) | ✅ |
| `eval` | ✅ | ✅ (mit --input, --data, --bundle, --format) | ✅ |
| `test` | ✅ | ✅ (mit --verbose, --run Filter) | ✅ |
| `fmt` | ✅ | ✅ (mit --diff, --check) | ✅ |
| `build` | ✅ | ✅ (mit --output, --revision) | ✅ |
| `check` | ✅ | ✅ (mit --strict) | ✅ |
| `parse` | ✅ | ✅ (AST als JSON) | ✅ |
| `inspect` | ✅ | ✅ (Bundle-Inhalt als Tabelle) | ✅ |
| `sign` | ✅ | ✅ (mit --signing-key, --signing-alg) | ✅ |
| `version` | ✅ | ✅ | ✅ |
| **`bench`** | ✅ | ❌ | 🟢 Nice-to-have |
| **`deps`** | ✅ | ❌ | 🟢 Nice-to-have |
| **`capabilities`** | ✅ | ❌ | 🟢 Nice-to-have |
| **`exec`** | ✅ | ❌ | 🟡 Important |
| **`oracle`** | ✅ | ❌ | 🟢 Nice-to-have |
| **`refactor`** | ✅ | ❌ | 🟢 Nice-to-have |

**Fazit CLI:** 10 von 16 OPA-Befehlen sind implementiert — alle wichtigen für den Alltag.

---

## 7. Storage Layer

| Feature | OPA | NPA | Status |
|---------|-----|-----|--------|
| In-Memory Backend | ✅ | ✅ (Thread-safe, Copy-on-Write) | ✅ |
| Disk Backend | ✅ (badger/bolt) | ✅ (SQLite mit WAL-Modus) | ✅ |
| Abstract Storage Interface | ✅ | ✅ | ✅ |
| Transactions (Read/Write) | ✅ | ✅ (TxnMode.READ / WRITE) | ✅ |
| Snapshot Isolation | ✅ | ✅ (deep copy auf Write-Txn) | ✅ |
| Storage Events | ✅ | ✅ (StorageEvent: op, path, value) | ✅ |
| Transaction Context Manager | ✅ | ✅ | ✅ |
| Policy Storage (CRUD) | ✅ | ✅ | ✅ |
| **Triggers** (Callbacks nach Mutation) | ✅ | ❌ | 🟡 Important |
| **Truncate Operation** | ✅ | ❌ | 🟢 Nice-to-have |
| **Multi-Version Concurrency** | ✅ | ⚠️ RLock-basiert, kein MVCC | 🟢 Nice-to-have |

---

## 8. Performance-Features

| Feature | OPA | NPA | Status |
|---------|-----|-----|--------|
| Intra-Query Cache | ✅ | ✅ | ✅ |
| Inter-Query Cache | ✅ (konfigurierbar) | ✅ (TTL-basiertes LRU) | ✅ |
| **Partial Evaluation** | ✅ (vollständig) | ❌ (nur Stub) | 🔴 Critical |
| **Rule Indexing** | ✅ (Trie-basiert, O(1)-Lookup) | ❌ (linearer Scan) | 🟡 Important |
| **Comprehension Indexing** | ✅ | ❌ | 🟡 Important |
| **Early Exit Optimization** | ✅ | ⚠️ Teilweise (Complete Rules: First Match) | 🟢 Nice-to-have |
| **Query Profiling** | ✅ | ❌ | 🟡 Important |
| **Benchmarking (bench Befehl)** | ✅ | ❌ | 🟢 Nice-to-have |

---

## 9. Sicherheit

| Feature | OPA | NPA | Status |
|---------|-----|-----|--------|
| TLS/HTTPS | ✅ | ✅ (HTTPS-first Design, Auto-Cert für Dev) | ✅ |
| Bearer Token Auth | ✅ | ✅ (API Keys + JWT) | ✅ |
| Client Certificate Auth | ✅ | ⚠️ Config-Option vorhanden, Implementierung fehlt in auth.py | 🟡 Important |
| Authorization (Policy-basiert) | ✅ (system.authz) | ❌ | 🟡 Important |
| Security Headers | ❌ (nicht eingebaut) | ✅ (CSP, HSTS, X-Frame-Options, etc.) | ✅ NPA besser |
| CORS | ✅ | ✅ | ✅ |
| Session-basierte Web-UI Auth | ❌ | ✅ (Cookies, constant-time compare) | ✅ NPA-Bonus |
| Rate Limiting | ❌ (extern) | ⚠️ Config vorhanden (`rate_limit`), Enforcement nicht implementiert | 🟢 Nice-to-have |
| Request Size Limit | ✅ | ✅ (`max_request_size` in Config) | ✅ |
| **Authorization Policy** | ✅ (`system.authz`) | ❌ | 🟡 Important |
| **Min TLS Version** | ✅ | ✅ (konfigurierbar, Default TLSv1.2) | ✅ |

---

## 10. Wasm/IR Compilation

| Feature | OPA | NPA | Status |
|---------|-----|-----|--------|
| Rego → Wasm Compilation | ✅ | ❌ | 🟡 Important |
| Rego → IR (Intermediate Repr.) | ✅ | ❌ | 🟡 Important |
| Wasm SDK Support | ✅ | ❌ | 🟡 Important |
| Wasm in Bundles | ✅ | ❌ (Property `.is_wasm` existiert, wird ignoriert) | 🟡 Important |

**Fazit:** NPA hat kein Äquivalent zur Wasm-Compilation. Da NPA in Python läuft, wäre ein Äquivalent (z.B. Transpilation zu Python-Bytecode oder ein embedded evaluator) aufwandreich.

---

## Zusammenfassung nach Priorität

### 🔴 Critical (Kernkompatibilität gebrochen)

| # | Gap | Bereich |
|---|-----|---------|
| 1 | **Partial Evaluation Engine** — `/v1/compile` ist nur ein Stub | Evaluator + REST API |
| 2 | **`with` auf `data.`-Pfade** — Nur input.* wird modifiziert | Evaluator |

### 🟡 Important (Produktionsrelevant)

| # | Gap | Bereich |
|---|-----|---------|
| 3 | v0 Data API (`POST /v0/data`) | REST API |
| 4 | `explain`/`instrument` Query-Parameter | REST API |
| 5 | Rule Indexing | Performance |
| 6 | Comprehension Indexing | Performance |
| 7 | Delta Bundles | Bundle |
| 8 | Bundle Discovery Service | Bundle |
| 9 | Bundle Persistence (Disk-Cache) | Bundle |
| 10 | Multi-Bundle echte Orchestrierung | Bundle |
| 11 | Bundle Plugin (konkretes Plugin, nicht nur Framework) | Plugin |
| 12 | Decision Log Plugin | Plugin |
| 13 | Status Plugin | Plugin |
| 14 | Discovery Plugin | Plugin |
| 15 | Storage Triggers | Storage |
| 16 | Client Certificate Auth (Implementierung) | Security |
| 17 | Policy-basierte Authorization (`system.authz`) | Security |
| 18 | Query Profiling | Performance |
| 19 | Evaluation Trace/Explain | Evaluator |
| 20 | JWT einzelne `verify_*` Builtins (13 Stück) | Builtins |
| 21 | `exec` CLI-Befehl | CLI |
| 22 | Ref Head Rules (`a.b.c := ...`) | Parser |
| 23 | Wasm/IR Compilation | Compilation |

### 🟢 Nice-to-have

| # | Gap | Bereich |
|---|-----|---------|
| 24 | Health mit Policy-Evaluation | REST API |
| 25 | `POST /` Root-Query | REST API |
| 26 | `rego.v1` Enforcement | Parser |
| 27 | `bench` CLI | CLI |
| 28 | `deps` CLI | CLI |
| 29 | `capabilities` CLI | CLI |
| 30 | `oracle` CLI | CLI |
| 31 | `refactor` CLI | CLI |
| 32 | Storage Truncate | Storage |
| 33 | MVCC (vs RLock) | Storage |
| 34 | Rate Limiting Enforcement | Security |
| 35 | `crypto.x509.parse_and_verify_certificates_with_options` | Builtins |
| 36 | `providers.aws.sign_req_obj` | Builtins |

---

## Stärken von NPA gegenüber OPA

| Feature | Details |
|---------|---------|
| **Web Dashboard** | Integriertes UI mit Login, Decision-Log, Data-Browser |
| **HTTPS-first** | Auto-generierte Dev-Zertifikate, Security Headers |
| **SQLite Backend** | Persistenter Storage mit WAL, besser als OPA's badger für embedded |
| **Python-Ökosystem** | Einfacher erweiterbar, bessere Tooling-Integration |
| **FastAPI/OpenAPI** | Auto-generierte API-Dokumentation unter `/v1/docs` |
| **Pydantic Config** | Typsichere Konfiguration mit Env-Variable-Support |
| **192+ Builtins** | Nahezu vollständige OPA-Builtin-Abdeckung in Python |

---

## Empfohlene Prioritätsreihenfolge für Implementierung

1. **`with` auf `data.`-Pfade** — Kleiner Aufwand, hohe Wirkung
2. **Partial Evaluation** — Kernfeature, benötigt für `/v1/compile`
3. **Rule Indexing** — Wichtig für Performance bei großen Policy-Sets
4. **Bundle Plugin** — Verbindet Bundle-Loader mit Plugin-Lifecycle
5. **JWT Einzelverifier** — Mapping auf `io.jwt.decode_verify` Unterfunktionen
6. **v0 Data API** — Triviale Route, maximale Kompatibilität
7. **`system.authz` Policy-Authorization** — Produktions-Sicherheit
