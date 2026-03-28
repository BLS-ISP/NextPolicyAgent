# NPA Konfigurationsreferenz

Vollstaendige Dokumentation aller Konfigurationsoptionen.
NPA kann per Konfigurationsdatei (YAML/JSON), Umgebungsvariablen oder CLI-Optionen konfiguriert werden.

**Prioritaet:** CLI-Optionen > Umgebungsvariablen > Konfigurationsdatei > Defaults

---

## Inhaltsverzeichnis

1. [Konfigurationsdatei](#konfigurationsdatei)
2. [TLS-Konfiguration](#tls-konfiguration)
3. [Server-Konfiguration](#server-konfiguration)
4. [Authentifizierung](#authentifizierung)
5. [Storage](#storage)
6. [Bundles](#bundles)
7. [Logging](#logging)
8. [Labels](#labels)
9. [Umgebungsvariablen](#umgebungsvariablen)
10. [Vollstaendiges Beispiel](#vollstaendiges-beispiel)

---

## Konfigurationsdatei

NPA unterstuetzt YAML- und JSON-Konfigurationsdateien:

```bash
npa run -c npa.yaml
npa run -c config.json
```

### Minimale Konfiguration (YAML)

```yaml
server:
  port: 8443

auth:
  enabled: false
```

### Minimale Konfiguration (JSON)

```json
{
  "server": {
    "port": 8443
  },
  "auth": {
    "enabled": false
  }
}
```

---

## TLS-Konfiguration

HTTPS ist standardmaessig aktiviert.

```yaml
tls:
  enabled: true
  cert_file: /etc/npa/cert.pem
  key_file: /etc/npa/key.pem
  min_version: "TLSv1.2"
  auto_generate: true
```

| Feld | Typ | Default | Env-Variable | Beschreibung |
|------|-----|---------|-------------|-------------|
| `enabled` | bool | `true` | `NPA_TLS_ENABLED` | HTTPS aktivieren |
| `cert_file` | Path | `null` | `NPA_TLS_CERT_FILE` | Pfad zum TLS-Zertifikat (PEM) |
| `key_file` | Path | `null` | `NPA_TLS_KEY_FILE` | Pfad zum privaten Schluessel (PEM) |
| `min_version` | str | `"TLSv1.2"` | `NPA_TLS_MIN_VERSION` | Minimale TLS-Version |
| `auto_generate` | bool | `true` | `NPA_TLS_AUTO_GENERATE` | Selbstsigniertes Zertifikat fuer Entwicklung |

### Szenarien

**Produktion (eigene Zertifikate):**

```yaml
tls:
  enabled: true
  cert_file: /etc/npa/fullchain.pem
  key_file: /etc/npa/privkey.pem
  auto_generate: false
```

**Entwicklung (selbstsigniert):**

```yaml
tls:
  enabled: true
  auto_generate: true
```

**Kein TLS (nur fuer Tests):**

```yaml
tls:
  enabled: false
```

---

## Server-Konfiguration

```yaml
server:
  addr: "0.0.0.0"
  port: 8443
  workers: 1
  cors_origins:
    - "*"
  rate_limit: 1000
  request_timeout: 30.0
  max_request_size: 10485760
```

| Feld | Typ | Default | Env-Variable | Beschreibung |
|------|-----|---------|-------------|-------------|
| `addr` | str | `"0.0.0.0"` | `NPA_SERVER_ADDR` | Bind-Adresse |
| `port` | int | `8443` | `NPA_SERVER_PORT` | Port (8443 HTTPS, 8181 HTTP) |
| `workers` | int | `1` | `NPA_SERVER_WORKERS` | Anzahl Worker-Prozesse |
| `cors_origins` | list[str] | `["*"]` | `NPA_SERVER_CORS_ORIGINS` | Erlaubte CORS-Origins |
| `rate_limit` | int | `1000` | `NPA_SERVER_RATE_LIMIT` | Max. Requests/Minute pro Client |
| `request_timeout` | float | `30.0` | `NPA_SERVER_REQUEST_TIMEOUT` | Request-Timeout in Sekunden |
| `max_request_size` | int | `10485760` | `NPA_SERVER_MAX_REQUEST_SIZE` | Max. Request-Groesse (Bytes, Default 10 MB) |

### Produktions-Empfehlungen

```yaml
server:
  addr: "0.0.0.0"
  port: 8443
  workers: 4
  cors_origins:
    - "https://dashboard.example.com"
  rate_limit: 5000
  request_timeout: 10.0
```

---

## Authentifizierung

```yaml
auth:
  enabled: true
  token_type: "bearer"
  jwt_secret: "my-super-secret-key"
  jwt_algorithm: "HS256"
  api_keys:
    - "key-for-service-a"
    - "key-for-service-b"
  ui_username: "admin"
  ui_password: "sicheres-passwort"
```

| Feld | Typ | Default | Env-Variable | Beschreibung |
|------|-----|---------|-------------|-------------|
| `enabled` | bool | `false` | `NPA_AUTH_ENABLED` | API-Authentifizierung aktivieren |
| `token_type` | str | `"bearer"` | `NPA_AUTH_TOKEN_TYPE` | Token-Typ: `"bearer"` oder `"client_cert"` |
| `jwt_secret` | str | `""` | `NPA_AUTH_JWT_SECRET` | JWT-Signaturschluessel |
| `jwt_algorithm` | str | `"HS256"` | `NPA_AUTH_JWT_ALGORITHM` | JWT-Algorithmus |
| `api_keys` | list[str] | `[]` | `NPA_AUTH_API_KEYS` | Statische API-Schluessel |
| `ui_username` | str | `"admin"` | `NPA_AUTH_UI_USERNAME` | Web-Dashboard Benutzername |
| `ui_password` | str | `"admin"` | `NPA_AUTH_UI_PASSWORD` | Web-Dashboard Passwort |

### Authentifizierungsmethoden

**1. Bearer Token (API-Key):**

```bash
curl -sk -H "Authorization: Bearer key-for-service-a" \
  https://localhost:8443/v1/data
```

**2. JWT Token:**

```bash
curl -sk -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  https://localhost:8443/v1/data
```

**3. Web-Dashboard (Cookie):**

```bash
curl -sk -X POST https://localhost:8443/v1/ui/login \
  -d '{"username": "admin", "password": "sicheres-passwort"}'
```

### Ausgenommene Pfade

Diese Pfade erfordern nie Authentifizierung:

- `/health`, `/health/live`, `/health/ready`
- `/v1/docs`, `/v1/redoc`
- `/openapi.json`

### Sicherheitshinweise

- `ui_password` unbedingt in Produktion aendern!
- `jwt_secret` mindestens 32 Zeichen, zufaellig generiert
- API-Keys ueber Umgebungsvariablen setzen, nicht in Konfigurationsdateien
- API-Key-Vergleich ist timing-safe (constant-time)

---

## Storage

```yaml
storage:
  backend: "memory"
  disk_path: "npa_data.db"
```

| Feld | Typ | Default | Env-Variable | Beschreibung |
|------|-----|---------|-------------|-------------|
| `backend` | str | `"memory"` | `NPA_STORAGE_BACKEND` | Backend: `"memory"` oder `"disk"` |
| `disk_path` | Path | `"npa_data.db"` | `NPA_STORAGE_DISK_PATH` | Pfad zur SQLite-Datenbank |

### InMemory (Default)

```yaml
storage:
  backend: "memory"
```

- Thread-safe mit RLock und Copy-on-Write
- Schnellste Option fuer Policy-Evaluierung
- Daten gehen beim Neustart verloren
- Snapshot-Isolation fuer konsistente Reads

### Disk (SQLite)

```yaml
storage:
  backend: "disk"
  disk_path: "/var/lib/npa/data.db"
```

- Persistente Speicherung mit SQLite
- WAL-Modus (Write-Ahead Logging) fuer Concurrency
- Ueberlebt Neustarts
- Leicht langsamer als Memory

---

## Bundles

Automatisches Laden und Aktualisieren von Policy-Bundles.

```yaml
bundles:
  - name: "authz"
    url: "https://bundle-server.example.com/authz/bundle.tar.gz"
    polling_interval: 60
    auth_token: "bundle-download-token"
  - name: "rbac"
    url: "https://bundle-server.example.com/rbac/bundle.tar.gz"
    polling_interval: 120
```

| Feld | Typ | Default | Env-Variable | Beschreibung |
|------|-----|---------|-------------|-------------|
| `name` | str | `"default"` | `NPA_BUNDLE_NAME` | Bundle-Bezeichner |
| `url` | str | `""` | `NPA_BUNDLE_URL` | Download-URL |
| `polling_interval` | int | `60` | `NPA_BUNDLE_POLLING_INTERVAL` | Polling-Intervall in Sekunden |
| `auth_token` | str | `""` | `NPA_BUNDLE_AUTH_TOKEN` | Auth-Token fuer den Download |

### Lokale Bundles (CLI)

```bash
npa run -b ./policies -b ./roles
```

---

## Logging

```yaml
logging:
  level: "INFO"
  format: "json"
  decision_log: false
```

| Feld | Typ | Default | Env-Variable | Beschreibung |
|------|-----|---------|-------------|-------------|
| `level` | str | `"INFO"` | `NPA_LOG_LEVEL` | Log-Level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `format` | str | `"json"` | `NPA_LOG_FORMAT` | Format: `"json"` oder `"text"` |
| `decision_log` | bool | `false` | `NPA_LOG_DECISION_LOG` | Decision-Logging aktivieren |

### Log-Levels

| Level | Beschreibung |
|-------|-------------|
| `DEBUG` | Alle Details inkl. Query-Evaluation |
| `INFO` | Normaler Betrieb, Startup-Info |
| `WARNING` | Potenzielle Probleme |
| `ERROR` | Nur Fehler |

---

## Labels

Benutzerdefinierte Labels fuer Status- und Discovery-Endpoints:

```yaml
labels:
  environment: "production"
  region: "eu-west-1"
  team: "platform"
  version: "v1.2.3"
```

Labels erscheinen in:
- `GET /v1/status`
- `GET /v1/config`
- Decision-Logs (wenn aktiviert)

---

## Umgebungsvariablen

Alle Konfigurationsoptionen koennen per Umgebungsvariable gesetzt werden.
Das Praefix ist `NPA_`, gefolgt vom Abschnitt und Feldnamen.

### Uebersicht

```bash
# TLS
NPA_TLS_ENABLED=true
NPA_TLS_CERT_FILE=/etc/npa/cert.pem
NPA_TLS_KEY_FILE=/etc/npa/key.pem

# Server
NPA_SERVER_ADDR=0.0.0.0
NPA_SERVER_PORT=8443
NPA_SERVER_WORKERS=4

# Auth
NPA_AUTH_ENABLED=true
NPA_AUTH_JWT_SECRET=my-secret
NPA_AUTH_UI_PASSWORD=sicheres-passwort

# Storage
NPA_STORAGE_BACKEND=memory

# Logging
NPA_LOG_LEVEL=INFO
NPA_LOG_FORMAT=json
NPA_LOG_DECISION_LOG=true
```

### Docker-Compose Beispiel

```yaml
services:
  npa:
    image: npa:latest
    environment:
      NPA_SERVER_PORT: "8443"
      NPA_AUTH_ENABLED: "true"
      NPA_AUTH_JWT_SECRET: "${JWT_SECRET}"
      NPA_AUTH_UI_PASSWORD: "${ADMIN_PASSWORD}"
      NPA_STORAGE_BACKEND: "disk"
      NPA_STORAGE_DISK_PATH: "/data/npa.db"
      NPA_LOG_LEVEL: "INFO"
    volumes:
      - npa-data:/data
    ports:
      - "8443:8443"
```

---

## Vollstaendiges Beispiel

### Produktions-Konfiguration (npa.yaml)

```yaml
tls:
  enabled: true
  cert_file: /etc/npa/tls/cert.pem
  key_file: /etc/npa/tls/key.pem
  min_version: "TLSv1.2"
  auto_generate: false

server:
  addr: "0.0.0.0"
  port: 8443
  workers: 4
  cors_origins:
    - "https://dashboard.internal.example.com"
  rate_limit: 5000
  request_timeout: 10.0
  max_request_size: 5242880  # 5 MB

auth:
  enabled: true
  token_type: "bearer"
  jwt_secret: "${NPA_AUTH_JWT_SECRET}"  # Via Env-Variable
  jwt_algorithm: "HS256"
  api_keys:
    - "${NPA_API_KEY_SERVICE_A}"
    - "${NPA_API_KEY_SERVICE_B}"
  ui_username: "admin"
  ui_password: "${NPA_AUTH_UI_PASSWORD}"

storage:
  backend: "disk"
  disk_path: "/var/lib/npa/data.db"

bundles:
  - name: "core-policies"
    url: "https://bundles.internal.example.com/core/bundle.tar.gz"
    polling_interval: 30
    auth_token: "${NPA_BUNDLE_AUTH_TOKEN}"

logging:
  level: "INFO"
  format: "json"
  decision_log: true

labels:
  environment: "production"
  cluster: "eu-west-1"
  managed_by: "platform-team"
```

### Entwicklungs-Konfiguration (npa-dev.yaml)

```yaml
tls:
  enabled: true
  auto_generate: true

server:
  port: 8443
  workers: 1
  cors_origins:
    - "*"

auth:
  enabled: false

storage:
  backend: "memory"

logging:
  level: "DEBUG"
  format: "text"
  decision_log: true

labels:
  environment: "development"
```
