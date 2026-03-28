# NPA Schnellstart-Anleitung

Diese Anleitung bringt dich in 10 Minuten von der Installation bis zur ersten
Policy-Evaluation -- lokal, per Docker oder als eingebettete Library.

---

## Inhaltsverzeichnis

1. [Installation](#1-installation)
2. [Server starten](#2-server-starten)
3. [Erste Policy hochladen](#3-erste-policy-hochladen)
4. [Policy evaluieren](#4-policy-evaluieren)
5. [Daten verwalten](#5-daten-verwalten)
6. [CLI-Auswertung (ohne Server)](#6-cli-auswertung-ohne-server)
7. [Web-Dashboard](#7-web-dashboard)
8. [Docker-Quickstart](#8-docker-quickstart)
9. [Python SDK (Embedded)](#9-python-sdk-embedded)
10. [Bundles verwenden](#10-bundles-verwenden)
11. [Authentifizierung einrichten](#11-authentifizierung-einrichten)
12. [Konfigurationsdatei](#12-konfigurationsdatei)
13. [Naechste Schritte](#13-naechste-schritte)

---

## 1. Installation

### Voraussetzungen

- Python >= 3.12
- pip (oder uv, poetry)

### Installation aus dem Repository

```bash
git clone https://github.com/BLS-ISP/NextPolicyAgent.git
cd NextPolicyAgent
pip install -e ".[dev]"
```

### Pruefen, ob NPA installiert ist

```bash
npa version
# NPA v0.1.0 (Python 3.13.x)
```

---

## 2. Server starten

### Mit automatischem TLS-Zertifikat (Standard)

```bash
npa run
```

NPA generiert automatisch ein Self-Signed-Zertifikat und startet auf
`https://0.0.0.0:8443`. Das ist der empfohlene Modus fuer Entwicklung.

### Mit eigenem Zertifikat

```bash
npa run --tls-cert-file /pfad/zu/cert.pem --tls-private-key-file /pfad/zu/key.pem
```

### Ohne TLS (nur Entwicklung/Tests)

```bash
npa run --no-tls
```

Der Server laeuft dann auf `http://0.0.0.0:8443`.

### Adresse und Port aendern

```bash
npa run --addr 127.0.0.1:9090 --no-tls
```

### Mit Policies beim Start laden

```bash
npa run --bundle ./mein-policy-verzeichnis/
```

---

## 3. Erste Policy hochladen

Erstelle eine Datei `authz.rego`:

```rego
package authz

import future.keywords.if

default allow = false

allow if {
    input.role == "admin"
}

allow if {
    input.role == "editor"
    input.action == "read"
}
```

Lade sie per REST-API hoch:

```bash
# Mit TLS (Self-Signed -> -k fuer insecure)
curl -sk -X PUT https://localhost:8443/v1/policies/authz \
  -H "Content-Type: text/plain" \
  --data-binary @authz.rego

# Ohne TLS
curl -s -X PUT http://localhost:8443/v1/policies/authz \
  -H "Content-Type: text/plain" \
  --data-binary @authz.rego
```

Antwort:

```json
{
  "result": {
    "id": "authz",
    "raw": "package authz\n..."
  }
}
```

### Hochgeladene Policies auflisten

```bash
curl -sk https://localhost:8443/v1/policies | python -m json.tool
```

---

## 4. Policy evaluieren

### Per REST-API (POST)

```bash
# Admin -> allow = true
curl -sk -X POST https://localhost:8443/v1/data/authz/allow \
  -H "Content-Type: application/json" \
  -d '{"input": {"role": "admin", "action": "write"}}'
```

Antwort:

```json
{
  "decision_id": "a1b2c3d4-...",
  "result": true
}
```

```bash
# Viewer -> allow = false
curl -sk -X POST https://localhost:8443/v1/data/authz/allow \
  -H "Content-Type: application/json" \
  -d '{"input": {"role": "viewer", "action": "write"}}'
```

Antwort:

```json
{
  "decision_id": "e5f6g7h8-...",
  "result": false
}
```

### Ganzes Package abfragen

```bash
curl -sk -X POST https://localhost:8443/v1/data/authz \
  -H "Content-Type: application/json" \
  -d '{"input": {"role": "editor", "action": "read"}}'
```

Antwort:

```json
{
  "result": {
    "allow": true
  }
}
```

### Per REST-API (GET mit Query-Parameter)

```bash
curl -sk "https://localhost:8443/v1/data/authz/allow?input=%7B%22role%22%3A%22admin%22%7D"
```

### Ad-hoc Query

```bash
curl -sk -X POST https://localhost:8443/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "data.authz.allow", "input": {"role": "admin"}}'
```

---

## 5. Daten verwalten

Neben Policies kannst du auch JSON-Daten im Store ablegen, auf die Policies
per `data.*` zugreifen koennen.

### Daten setzen

```bash
curl -sk -X PUT https://localhost:8443/v1/data/users \
  -H "Content-Type: application/json" \
  -d '{
    "admins": ["alice", "bob"],
    "editors": ["charlie", "diana"]
  }'
```

### Daten lesen

```bash
curl -sk https://localhost:8443/v1/data/users
# {"result": {"admins": ["alice", "bob"], "editors": ["charlie", "diana"]}}
```

### Daten in Policy verwenden

```rego
package user_check

import future.keywords.if
import future.keywords.in

is_admin if {
    input.user in data.users.admins
}
```

```bash
curl -sk -X POST https://localhost:8443/v1/data/user_check/is_admin \
  -H "Content-Type: application/json" \
  -d '{"input": {"user": "alice"}}'
# {"result": true}
```

### Daten patchen (RFC 6902 JSON Patch)

```bash
curl -sk -X PATCH https://localhost:8443/v1/data/users \
  -H "Content-Type: application/json" \
  -d '[{"op": "add", "path": "/editors/-", "value": "eve"}]'
```

### Daten loeschen

```bash
curl -sk -X DELETE https://localhost:8443/v1/data/users
```

---

## 6. CLI-Auswertung (ohne Server)

Die CLI evaluiert Policies direkt -- ohne laufenden Server:

### Einfache Evaluation

```bash
npa eval "1 + 2"
# {"result": [3]}
```

### Mit Policy und Input

Erstelle `input.json`:

```json
{
  "role": "admin",
  "action": "delete"
}
```

```bash
npa eval -d authz.rego -i input.json "data.authz.allow"
# {"result": [true]}
```

### Ganzes Verzeichnis laden

```bash
npa eval -d examples/rbac/ -i examples/rbac/input.json "data.rbac.authz"
```

### Ausgabeformate

```bash
# JSON (Standard)
npa eval -d authz.rego "data.authz" --format json

# Schoen formatiert
npa eval -d authz.rego "data.authz" --format pretty

# Rohe Werte
npa eval -d authz.rego "data.authz" --format raw
```

### Weitere CLI-Befehle

```bash
# Syntax pruefen
npa check authz.rego

# AST anzeigen
npa parse authz.rego

# Code formatieren
npa fmt authz.rego

# Tests ausfuehren (test_*-Regeln)
npa test ./policies/ -v

# Policy-Abhaengigkeiten anzeigen
npa deps "data.authz.allow" -d authz.rego

# Performance messen
npa bench "data.authz.allow" -d authz.rego -i input.json -n 1000
```

---

## 7. Web-Dashboard

NPA hat ein integriertes Web-Dashboard unter `https://localhost:8443/`.

> **Ausfuehrliche Dokumentation:** Alle 7 Dashboard-Seiten mit Workflows,
> Tastenkuerzeln und Fehlerbehebung sind im
> [Web-Dashboard Benutzerhandbuch](Web_Dashboard.md) beschrieben.

### Login

- **Benutzer:** `admin` (Standard)
- **Passwort:** `admin` (Standard)

Aenderbar ueber Umgebungsvariablen:

```bash
export NPA_AUTH_UI_USERNAME=mein_user
export NPA_AUTH_UI_PASSWORD=sicheres_passwort
npa run
```

### Dashboard-Funktionen

- **Status-Uebersicht:** Server-Uptime, geladene Policies, Evaluationen
- **Policy-Editor:** Policies erstellen, bearbeiten und loeschen
- **Daten-Browser:** JSON-Daten im Store durchsuchen und bearbeiten
- **Query-Konsole:** Rego-Queries interaktiv ausfuehren
- **Decision-Log:** Letzte Entscheidungen mit Input/Output und Dauer
- **Metriken:** Live-Performance-Zahlen
- **Einstellungen:** Server-Konfiguration einsehen

---

## 8. Docker-Quickstart

### Image bauen und starten

```bash
docker build -t npa:latest .
docker run -d -p 8443:8443 --name npa npa:latest
```

### Mit eigenen Policies

```bash
docker run -d -p 8443:8443 \
  -v ./policies:/policies:ro \
  npa:latest
```

### Docker Compose

```bash
docker compose up -d
```

### Health pruefen

```bash
curl -sk https://localhost:8443/health
# {}  (200 OK = gesund)
```

Vollstaendige Docker-Anleitung: [Docker-Anleitung.md](Docker-Anleitung.md)

---

## 9. Python SDK (Embedded)

NPA kann als Library direkt in Python-Anwendungen eingebettet werden --
ohne HTTP-Server.

### Einfaches Beispiel

```python
from npa.sdk.sdk import NPA

# Engine erstellen
engine = NPA()

# Policy laden
engine.load_policy("authz", """
    package authz
    import future.keywords.if
    default allow = false
    allow if { input.role == "admin" }
""")

# Evaluieren
result = engine.decide_bool("data.authz.allow", {"role": "admin"})
print(result)  # True

result = engine.decide_bool("data.authz.allow", {"role": "viewer"})
print(result)  # False
```

### Mit Daten

```python
engine = NPA()

engine.load_policy("rbac", """
    package rbac
    import future.keywords.if
    import future.keywords.in
    allow if { input.user in data.admins }
""")

engine.set_data({"admins": ["alice", "bob"]})

result = engine.decide_bool("data.rbac.allow", {"user": "alice"})
print(result)  # True
```

### Detaillierte Ergebnisse

```python
result = engine.decide("data.authz", {"role": "admin"})
# Gibt das volle Ergebnis zurueck (dict/list/bool/None)
```

### Cache-Statistiken

```python
stats = engine.cache_stats
print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
```

Vollstaendige SDK-Referenz: [SDK_Referenz.md](SDK_Referenz.md)

---

## 10. Bundles verwenden

Bundles packen Policies und Daten in eine `.tar.gz`-Datei fuer einfaches
Deployment.

### Bundle bauen

```bash
# Aus einem Verzeichnis
npa build examples/rbac/ -o rbac-bundle.tar.gz

# Mit Revision
npa build examples/rbac/ -o rbac-bundle.tar.gz -r "v1.0"
```

### Bundle inspizieren

```bash
npa inspect rbac-bundle.tar.gz
# Type    Path            Size
# rego    policy.rego     245
# data    data.json       128
```

### Bundle signieren

```bash
npa sign rbac-bundle.tar.gz --signing-key private.pem
```

### Bundle beim Server-Start laden

```bash
npa run --bundle rbac-bundle.tar.gz
```

### Bundle per REST-API hochladen

```bash
curl -sk -X PUT https://localhost:8443/v1/bundles/rbac \
  -H "Content-Type: application/gzip" \
  --data-binary @rbac-bundle.tar.gz
```

### Bundle-Status pruefen

```bash
curl -sk https://localhost:8443/v1/bundles
```

---

## 11. Authentifizierung einrichten

### API-Key-Authentifizierung

```bash
export NPA_AUTH_ENABLED=true
export NPA_AUTH_API_KEYS='["mein-geheimer-key-123"]'
npa run
```

Anfragen mit API-Key:

```bash
curl -sk -H "Authorization: Bearer mein-geheimer-key-123" \
  https://localhost:8443/v1/data/authz/allow \
  -d '{"input": {"role": "admin"}}'
```

### JWT-Authentifizierung

```bash
export NPA_AUTH_ENABLED=true
export NPA_AUTH_JWT_SECRET=mein-jwt-secret
npa run
```

Anfragen mit JWT-Token:

```bash
TOKEN=$(python -c "import jwt; print(jwt.encode({'sub': 'user1'}, 'mein-jwt-secret', algorithm='HS256'))")
curl -sk -H "Authorization: Bearer $TOKEN" \
  https://localhost:8443/v1/data/authz/allow \
  -d '{"input": {"role": "admin"}}'
```

### Ohne Authentifizierung

API-Auth ist standardmaessig deaktiviert. Das Web-Dashboard hat immer ein
eigenes Login (Standard: `admin`/`admin`).

---

## 12. Konfigurationsdatei

Alle Einstellungen koennen in einer YAML-Datei zusammengefasst werden:

Erstelle `npa.yaml`:

```yaml
server:
  addr: "0.0.0.0"
  port: 8443
  workers: 1

tls:
  enabled: true
  auto_generate: true

auth:
  enabled: false
  ui_username: "admin"
  ui_password: "sicheres-passwort"

storage:
  backend: "memory"

logging:
  level: "INFO"
  format: "json"
  decision_log: true

bundles:
  - name: "authz"
    url: "https://bundle-server.example.com/bundles/authz"
    polling_interval: 30

labels:
  environment: "development"
```

Starten mit Config-Datei:

```bash
npa run --config-file npa.yaml
```

Alle Werte koennen auch per Umgebungsvariable ueberschrieben werden
(Prefix `NPA_`). Vollstaendige Referenz: [Konfigurationsreferenz.md](Konfigurationsreferenz.md)

---

## 13. Naechste Schritte

| Was | Wo |
|-----|----|
| REST-API Referenz | [REST_API_Referenz.md](REST_API_Referenz.md) |
| CLI-Referenz | [CLI_Referenz.md](CLI_Referenz.md) |
| Rego-Sprachreferenz | [Rego_Sprachreferenz.md](Rego_Sprachreferenz.md) |
| SDK-Referenz | [SDK_Referenz.md](SDK_Referenz.md) |
| Konfigurationsreferenz | [Konfigurationsreferenz.md](Konfigurationsreferenz.md) |
| Policy-Beispiele | [../examples/README.md](../examples/README.md) |
| Plugin-Beispiele | [../examples/plugins/README.md](../examples/plugins/README.md) |
| Docker-Anleitung | [Docker-Anleitung.md](Docker-Anleitung.md) |
| Performance-Vergleich | [Performance_Vergleich_OPA_vs_NPA.md](Performance_Vergleich_OPA_vs_NPA.md) |
