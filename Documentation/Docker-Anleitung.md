# NPA Docker-Anleitung

Vollständige Anleitung zur Nutzung von NPA (Next Policy Agent) als Docker-Container.

---

## Inhaltsverzeichnis

1. [Voraussetzungen](#voraussetzungen)
2. [Schnellstart](#schnellstart)
3. [Image bauen](#image-bauen)
4. [Container starten](#container-starten)
5. [Docker Compose](#docker-compose)
6. [Konfiguration](#konfiguration)
7. [TLS / HTTPS](#tls--https)
8. [Policies & Daten einbinden](#policies--daten-einbinden)
9. [Authentifizierung](#authentifizierung)
10. [Health Checks](#health-checks)
11. [Logging & Debugging](#logging--debugging)
12. [Produktionsbetrieb](#produktionsbetrieb)
13. [Beispiele](#beispiele)
14. [Troubleshooting](#troubleshooting)

---

## Voraussetzungen

- **Docker** ≥ 20.10 (oder Docker Desktop)
- **Docker Compose** ≥ 2.0 (optional, im Docker Desktop enthalten)
- Rechner mit **amd64**- oder **arm64**-Architektur

```bash
# Docker-Version prüfen
docker --version
docker compose version
```

---

## Schnellstart

```bash
# 1. Repository klonen
git clone https://github.com/BLS-ISP/NextPolicyAgent.git
cd NextPolicyAgent

# 2. Image bauen
docker build -t npa:latest .

# 3. Container starten
docker run -d -p 8443:8443 --name npa npa:latest

# 4. Testen
curl -sk https://localhost:8443/health
# Erwartet: {}
```

Das war's — NPA läuft mit automatisch generiertem TLS-Zertifikat.

---

## Image bauen

### Standard-Build

```bash
docker build -t npa:latest .
```

### Mit Custom-Tag

```bash
docker build -t npa:1.0.0 .
docker build -t meine-registry.example.com/npa:latest .
```

### Build-Details

Das Image basiert auf **Fedora 41** und nutzt einen Multi-Stage-Build:

| Stage | Inhalt | Zweck |
|-------|--------|-------|
| `builder` | Python 3, pip, gcc, python3-devel | Abhängigkeiten kompilieren |
| `runtime` | Python 3 (lean) | Nur Laufzeit-Minimum (~300 MB) |

---

## Container starten

### Minimal (Auto-TLS)

```bash
docker run -d -p 8443:8443 --name npa npa:latest
```

NPA generiert automatisch ein selbstsigniertes TLS-Zertifikat.

### Mit eigenen TLS-Zertifikaten

```bash
docker run -d -p 8443:8443 \
  -v /pfad/zu/certs:/certs:ro \
  -e NPA_TLS_CERT_FILE=/certs/server.crt \
  -e NPA_TLS_KEY_FILE=/certs/server.key \
  --name npa npa:latest
```

### Mit Policies und Daten

```bash
docker run -d -p 8443:8443 \
  -v ./policies:/policies:ro \
  -v ./data:/data:ro \
  --name npa npa:latest
```

### Ohne TLS (nur für Entwicklung!)

```bash
docker run -d -p 8181:8181 \
  --name npa npa:latest \
  --addr 0.0.0.0:8181 --no-tls --log-level debug
```

### Container stoppen

```bash
docker stop npa
docker rm npa
```

---

## Docker Compose

### Standard-Setup

```bash
# Starten
docker compose up -d

# Neu bauen und starten
docker compose up -d --build

# Logs verfolgen
docker compose logs -f npa

# Stoppen
docker compose down
```

### docker-compose.yml anpassen

Die mitgelieferte `docker-compose.yml` enthält alle gängigen Optionen als Kommentare.
Wichtige Einstellungen:

```yaml
services:
  npa:
    build: .
    ports:
      - "8443:8443"              # HTTPS
    volumes:
      - ./policies:/policies:ro  # Policies einbinden
      - ./data:/data:ro          # Daten einbinden
      - ./bundles:/bundles:ro    # Bundles einbinden
      # - ./certs:/certs:ro      # Eigene TLS-Zertifikate
    environment:
      - NPA_LOGGING_LEVEL=INFO
      # - NPA_AUTH_ENABLED=true
      # - NPA_AUTH_UI_USERNAME=admin
      # - NPA_AUTH_UI_PASSWORD=sicheresPasswort
    restart: unless-stopped
```

---

## Konfiguration

NPA wird vollständig über **Umgebungsvariablen** konfiguriert (Prefix `NPA_`).

### Server

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `NPA_SERVER_ADDR` | `0.0.0.0` | Bind-Adresse |
| `NPA_SERVER_PORT` | `8443` | Server-Port |
| `NPA_SERVER_WORKERS` | `1` | Uvicorn-Worker |
| `NPA_SERVER_CORS_ORIGINS` | `["*"]` | Erlaubte CORS-Origins |
| `NPA_SERVER_RATE_LIMIT` | `1000` | Requests/Minute pro Client |

### TLS

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `NPA_TLS_ENABLED` | `true` | TLS aktivieren/deaktivieren |
| `NPA_TLS_CERT_FILE` | *(auto)* | Pfad zur Zertifikatsdatei |
| `NPA_TLS_KEY_FILE` | *(auto)* | Pfad zum privaten Schlüssel |
| `NPA_TLS_MIN_VERSION` | `TLSv1.2` | Minimum TLS-Version |
| `NPA_TLS_AUTO_GENERATE` | `true` | Selbstsigniertes Zertifikat generieren |

### Authentifizierung

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `NPA_AUTH_ENABLED` | `false` | API-Auth aktivieren |
| `NPA_AUTH_TOKEN_TYPE` | `bearer` | `bearer` oder `client_cert` |
| `NPA_AUTH_JWT_SECRET` | *(leer)* | JWT-Signaturschlüssel |
| `NPA_AUTH_API_KEYS` | `[]` | Erlaubte API-Keys |
| `NPA_AUTH_UI_USERNAME` | `admin` | Web-UI Benutzername |
| `NPA_AUTH_UI_PASSWORD` | `admin` | Web-UI Passwort |

### Logging

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `NPA_LOGGING_LEVEL` | `INFO` | Log-Level (DEBUG, INFO, WARNING, ERROR) |
| `NPA_LOG_FORMAT` | `json` | Log-Format (`json` oder `text`) |
| `NPA_LOG_DECISION_LOG` | `false` | Decision-Logging aktivieren |

### Storage

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `NPA_STORAGE_BACKEND` | `memory` | `memory` oder `disk` |
| `NPA_STORAGE_DISK_PATH` | `npa_data.db` | SQLite-Datenbankpfad |

### Bundles

| Variable | Standard | Beschreibung |
|----------|----------|-------------|
| `NPA_BUNDLE_URL` | *(leer)* | Bundle-Download-URL |
| `NPA_BUNDLE_POLLING_INTERVAL` | `60` | Polling-Intervall (Sekunden) |
| `NPA_BUNDLE_AUTH_TOKEN` | *(leer)* | Auth-Token für Bundle-Server |

---

## TLS / HTTPS

### Auto-generiertes Zertifikat (Standard)

Ohne Konfiguration generiert NPA beim Start ein selbstsigniertes Zertifikat.
Ideal für **Entwicklung und Tests**.

```bash
docker run -d -p 8443:8443 npa:latest
# Logs zeigen: "Auto-generated dev TLS certificate"
```

> ⚠️ **Nicht für Produktion verwenden!** Browser und Clients zeigen Warnungen.

### Eigene Zertifikate

Für Produktion eigene Zertifikate einbinden:

```bash
# Zertifikate vorbereiten
mkdir certs/
# Eigene cert.pem und key.pem in certs/ ablegen

# Container mit eigenen Zertifikaten
docker run -d -p 8443:8443 \
  -v ./certs:/certs:ro \
  -e NPA_TLS_CERT_FILE=/certs/cert.pem \
  -e NPA_TLS_KEY_FILE=/certs/key.pem \
  --name npa npa:latest
```

### Let's Encrypt mit Reverse Proxy

Für automatische Zertifikate empfehlen wir einen Reverse Proxy:

```yaml
# docker-compose.yml (Beispiel mit Traefik)
services:
  traefik:
    image: traefik:v3
    command:
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.le.acme.tlschallenge=true
      - --certificatesresolvers.le.acme.email=admin@example.com
      - --certificatesresolvers.le.acme.storage=/letsencrypt/acme.json
    ports:
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - letsencrypt:/letsencrypt

  npa:
    build: .
    labels:
      - traefik.enable=true
      - traefik.http.routers.npa.rule=Host(`npa.example.com`)
      - traefik.http.routers.npa.tls.certresolver=le
      - traefik.http.services.npa.loadbalancer.server.scheme=https
      - traefik.http.services.npa.loadbalancer.server.port=8443
    environment:
      - NPA_LOGGING_LEVEL=INFO

volumes:
  letsencrypt:
```

---

## Policies & Daten einbinden

### Via Volume-Mounts

```bash
# Verzeichnisstruktur auf dem Host:
# ./policies/rbac/policy.rego
# ./data/rbac/data.json

docker run -d -p 8443:8443 \
  -v ./policies:/policies:ro \
  -v ./data:/data:ro \
  --name npa npa:latest
```

### Via REST-API zur Laufzeit

Policies und Daten können auch dynamisch über die API geladen werden:

```bash
# Policy hochladen
curl -sk -X PUT https://localhost:8443/v1/policies/mypolicy \
  -H "Content-Type: text/plain" \
  -d 'package mypolicy
default allow = false
allow if { input.role == "admin" }'

# Daten setzen
curl -sk -X PUT https://localhost:8443/v1/data/users \
  -H "Content-Type: application/json" \
  -d '{"admins": ["alice", "bob"]}'

# Policy evaluieren
curl -sk -X POST https://localhost:8443/v1/data/mypolicy/allow \
  -H "Content-Type: application/json" \
  -d '{"input": {"role": "admin"}}'
# → {"result": true}
```

### Via Bundles

```bash
docker run -d -p 8443:8443 \
  -v ./bundles:/bundles:ro \
  --name npa npa:latest
```

---

## Authentifizierung

### Web-UI Passwort ändern

```bash
docker run -d -p 8443:8443 \
  -e NPA_AUTH_UI_USERNAME=meinadmin \
  -e NPA_AUTH_UI_PASSWORD=sicheresPasswort123 \
  --name npa npa:latest
```

### API-Auth aktivieren

```bash
docker run -d -p 8443:8443 \
  -e NPA_AUTH_ENABLED=true \
  -e NPA_AUTH_TOKEN_TYPE=bearer \
  -e NPA_AUTH_JWT_SECRET=mein-geheimes-jwt-secret \
  --name npa npa:latest
```

---

## Health Checks

NPA hat einen eingebauten Health-Check auf `/health`:

```bash
# Von außen testen
curl -sk https://localhost:8443/health
# → {}

# Docker Health-Status prüfen
docker inspect --format='{{.State.Health.Status}}' npa
# → healthy
```

### Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8443
    scheme: HTTPS
  initialDelaySeconds: 10
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health
    port: 8443
    scheme: HTTPS
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## Logging & Debugging

### Log-Level anpassen

```bash
# Debug-Logging aktivieren
docker run -d -p 8443:8443 \
  -e NPA_LOGGING_LEVEL=DEBUG \
  --name npa npa:latest

# Logs lesen
docker logs npa
docker logs -f npa  # Live mitverfolgen
```

### Decision-Logging

```bash
docker run -d -p 8443:8443 \
  -e NPA_LOG_DECISION_LOG=true \
  --name npa npa:latest
```

Jede Policy-Entscheidung wird geloggt (Decision-ID, Input, Result, Dauer).

---

## Produktionsbetrieb

### Empfohlene Konfiguration

```bash
docker run -d \
  --name npa \
  --restart unless-stopped \
  --memory 512m \
  --cpus 2 \
  -p 8443:8443 \
  -v /etc/npa/certs:/certs:ro \
  -v /etc/npa/policies:/policies:ro \
  -v /etc/npa/data:/data:ro \
  -e NPA_TLS_CERT_FILE=/certs/server.crt \
  -e NPA_TLS_KEY_FILE=/certs/server.key \
  -e NPA_AUTH_ENABLED=true \
  -e NPA_AUTH_JWT_SECRET=prodSecret123 \
  -e NPA_AUTH_UI_PASSWORD=sicheresUiPasswort \
  -e NPA_LOGGING_LEVEL=WARNING \
  -e NPA_SERVER_RATE_LIMIT=500 \
  npa:latest
```

### Checkliste für Produktion

- [ ] Eigene TLS-Zertifikate (nicht selbstsigniert)
- [ ] `NPA_AUTH_ENABLED=true` — API-Authentifizierung aktiv
- [ ] `NPA_AUTH_UI_PASSWORD` — Standard-Passwort `admin` geändert
- [ ] `NPA_AUTH_JWT_SECRET` — sicheres Secret gesetzt
- [ ] `NPA_LOGGING_LEVEL=WARNING` — kein Debug im Produktionsbetrieb
- [ ] `--restart unless-stopped` — Auto-Restart bei Absturz
- [ ] `--memory` und `--cpus` — Ressourcen-Limits gesetzt
- [ ] Volumes mit `:ro` — Policies/Daten schreibgeschützt
- [ ] Health-Monitoring eingerichtet

### Image in Registry pushen

```bash
# Taggen
docker tag npa:latest meine-registry.example.com/npa:1.0.0

# Pushen
docker push meine-registry.example.com/npa:1.0.0
```

---

## Beispiele

Das Image enthält 6 fertige Policy-Beispiele unter `/examples/`:

| Beispiel | Package | Beschreibung |
|----------|---------|-------------|
| `rbac/` | `rbac.authz` | Rollenbasierte Zugriffskontrolle |
| `http-api-authz/` | `httpapi.authz` | REST-API Endpunktschutz |
| `kubernetes-admission/` | `kubernetes.admission` | K8s Pod-Validierung |
| `network-firewall/` | `network.firewall` | IP/Port Firewall-Regeln |
| `jwt-validation/` | `jwt.validation` | JWT Token-Prüfung |
| `data-filtering/` | `filtering` | Daten-Filterung & Aggregation |

### Beispiel im Container testen

```bash
# Interaktive Shell im Container
docker exec -it npa bash

# RBAC-Beispiel auswerten
python3 -m npa eval \
  -d /examples/rbac/ \
  -i /examples/rbac/input.json \
  "data.rbac.authz"
```

---

## Troubleshooting

### Container startet nicht

```bash
# Logs prüfen
docker logs npa

# Häufige Ursachen:
# - Port bereits belegt → anderen Port wählen: -p 9443:8443
# - Zertifikatsdatei nicht gefunden → Pfade prüfen
```

### "Connection refused" vom Host

```bash
# Container läuft?
docker ps

# Port-Mapping korrekt?
docker port npa

# Health-Check intern testen
docker exec npa python3 -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
r = urllib.request.urlopen('https://localhost:8443/health', context=ctx)
print(r.status, r.read().decode())
"
```

### SSL-Fehler bei der Verbindung

Das selbstsignierte Zertifikat wird von Clients nicht vertraut:

```bash
# curl: --insecure / -k Flag nutzen
curl -sk https://localhost:8443/health

# Python: SSL-Verifikation deaktivieren
python -c "
import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
r = urllib.request.urlopen('https://localhost:8443/health', context=ctx)
print(r.read().decode())
"

# PowerShell 7+: -SkipCertificateCheck
Invoke-RestMethod https://localhost:8443/health -SkipCertificateCheck
```

> **Hinweis:** PowerShell 5.1 unterstützt `-SkipCertificateCheck` nicht.
> Nutze stattdessen Python oder `curl` für Tests mit selbstsignierten Zertifikaten.

### Image neu bauen (nach Code-Änderungen)

```bash
docker compose up -d --build
# oder
docker build --no-cache -t npa:latest .
```
