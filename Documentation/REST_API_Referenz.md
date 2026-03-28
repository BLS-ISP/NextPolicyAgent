# NPA REST-API Referenz

Vollstaendige Dokumentation aller HTTP-Endpunkte des NPA-Servers.
Die API ist OPA-kompatibel -- bestehende OPA-Clients funktionieren ohne Aenderungen.

---

## Inhaltsverzeichnis

1. [Ueberblick](#ueberblick)
2. [Data API](#data-api)
3. [Policy API](#policy-api)
4. [Query API](#query-api)
5. [Compile API (Partial Evaluation)](#compile-api)
6. [Bundle API](#bundle-api)
7. [Health API](#health-api)
8. [Config & Status API](#config--status-api)
9. [Metrics API](#metrics-api)
10. [Web-UI API](#web-ui-api)
11. [Fehlerformat](#fehlerformat)
12. [Authentifizierung](#authentifizierung)

---

## Ueberblick

| Basis-URL | Standard |
|-----------|----------|
| HTTPS | `https://localhost:8443` |
| HTTP (--no-tls) | `http://localhost:8443` |

### Allgemeine Query-Parameter

Diese Parameter sind bei den meisten Endpunkten verfuegbar:

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `pretty` | Flag | JSON-Ausgabe eingerueckt formatieren |
| `metrics` | Flag | Performance-Metriken in Antwort einschliessen |
| `provenance` | Flag | Herkunftsinformation (NPA-Version, Engine) einschliessen |
| `explain` | String | Erklaerungsmodus: `off`, `full`, `notes`, `fails`, `debug` |
| `instrument` | Flag | Detaillierte Instrumentierungsmetriken |

### Content-Types

| Endpunkt | Request | Response |
|----------|---------|----------|
| Data API | `application/json` | `application/json` |
| Policy API | `text/plain` (Rego) | `application/json` |
| Bundle API | `application/gzip` | `application/json` |
| Metrics | -- | `text/plain` (Prometheus) |

---

## Data API

Die Data API ist der Hauptendpunkt fuer Policy-Evaluierung und Datenmanagement.

### GET /v1/data/{path}

Liest Daten oder evaluiert eine Policy am angegebenen Pfad.

**Parameter:**

| Name | In | Typ | Beschreibung |
|------|----|-----|-------------|
| `path` | URL | String | Pfad im Datenbaum (z.B. `authz/allow`) |
| `input` | Query | JSON-String | URL-encodiertes Input-Dokument |
| `pretty` | Query | Flag | Huebsche Formatierung |
| `metrics` | Query | Flag | Metriken einschliessen |
| `provenance` | Query | Flag | Herkunft einschliessen |
| `explain` | Query | String | Erklaerungsmodus |

**Beispiel:**

```bash
curl -sk "https://localhost:8443/v1/data/authz/allow"
```

**Antwort (200):**

```json
{
  "decision_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "result": true
}
```

**Antwort mit Metriken:**

```json
{
  "decision_id": "...",
  "result": true,
  "metrics": {
    "timer_rego_query_eval_ns": 15000,
    "timer_rego_query_parse_ns": 3000,
    "timer_rego_query_compile_ns": 2000
  }
}
```

---

### POST /v1/data/{path}

Evaluiert eine Policy mit Input-Dokument.

**Request Body:**

```json
{
  "input": {
    "role": "admin",
    "action": "write",
    "resource": "reports"
  }
}
```

**Beispiel:**

```bash
curl -sk -X POST https://localhost:8443/v1/data/authz/allow \
  -H "Content-Type: application/json" \
  -d '{"input": {"role": "admin"}}'
```

**Antwort (200):**

```json
{
  "decision_id": "...",
  "result": true
}
```

**Antwort bei undefiniertem Ergebnis (200):**

```json
{
  "decision_id": "..."
}
```

(Kein `result`-Feld wenn die Policy kein Ergebnis liefert.)

---

### PUT /v1/data/{path}

Erstellt oder ueberschreibt ein Dokument im Datenbaum.

**Beispiel:**

```bash
curl -sk -X PUT https://localhost:8443/v1/data/users \
  -H "Content-Type: application/json" \
  -d '{"admins": ["alice", "bob"], "editors": ["charlie"]}'
```

**Antwort:** `204 No Content`

**Bedingtes Schreiben:**

```bash
# Nur erstellen, wenn nicht vorhanden
curl -sk -X PUT https://localhost:8443/v1/data/users \
  -H "Content-Type: application/json" \
  -H "If-None-Match: *" \
  -d '{"admins": ["alice"]}'
```

Antwort `304 Not Modified` wenn Daten bereits existieren.

---

### PATCH /v1/data/{path}

Aendert Daten per JSON Patch (RFC 6902).

**Request Body (Array von Operationen):**

```json
[
  {"op": "add", "path": "/editors/-", "value": "eve"},
  {"op": "remove", "path": "/admins/1"},
  {"op": "replace", "path": "/admins/0", "value": "alice_new"},
  {"op": "move", "from": "/temp", "path": "/archive"},
  {"op": "copy", "from": "/admins", "path": "/backup_admins"},
  {"op": "test", "path": "/admins/0", "value": "alice_new"}
]
```

**Unterstuetzte Operationen:**

| Operation | Beschreibung |
|-----------|-------------|
| `add` | Wert an Pfad einfuegen |
| `remove` | Wert an Pfad entfernen |
| `replace` | Wert an Pfad ersetzen |
| `move` | Wert von `from` nach `path` verschieben |
| `copy` | Wert von `from` nach `path` kopieren |
| `test` | Pruefen, ob Wert an Pfad dem erwarteten Wert entspricht |

**Antwort:** `204 No Content`

---

### DELETE /v1/data/{path}

Loescht ein Dokument aus dem Datenbaum.

```bash
curl -sk -X DELETE https://localhost:8443/v1/data/users
```

**Antwort:** `204 No Content`

---

### GET /v0/data/{path}

Legacy OPA v0 API -- gibt das Ergebnis direkt zurueck (ohne Wrapper).

```bash
curl -sk https://localhost:8443/v0/data/authz/allow
# true
```

---

## Policy API

### GET /v1/policies

Listet alle geladenen Policies.

```bash
curl -sk https://localhost:8443/v1/policies
```

**Antwort (200):**

```json
{
  "result": [
    {
      "id": "authz",
      "raw": "package authz\nimport future.keywords.if\n...",
      "ast": {
        "package": {"path": [{"value": "data"}, {"value": "authz"}]},
        "rules": [...]
      }
    }
  ]
}
```

---

### GET /v1/policies/{id}

Gibt eine einzelne Policy zurueck.

```bash
curl -sk https://localhost:8443/v1/policies/authz
```

**Antwort (200):**

```json
{
  "result": {
    "id": "authz",
    "raw": "package authz\n...",
    "ast": {...}
  }
}
```

**Fehler (404):**

```json
{
  "code": "resource_not_found",
  "message": "policy id \"unknown\" not found"
}
```

---

### PUT /v1/policies/{id}

Erstellt oder aktualisiert eine Policy.

**Content-Type:** `text/plain` (Rego-Quellcode)

```bash
curl -sk -X PUT https://localhost:8443/v1/policies/authz \
  -H "Content-Type: text/plain" \
  -d 'package authz
import future.keywords.if
default allow = false
allow if { input.role == "admin" }'
```

**Antwort (200):**

```json
{
  "result": {
    "id": "authz",
    "raw": "package authz\n..."
  }
}
```

**Fehler (400) bei Syntax-Fehlern:**

```json
{
  "code": "invalid_parameter",
  "message": "error(s) in policy: 1:10 expected rule head"
}
```

---

### DELETE /v1/policies/{id}

Loescht eine Policy.

```bash
curl -sk -X DELETE https://localhost:8443/v1/policies/authz
```

**Antwort:** `204 No Content`

---

## Query API

### POST /v1/query

Fuehrt eine Ad-hoc Rego-Query aus.

**Request Body:**

```json
{
  "query": "data.authz.allow",
  "input": {
    "role": "admin"
  }
}
```

**Beispiel:**

```bash
curl -sk -X POST https://localhost:8443/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "x := 1 + 2", "input": {}}'
```

**Antwort (200):**

```json
{
  "decision_id": "...",
  "result": [{"x": 3}]
}
```

---

### GET /v1/query

Query per GET-Request.

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `q` | String | Rego-Query |
| `input` | JSON-String | URL-encodiertes Input-Dokument |

```bash
curl -sk "https://localhost:8443/v1/query?q=data.authz.allow&input=%7B%22role%22%3A%22admin%22%7D"
```

---

## Compile API

### POST /v1/compile

Partial Evaluation -- evaluiert eine Query teilweise und gibt
residuale Queries zurueck.

**Request Body:**

```json
{
  "query": "data.authz.allow",
  "input": {
    "role": "admin"
  },
  "unknowns": ["input.resource"],
  "options": {
    "disableInlining": [],
    "nondeterministicBuiltins": false
  }
}
```

**Antwort (200):**

```json
{
  "result": {
    "queries": [
      [{"terms": [...]}]
    ],
    "support": [...]
  }
}
```

**Ohne `unknowns`:** Fuehrt vollstaendige Evaluation durch (wie `/v1/query`).

---

## Bundle API

### GET /v1/bundles

Listet alle aktiven Bundles.

```bash
curl -sk https://localhost:8443/v1/bundles
```

**Antwort (200):**

```json
{
  "result": {
    "authz": {
      "active": true,
      "revision": "v1.0",
      "roots": ["authz"],
      "policies": ["authz/policy.rego"],
      "activated_at": "2026-03-28T12:00:00Z"
    }
  }
}
```

---

### GET /v1/bundles/{name}

Gibt Info zu einem spezifischen Bundle zurueck.

```bash
curl -sk https://localhost:8443/v1/bundles/authz
```

---

### PUT /v1/bundles/{name}

Laedt ein Bundle hoch und aktiviert es.

```bash
curl -sk -X PUT https://localhost:8443/v1/bundles/authz \
  -H "Content-Type: application/gzip" \
  --data-binary @authz-bundle.tar.gz
```

**Antwort:** `200 OK`

---

### DELETE /v1/bundles/{name}

Deaktiviert und entfernt ein Bundle.

```bash
curl -sk -X DELETE https://localhost:8443/v1/bundles/authz
```

**Antwort:** `204 No Content`

---

## Health API

### GET /health

Aggregierter Health-Check.

```bash
curl -sk https://localhost:8443/health
```

**Antwort (200 = gesund):**

```json
{}
```

**Mit Optionen:**

| Parameter | Beschreibung |
|-----------|-------------|
| `bundles` | Fordert, dass alle Bundles aktiv sind |
| `plugins` | Fordert, dass alle Plugins OK sind |
| `exclude-plugin[]` | Schliesst bestimmte Plugins aus der Pruefung aus |

```bash
# Nur gesund wenn alle Bundles aktiv
curl -sk "https://localhost:8443/health?bundles"

# Nur gesund wenn alle Plugins OK, ausser Discovery
curl -sk "https://localhost:8443/health?plugins&exclude-plugin[]=discovery"
```

**Antwort (500 = ungesund):**

```json
{
  "code": "unhealthy",
  "message": "bundle \"authz\" not active"
}
```

---

### GET /health/live

Kubernetes Liveness Probe -- immer erfolgreich wenn der Server laeuft.

```bash
curl -sk https://localhost:8443/health/live
# {"status": "ok"}
```

---

### GET /health/ready

Kubernetes Readiness Probe -- prueft ob NPA bereit ist, Anfragen zu verarbeiten.

```bash
curl -sk https://localhost:8443/health/ready
```

**Bereit (200):**

```json
{"status": "ok"}
```

**Nicht bereit (503):**

```json
{"status": "not_ready"}
```

---

## Config & Status API

### GET /v1/config

Gibt die aktive Konfiguration zurueck (sicherer Teilausschnitt -- keine Secrets).

```bash
curl -sk https://localhost:8443/v1/config
```

**Antwort (200):**

```json
{
  "result": {
    "labels": {"environment": "development"},
    "default_decision": "/system/main",
    "storage": {"backend": "memory"},
    "server": {"addr": "0.0.0.0", "port": 8443}
  }
}
```

---

### GET /v1/status

Gibt Server-Status inkl. Plugin-Status zurueck.

```bash
curl -sk https://localhost:8443/v1/status
```

**Antwort (200):**

```json
{
  "result": {
    "uptime_ns": 3600000000000,
    "plugins": {
      "decision_logs": {"state": "OK"},
      "status": {"state": "OK"},
      "bundle": {"state": "OK"}
    }
  }
}
```

---

## Metrics API

### GET /metrics

Prometheus-kompatible Metriken im Text-Format.

```bash
curl -sk https://localhost:8443/metrics
```

**Antwort (200, text/plain):**

```
# HELP npa_policy_evaluations_total Total number of policy evaluations
# TYPE npa_policy_evaluations_total counter
npa_policy_evaluations_total 42

# HELP npa_http_requests_total Total HTTP requests
# TYPE npa_http_requests_total counter
npa_http_requests_total{method="POST",path="/v1/data"} 38

# HELP npa_uptime_seconds Server uptime in seconds
# TYPE npa_uptime_seconds gauge
npa_uptime_seconds 3600.5

# HELP npa_last_evaluation_ns Last evaluation duration in nanoseconds
# TYPE npa_last_evaluation_ns gauge
npa_last_evaluation_ns 15000
```

---

## Web-UI API

Endpunkte fuer das Web-Dashboard. Cookie-basierte Authentifizierung.

### POST /v1/ui/login

```bash
curl -sk -X POST https://localhost:8443/v1/ui/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}' \
  -c cookies.txt
```

**Antwort (200):**

```json
{"status": "ok"}
```

Setzt HTTPOnly-Cookie `npa_session` (8h TTL).

---

### POST /v1/ui/logout

```bash
curl -sk -X POST https://localhost:8443/v1/ui/logout -b cookies.txt
```

---

### GET /v1/ui/session

Prueft ob die aktuelle Session gueltig ist.

```bash
curl -sk https://localhost:8443/v1/ui/session -b cookies.txt
# {"authenticated": true}
```

---

### GET /v1/ui/status

Aggregierter Dashboard-Status.

```bash
curl -sk https://localhost:8443/v1/ui/status -b cookies.txt
```

**Antwort:**

```json
{
  "server": {"uptime": "1h 30m", "version": "1.0.0"},
  "policies": {"count": 3, "ids": ["authz", "rbac", "network"]},
  "data": {"keys": ["users", "roles"]},
  "evaluator": {"total_evaluations": 150, "avg_duration_ms": 1.2},
  "decisions": {"total": 150, "last_5min": 42}
}
```

---

### GET /v1/ui/decisions

Decision-Log mit Pagination.

| Parameter | Default | Beschreibung |
|-----------|---------|-------------|
| `limit` | 100 | Maximale Anzahl Eintraege |
| `offset` | 0 | Offset fuer Pagination |

```bash
curl -sk "https://localhost:8443/v1/ui/decisions?limit=10" -b cookies.txt
```

**Antwort:**

```json
{
  "entries": [
    {
      "id": "a1b2c3d4-...",
      "timestamp": "2026-03-28T12:00:00Z",
      "query": "data.authz.allow",
      "input": {"role": "admin"},
      "result": true,
      "duration_ms": 0.8,
      "error": null
    }
  ],
  "total": 150
}
```

---

## Fehlerformat

Alle Fehler folgen dem OPA-Fehlerformat:

```json
{
  "code": "invalid_parameter",
  "message": "Beschreibung des Fehlers",
  "errors": [
    {
      "code": "rego_parse_error",
      "message": "1:10: expected rule head",
      "location": {"file": "policy.rego", "row": 1, "col": 10}
    }
  ]
}
```

### Fehlercodes

| Code | HTTP Status | Beschreibung |
|------|-------------|-------------|
| `invalid_parameter` | 400 | Ungueltiger Request-Parameter oder Body |
| `unauthorized` | 401 | Fehlende oder ungueltige Authentifizierung |
| `resource_not_found` | 404 | Policy oder Daten nicht gefunden |
| `internal_error` | 500 | Interner Serverfehler |
| `unhealthy` | 500 | Health-Check fehlgeschlagen |
| `resource_conflict` | 304 | Bedingte Schreiboperation fehlgeschlagen |

---

## Authentifizierung

Wenn `NPA_AUTH_ENABLED=true`:

### Bearer Token (API-Key)

```
Authorization: Bearer mein-api-key
```

### Bearer Token (JWT)

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### Ausgenommene Pfade

Diese Pfade erfordern keine Authentifizierung:

- `/health`
- `/health/live`
- `/health/ready`
- `/v1/docs`
- `/v1/redoc`
- `/openapi.json`
