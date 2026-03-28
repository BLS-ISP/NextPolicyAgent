# NPA SDK-Referenz

Python SDK zum Einbetten der NPA Policy-Engine in eigene Anwendungen --
ohne den Server starten zu muessen.

---

## Inhaltsverzeichnis

1. [Installation](#installation)
2. [Schnellstart](#schnellstart)
3. [NPA-Klasse](#npa-klasse)
4. [Methoden-Referenz](#methoden-referenz)
5. [Fehlerbehandlung](#fehlerbehandlung)
6. [Cache-Konfiguration](#cache-konfiguration)
7. [Thread-Sicherheit](#thread-sicherheit)
8. [Praxisbeispiele](#praxisbeispiele)

---

## Installation

```bash
pip install npa
```

## Schnellstart

```python
from npa.sdk.sdk import NPA

# Engine erstellen
engine = NPA()

# Policy laden
engine.load_policy("authz", '''
    package authz
    import rego.v1

    default allow = false

    allow if {
        input.role == "admin"
    }
''')

# Policy evaluieren
result = engine.decide("data.authz.allow", {"role": "admin"})
print(result)  # True

# Boolean-Convenience
allowed = engine.decide_bool("data.authz.allow", {"role": "guest"})
print(allowed)  # False
```

---

## NPA-Klasse

### Konstruktor

```python
NPA(cache_size: int = 10_000, cache_ttl: float = 300.0)
```

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `cache_size` | int | 10.000 | Maximale Anzahl Cache-Eintraege |
| `cache_ttl` | float | 300.0 | Cache-TTL in Sekunden (5 Min.) |

```python
# Mit benutzerdefiniertem Cache
engine = NPA(cache_size=50_000, cache_ttl=600.0)
```

---

## Methoden-Referenz

### load_policy(policy_id, raw_rego)

Laedt oder aktualisiert eine einzelne Rego-Policy.

```python
load_policy(policy_id: str, raw_rego: str) -> None
```

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `policy_id` | str | Eindeutiger Bezeichner (z.B. Dateiname) |
| `raw_rego` | str | Rego-Quellcode |

```python
engine.load_policy("rbac", '''
    package rbac
    import rego.v1
    admin if { input.role == "admin" }
''')
```

**Hinweis:** Nach jedem `load_policy` werden alle Policies neu kompiliert.

---

### load_policies(policies)

Laedt mehrere Policies auf einmal (effizienter als einzeln).

```python
load_policies(policies: dict[str, str]) -> None
```

```python
engine.load_policies({
    "authz": "package authz\ndefault allow = false\n...",
    "rbac": "package rbac\n...",
    "network": "package network\n...",
})
```

---

### remove_policy(policy_id)

Entfernt eine Policy.

```python
remove_policy(policy_id: str) -> None
```

```python
engine.remove_policy("rbac")
```

---

### load_data(path, data)

Laedt Daten an einem bestimmten Pfad im Datenbaum.

```python
load_data(path: list[str], data: Any) -> None
```

```python
# Daten unter data.users laden
engine.load_data(["users"], {
    "alice": {"role": "admin", "email": "alice@example.com"},
    "bob": {"role": "viewer"}
})

# Daten unter data.config.features laden
engine.load_data(["config", "features"], {
    "audit_logging": True,
    "max_retries": 3
})
```

---

### set_data(data)

Ersetzt das gesamte Datendokument.

```python
set_data(data: dict[str, Any]) -> None
```

```python
engine.set_data({
    "users": {"alice": {"role": "admin"}},
    "roles": {"admin": {"permissions": ["read", "write", "delete"]}}
})
```

**Achtung:** Ueberschreibt alle vorhandenen Daten!

---

### load_bundle(bundle)

Laedt Policies und Daten aus einem Bundle-Objekt.

```python
load_bundle(bundle: Bundle) -> None
```

```python
from npa.bundle.bundle import load_bundle_from_bytes

data = open("policies.tar.gz", "rb").read()
bundle = load_bundle_from_bytes(data)
engine.load_bundle(bundle)
```

---

### load_bundle_from_file(path)

Laedt ein Bundle direkt aus einer `.tar.gz`-Datei.

```python
load_bundle_from_file(path: str | Path) -> None
```

```python
engine.load_bundle_from_file("policies.tar.gz")
engine.load_bundle_from_file(Path("/opt/npa/bundles/authz.tar.gz"))
```

---

### load_bundle_from_dir(directory)

Laedt ein Bundle aus einem Verzeichnis.

```python
load_bundle_from_dir(directory: str | Path) -> None
```

```python
engine.load_bundle_from_dir("./policies")
```

Laedt automatisch:
- Alle `.rego`-Dateien als Policies
- Alle `data.json`-Dateien als Daten
- `manifest.json` als Bundle-Manifest

---

### decide(query, input_data)

Evaluiert eine Policy-Query.

```python
decide(query: str, input_data: Any = None) -> Any
```

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `query` | str | (erforderlich) | Rego-Query (z.B. `"data.authz.allow"`) |
| `input_data` | Any | None | Input-Dokument fuer die Evaluierung |

**Rueckgabewerte:**

| Ergebnis | Beschreibung |
|----------|-------------|
| `True` / `False` | Boolesche Policy-Entscheidung |
| `dict`, `list`, etc. | Strukturierte Ergebnisse |
| `None` | Policy ist undefiniert (keine Regel matched) |

```python
# Boolean-Ergebnis
result = engine.decide("data.authz.allow", {"role": "admin"})
# True

# Strukturiertes Ergebnis
result = engine.decide("data.authz.user_permissions", {"user": "alice"})
# {"read": True, "write": True, "delete": False}

# Undefiniert (keine Regel matched)
result = engine.decide("data.nonexistent.rule")
# None
```

**Wirft** `NPAError` bei Evaluierungsfehlern.

---

### decide_bool(query, input_data)

Convenience-Methode -- gibt immer `bool` zurueck.

```python
decide_bool(query: str, input_data: Any = None) -> bool
```

| decide() Ergebnis | decide_bool() Ergebnis |
|-------------------|----------------------|
| `True` | `True` |
| `False` | `False` |
| `None` (undefiniert) | `False` |
| Truthy-Wert | `True` |
| Falsy-Wert | `False` |

```python
if engine.decide_bool("data.authz.allow", {"role": input_role}):
    grant_access()
else:
    deny_access()
```

---

### cache_stats (Property)

Gibt Cache-Statistiken zurueck.

```python
stats = engine.cache_stats
# {"hits": 150, "misses": 42, "size": 192, "max_size": 10000}
```

---

### clear_cache()

Leert den Query-Cache.

```python
engine.clear_cache()
```

---

## Fehlerbehandlung

```python
from npa.sdk.sdk import NPA, NPAError

engine = NPA()

# Parse-Fehler beim Laden
try:
    engine.load_policy("broken", "package broken\nthis is not valid rego")
except NPAError as e:
    print(f"Policy-Fehler: {e}")

# Evaluierungsfehler
try:
    result = engine.decide("data.example.allow", {"user": "admin"})
except NPAError as e:
    print(f"Evaluierungsfehler: {e}")
```

### NPAError

Die einzige Exception-Klasse der SDK. Wird geworfen bei:

- **Parse-Fehlern**: Ungueltiger Rego-Quellcode
- **Compile-Fehlern**: Widerspruechliche Regeln, ungueltige Referenzen
- **Evaluierungsfehlern**: Runtime-Fehler waehrend der Auswertung
- **Kein Policy geladen**: `decide()` ohne vorheriges `load_policy()`

---

## Cache-Konfiguration

NPA cached Query-Ergebnisse automatisch fuer bessere Performance.

```python
# Grosser Cache fuer High-Throughput
engine = NPA(cache_size=100_000, cache_ttl=600.0)

# Kleiner Cache oder kein Caching
engine = NPA(cache_size=0, cache_ttl=0)

# Stats pruefen
print(engine.cache_stats)
# {"hits": 500, "misses": 50, "size": 550, "max_size": 100000}

# Cache leeren (z.B. nach Daten-Update)
engine.set_data(new_data)
engine.clear_cache()
```

### Wann Cache leeren?

- Nach `set_data()` oder `load_data()` -- Datenbaum hat sich geaendert
- Nach `load_policy()` -- Regeln haben sich geaendert
- Periodisch bei haeufig wechselnden Daten

---

## Thread-Sicherheit

Die NPA-Klasse ist thread-safe fuer lesende Operationen nach der Initialisierung:

```python
import threading
from npa.sdk.sdk import NPA

engine = NPA()
engine.load_policy("authz", policy_source)
engine.set_data(data)

# Sicher: Parallele Evaluierungen
def worker(user_role):
    result = engine.decide("data.authz.allow", {"role": user_role})
    return result

threads = [
    threading.Thread(target=worker, args=("admin",)),
    threading.Thread(target=worker, args=("viewer",)),
]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

**Sicher (parallel):**
- `decide()` / `decide_bool()`
- `cache_stats`

**Nicht parallel ausfuehren:**
- `load_policy()` / `load_policies()` / `remove_policy()`
- `load_data()` / `set_data()`
- `load_bundle*()` Methoden

---

## Praxisbeispiele

### HTTP-API-Autorisierung (Flask)

```python
from flask import Flask, request, jsonify
from npa.sdk.sdk import NPA

app = Flask(__name__)
engine = NPA()
engine.load_policy("api_authz", open("policy.rego").read())

@app.before_request
def check_authorization():
    input_data = {
        "method": request.method,
        "path": request.path,
        "user": request.headers.get("X-User", "anonymous"),
        "roles": request.headers.get("X-Roles", "").split(","),
    }
    if not engine.decide_bool("data.api_authz.allow", input_data):
        return jsonify({"error": "forbidden"}), 403
```

### Kubernetes Admission Controller

```python
from npa.sdk.sdk import NPA

engine = NPA()
engine.load_bundle_from_dir("./k8s-policies")

def validate_admission(admission_review: dict) -> dict:
    input_data = admission_review["request"]
    allowed = engine.decide_bool("data.k8s.admission.allow", input_data)
    reasons = engine.decide("data.k8s.admission.deny_reasons", input_data) or []

    return {
        "apiVersion": "admission.k8s.io/v1",
        "kind": "AdmissionReview",
        "response": {
            "uid": input_data["uid"],
            "allowed": allowed,
            "status": {"message": "; ".join(reasons)} if reasons else {}
        }
    }
```

### Feature-Flags

```python
from npa.sdk.sdk import NPA

engine = NPA()
engine.load_policy("features", '''
    package features
    import rego.v1

    enabled(feature) if {
        data.feature_flags[feature].enabled == true
        data.feature_flags[feature].rollout_pct >= input.user_bucket
    }
''')

engine.set_data({
    "feature_flags": {
        "dark_mode": {"enabled": True, "rollout_pct": 100},
        "new_checkout": {"enabled": True, "rollout_pct": 25},
        "beta_api": {"enabled": False, "rollout_pct": 0}
    }
})

# Nutzer in Bucket 15 -> hat new_checkout
engine.decide_bool("data.features.enabled", {
    "args": ["new_checkout"],
    "user_bucket": 15
})
```
