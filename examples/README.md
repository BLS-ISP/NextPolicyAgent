# NPA Policy-Beispiele

Praxisnahe Rego-Policies, die mit dem NPA-Evaluator getestet und funktionsfähig sind.
Jedes Beispiel enthält eine Policy (`policy.rego`), Testdaten (`data.json`) und eine Beispiel-Eingabe (`input.json`).

---

## Schnellstart

```bash
# Beispiel auswerten (ganzes Verzeichnis laden)
npa eval -d examples/rbac/ -i examples/rbac/input.json "data.rbac.authz"

# Einzelne Regel abfragen
npa eval -d examples/rbac/ -i examples/rbac/input.json "data.rbac.authz.allow"

# Per REST-API
curl -k -X POST https://localhost:8443/v1/data/rbac/authz \
  -H "Content-Type: application/json" \
  -d '{"input": {"user": "alice", "action": "write", "resource": "reports"}}'
```

---

## Beispiele im Überblick

| # | Beispiel | Beschreibung | Package |
|---|----------|-------------|---------|
| 1 | [RBAC](#1-rbac--rollenbasierte-zugriffskontrolle) | Rollen → Berechtigungen | `rbac.authz` |
| 2 | [HTTP API Auth](#2-http-api-autorisierung) | REST-Endpunkte schützen | `httpapi.authz` |
| 3 | [Kubernetes Admission](#3-kubernetes-admission-control) | Pod-Validierung | `kubernetes.admission` |
| 4 | [Network Firewall](#4-netzwerk-firewall) | IP/Port-Regeln | `network.firewall` |
| 5 | [JWT Validation](#5-jwt-token-validierung) | Token-Prüfung & Claims | `jwt.validation` |
| 6 | [Data Filtering](#6-daten-filterung) | Comprehensions & Aggregation | `filtering` |

---

## 1. RBAC – Rollenbasierte Zugriffskontrolle

**Verzeichnis:** `examples/rbac/`

Klassisches RBAC-Modell: Benutzer werden Rollen zugewiesen, Rollen haben Berechtigungen (action + resource).

**Rego-Features:** `some ... in`, `default`, `else`-Kette

```bash
# Erwartet: allow = true, reason = "Zugriff erlaubt"
npa eval -d examples/rbac/ -i examples/rbac/input.json "data.rbac.authz"
```

**Dateien:**
- `policy.rego` – Rollenprüfung über `data.rbac.bindings` und `data.rbac.grants`
- `data.json` – Benutzer-Rollen-Zuordnung und Rollen-Berechtigungen
- `input.json` – Anfrage: Alice möchte `write` auf `reports`

---

## 2. HTTP API Autorisierung

**Verzeichnis:** `examples/http-api-authz/`

Schützt REST-API-Endpunkte mit gestaffelten Zugriffsregeln: öffentliche Routen, authentifizierte Routen und Admin-only-Routen.

**Rego-Features:** `in` (Membership-Test), `count()`, `else`-Kette, Pfad-Matching

```bash
# Erwartet: allow = true, status_code = 200
npa eval -d examples/http-api-authz/ -i examples/http-api-authz/input.json "data.httpapi.authz"
```

**Dateien:**
- `policy.rego` – Endpunkt-Regeln nach Methode, Pfad und Rolle
- `data.json` – Admin-Liste
- `input.json` – DELETE /api/v1/users durch Alice (Admin)

---

## 3. Kubernetes Admission Control

**Verzeichnis:** `examples/kubernetes-admission/`

Validiert Kubernetes Pod-Specs: erlaubte Image-Registries, kein Root-User, Pflicht-Labels.

**Rego-Features:** `every ... in`, benutzerdefinierte Funktionen, `startswith()`

```bash
# Erwartet: true (valider Pod)
npa eval -d examples/kubernetes-admission/policy.rego \
         -i examples/kubernetes-admission/input-valid.json \
         "data.kubernetes.admission.allow"

# Erwartet: false (ungültiger Pod)
npa eval -d examples/kubernetes-admission/policy.rego \
         -i examples/kubernetes-admission/input-invalid.json \
         "data.kubernetes.admission.allow"
```

**Dateien:**
- `policy.rego` – Admission-Regeln mit `every`-Schleifen und Registry-Funktionen
- `input-valid.json` – Pod mit ghcr.io-Image, UID 1000, alle Labels
- `input-invalid.json` – Pod mit unerlaubter Registry, Root-User, fehlende Labels

---

## 4. Netzwerk-Firewall

**Verzeichnis:** `examples/network-firewall/`

IP-basierte Firewall-Regeln mit CIDR-Prüfung und Port-Whitelists für verschiedene Protokolle.

**Rego-Features:** `net.cidr_contains()`, `in` (Membership in Liste)

```bash
# Erwartet: allow = true, decision = "internal-traffic-allowed"
npa eval -d examples/network-firewall/ \
         -i examples/network-firewall/input.json \
         "data.network.firewall"
```

**Dateien:**
- `policy.rego` – CIDR-Regeln für 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
- `input.json` – 10.0.1.50 → 10.0.2.100:443/tcp (intern, erlaubt)

---

## 5. JWT Token Validierung

**Verzeichnis:** `examples/jwt-validation/`

Dekodiert JWT-Tokens, prüft den Issuer gegen eine Trusted-Liste und validiert die Ablaufzeit.

**Rego-Features:** `io.jwt.decode()`, Index-Zugriff `[1]`, `some ... in`, `:=` (Zuweisung)

```bash
# Erwartet: allow = true, reason = "Token gueltig - Zugriff erlaubt"
npa eval -d examples/jwt-validation/ \
         -i examples/jwt-validation/input.json \
         "data.jwt.validation"

# Nur Claims extrahieren
npa eval -d examples/jwt-validation/ \
         -i examples/jwt-validation/input.json \
         "data.jwt.validation.claims"
```

**Dateien:**
- `policy.rego` – Token-Decode, Issuer-Check, Expiry-Check, Claims-Extraktion
- `data.json` – Liste vertrauenswürdiger Issuers
- `input.json` – Gültiger JWT-Token (Base64-kodiert)

---

## 6. Daten-Filterung

**Verzeichnis:** `examples/data-filtering/`

Zeigt wie man mit Rego-Comprehensions Daten filtern, projizieren und aggregieren kann – nützlich für datengetriebene APIs.

**Rego-Features:** Array-Comprehensions `[x | ...]`, `count()`, `sprintf()`, Objekt-Projektion

```bash
# Alle Regeln auswerten
npa eval -d examples/data-filtering/ \
         -i examples/data-filtering/input.json \
         "data.filtering"

# Nur gefilterte Mitarbeiter der Abteilung
npa eval -d examples/data-filtering/ \
         -i examples/data-filtering/input.json \
         "data.filtering.department_employees"

# Zusammenfassung
npa eval -d examples/data-filtering/ \
         -i examples/data-filtering/input.json \
         "data.filtering.summary"
```

**Dateien:**
- `policy.rego` – Filter, Projektionen, Aggregationen, Zugriffskontrolle
- `data.json` – 7 Mitarbeiter mit Abteilung, Freigabestufe und Status
- `input.json` – Abfrage für Abteilung "engineering" als Admin

---

## Rego-Kurzreferenz (NPA-kompatibel)

| Feature | Syntax | Beispiel |
|---------|--------|----------|
| Default-Wert | `default x = false` | `default allow = false` |
| Iteration | `some x in data.items` | `some user in data.rbac.bindings` |
| Bedingung | `x if { ... }` | `allow if { input.role == "admin" }` |
| Else-Kette | `x = "a" if { ... } else = "b"` | Status-Codes, Begründungen |
| Every-Loop | `every x in list { ... }` | K8s Container-Validierung |
| Comprehension | `[x \| some x in data.items; cond]` | Daten filtern & projizieren |
| Membership | `x in [a, b, c]` | Methoden- oder Port-Check |
| Funktionen | `f(x) if { ... }` | `allowed_image(img)` |
| Builtins | `net.cidr_contains()`, `count()`, ... | 192+ verfügbare Builtins |
| JWT | `io.jwt.decode(token)` | Token-Claims extrahieren |
| String | `startswith()`, `sprintf()` | Image-Registry, Formatierung |

---

## Eigene Policies erstellen

1. **Verzeichnis anlegen** mit `policy.rego`, optional `data.json`
2. **Package definieren:** `package mein.paket`
3. **Imports:** `import future.keywords.if` / `import future.keywords.in` / `import future.keywords.every`
4. **Testen:** `npa eval -d mein-verzeichnis/ -i input.json "data.mein.paket"`

**Tipps:**
- Verwende `some x in data.*` oder `some x in input.*` für Iterationen
- Verwende `else`-Ketten für bedingte Werte statt `not`
- Inline komplexe Bedingungen direkt in die Regel statt auf andere Regeln zu verweisen
- Verwende `%s` statt `%v` in `sprintf()`-Aufrufen
