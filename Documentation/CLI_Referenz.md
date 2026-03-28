# NPA CLI-Referenz

Vollstaendige Dokumentation aller Kommandozeilen-Befehle von NPA.

```
npa [BEFEHL] [OPTIONEN] [ARGUMENTE]
```

---

## Inhaltsverzeichnis

1. [run -- Server starten](#run)
2. [eval -- Query auswerten](#eval)
3. [check -- Rego-Dateien pruefen](#check)
4. [parse -- AST ausgeben](#parse)
5. [build -- Bundle erstellen](#build)
6. [sign -- Bundle signieren](#sign)
7. [inspect -- Bundle inspizieren](#inspect)
8. [version -- Version anzeigen](#version)
9. [bench -- Benchmark ausfuehren](#bench)
10. [deps -- Abhaengigkeiten anzeigen](#deps)
11. [capabilities -- Faehigkeiten ausgeben](#capabilities)
12. [test -- Rego-Tests ausfuehren](#test)
13. [fmt -- Rego formatieren](#fmt)

---

## run

Startet den NPA-Server.

```bash
npa run [OPTIONEN]
```

### Optionen

| Option | Kurz | Default | Beschreibung |
|--------|------|---------|-------------|
| `--addr` | `-a` | `0.0.0.0:8443` | Adresse und Port (Format: `host:port`) |
| `--config-file` | `-c` | -- | Pfad zur Konfigurationsdatei (YAML/JSON) |
| `--tls-cert-file` | -- | -- | TLS-Zertifikat (PEM) |
| `--tls-private-key-file` | -- | -- | TLS-Privatschluessel (PEM) |
| `--no-tls` | -- | `false` | TLS deaktivieren (nicht empfohlen) |
| `--bundle` | `-b` | -- | Bundle-Pfade laden (mehrfach nutzbar) |
| `--log-level` | -- | `info` | Log-Level: `debug`, `info`, `warning`, `error` |

### Beispiele

```bash
# Standard-Start mit HTTPS
npa run

# Anderer Port
npa run -a 0.0.0.0:9443

# Mit Konfigurationsdatei
npa run -c npa.ini

# Eigene TLS-Zertifikate
npa run --tls-cert-file cert.pem --tls-private-key-file key.pem

# HTTP-Modus (Entwicklung)
npa run --no-tls

# Bundles direkt laden
npa run -b ./policies -b ./roles

# Debug-Log
npa run --log-level debug
```

### Verhalten

- Ohne `--no-tls` startet der Server mit HTTPS auf Port 8443
- Mit `--no-tls` wird der Standard-Port automatisch auf 8181 geaendert
- Selbstsignierte Zertifikate werden automatisch erzeugt, wenn keine angegeben sind
- Die Konfigurationsdatei kann CLI-Optionen ueberschreiben (CLI hat Vorrang)

---

## eval

Wertet eine Rego-Query von der Kommandozeile aus.

```bash
npa eval [OPTIONEN] QUERY
```

### Argumente

| Argument | Beschreibung |
|----------|-------------|
| `QUERY` | Rego-Query zum Auswerten (z.B. `data.authz.allow`) |

### Optionen

| Option | Kurz | Default | Beschreibung |
|--------|------|---------|-------------|
| `--input` | `-i` | -- | Input-Datei (JSON) |
| `--data` | `-d` | -- | Daten-/Policy-Dateien oder -Verzeichnisse (mehrfach) |
| `--bundle` | `-b` | -- | Bundle-Pfade (mehrfach) |
| `--format` | `-f` | `json` | Ausgabeformat: `json`, `raw`, `pretty` |

### Beispiele

```bash
# Einfache Berechnung
npa eval "1 + 2"
# 3

# Policy mit Input evaluieren
npa eval -d ./policies -i input.json "data.authz.allow"

# Mehrere Datenquellen
npa eval -d policies/ -d data/ "data.authz.users"

# Bundle verwenden
npa eval -b ./bundle "data.authz.allow" -i input.json

# Huebsche Ausgabe
npa eval -f pretty "data.authz.allow" -d policies/
```

### Daten-Laden

Wenn `-d` verwendet wird, laedt NPA:
- `.rego`-Dateien als Policies
- `.json`-Dateien als Daten
- Verzeichnisse rekursiv (alle `.rego` und `data.json`)

---

## check

Prueft Rego-Dateien auf Syntaxfehler.

```bash
npa check [OPTIONEN] PFADE...
```

### Argumente

| Argument | Beschreibung |
|----------|-------------|
| `PFADE` | Rego-Dateien oder Verzeichnisse (ein oder mehrere) |

### Optionen

| Option | Default | Beschreibung |
|--------|---------|-------------|
| `--strict` | `false` | Strikten Modus aktivieren |

### Beispiele

```bash
# Einzelne Datei pruefen
npa check policy.rego

# Ganzes Verzeichnis
npa check policies/

# Mehrere Pfade
npa check policies/ rules/ helpers.rego
```

### Exit-Codes

| Code | Bedeutung |
|------|-----------|
| 0 | Alle Dateien fehlerfrei |
| 1 | Syntaxfehler gefunden |

---

## parse

Parst eine Rego-Datei und gibt den AST (Abstract Syntax Tree) aus.

```bash
npa parse [OPTIONEN] DATEI
```

### Argumente

| Argument | Beschreibung |
|----------|-------------|
| `DATEI` | Rego-Datei zum Parsen |

### Optionen

| Option | Kurz | Default | Beschreibung |
|--------|------|---------|-------------|
| `--format` | `-f` | `json` | Ausgabeformat |

### Beispiel

```bash
npa parse policy.rego
```

Gibt den vollstaendigen AST als JSON aus -- nuetzlich fuer Debugging und Tooling.

---

## build

Erstellt ein Policy-Bundle (tar.gz).

```bash
npa build [OPTIONEN] PFADE...
```

### Argumente

| Argument | Beschreibung |
|----------|-------------|
| `PFADE` | Rego-Dateien oder Verzeichnisse zum Buendeln |

### Optionen

| Option | Kurz | Default | Beschreibung |
|--------|------|---------|-------------|
| `--output` | `-o` | `bundle.tar.gz` | Ausgabedatei |
| `--revision` | `-r` | `""` | Bundle-Revision (z.B. `v1.2.3`) |

### Beispiele

```bash
# Standard-Bundle bauen
npa build policies/

# Mit Revision und eigenem Dateinamen
npa build -o authz-v1.tar.gz -r v1.0.0 policies/ data/

# Mehrere Quellen
npa build policies/ roles/ exceptions/
```

### Bundle-Inhalt

Das Bundle enthaelt:
- Alle `.rego`-Dateien (relativ zum Quellverzeichnis)
- Alle `data.json`-Dateien
- Ein Manifest mit Revision und Roots

---

## sign

Signiert ein Policy-Bundle kryptografisch.

```bash
npa sign [OPTIONEN] BUNDLE
```

### Argumente

| Argument | Beschreibung |
|----------|-------------|
| `BUNDLE` | Pfad zur Bundle-Datei (.tar.gz) |

### Optionen

| Option | Default | Beschreibung |
|--------|---------|-------------|
| `--signing-key` | (erforderlich) | Privater Schluessel (PEM) |
| `--signing-alg` | `RS256` | Signatur-Algorithmus |

### Beispiel

```bash
npa sign bundle.tar.gz --signing-key private.pem
```

---

## inspect

Zeigt den Inhalt eines Bundles.

```bash
npa inspect PFAD
```

### Argumente

| Argument | Beschreibung |
|----------|-------------|
| `PFAD` | Bundle-Datei (.tar.gz) oder Verzeichnis |

### Beispiel

```bash
npa inspect bundle.tar.gz
```

**Beispielausgabe:**

```
         Bundle: bundle.tar.gz
┌──────┬─────────────────────┬───────┐
│ Type │ Path                │  Size │
├──────┼─────────────────────┼───────┤
│ rego │ authz/policy.rego   │ 256 B │
│ rego │ rbac/rules.rego     │ 512 B │
│ data │ data.json           │ 128 B │
├──────┼─────────────────────┼───────┤
│ ...  │ revision=v1.0.0     │       │
│ ...  │ hash=a1b2c3d4...    │       │
│ ...  │ signed=no           │       │
└──────┴─────────────────────┴───────┘
```

---

## version

Zeigt NPA-Versionsinformation.

```bash
npa version
```

**Beispielausgabe:**

```
NPA - Next Policy Agent v0.1.0
Python 3.12.0
```

---

## bench

Misst die Performance einer Rego-Query.

```bash
npa bench [OPTIONEN] QUERY
```

### Argumente

| Argument | Beschreibung |
|----------|-------------|
| `QUERY` | Rego-Query zum Benchmarken |

### Optionen

| Option | Kurz | Default | Beschreibung |
|--------|------|---------|-------------|
| `--input` | `-i` | -- | Input-Datei (JSON) |
| `--data` | `-d` | -- | Daten-/Policy-Dateien (mehrfach) |
| `--bundle` | `-b` | -- | Bundle-Pfade (mehrfach) |
| `--count` | `-n` | `100` | Anzahl Iterationen |

### Beispiel

```bash
npa bench -d policies/ -i input.json -n 1000 "data.authz.allow"
```

**Beispielausgabe:**

```
   Benchmark: data.authz.allow (1000 iterations)
┌────────┬──────────────┐
│ Metric │        Value │
├────────┼──────────────┤
│ avg    │   15,234 ns  │
│ min    │   12,100 ns  │
│ max    │   89,500 ns  │
│ p50    │   14,800 ns  │
└────────┴──────────────┘
```

### Hinweise

- Die erste Iteration dient als Warm-up und wird nicht gemessen
- Ergebnisse in Nanosekunden (ns)
- Hoehere `--count`-Werte liefern stabilere Ergebnisse

---

## deps

Zeigt Abhaengigkeiten einer Rego-Query.

```bash
npa deps [OPTIONEN] QUERY
```

### Argumente

| Argument | Beschreibung |
|----------|-------------|
| `QUERY` | Rego-Query fuer Abhaengigkeitsanalyse |

### Optionen

| Option | Kurz | Default | Beschreibung |
|--------|------|---------|-------------|
| `--data` | `-d` | -- | Daten-/Policy-Dateien (mehrfach) |
| `--bundle` | `-b` | -- | Bundle-Pfade (mehrfach) |
| `--format` | `-f` | `pretty` | Ausgabeformat: `pretty`, `json` |

### Beispiel

```bash
npa deps -d policies/ "data.authz.allow"
```

**Beispielausgabe:**

```
Data dependencies:
  data.roles.admin_permissions
  data.users
Input dependencies:
  input.role
  input.action
  input.resource
```

---

## capabilities

Gibt die Faehigkeiten und unterstuetzten Built-ins von NPA aus.

```bash
npa capabilities [OPTIONEN]
```

### Optionen

| Option | Default | Beschreibung |
|--------|---------|-------------|
| `--format` | `json` | Ausgabeformat |
| `--current` | `true` | Aktuelle Faehigkeiten anzeigen |

### Beispiel

```bash
npa capabilities
```

**Ausgabe (gekuerzt):**

```json
{
  "npa_version": "0.1.0",
  "builtins": [
    {"name": "abs"},
    {"name": "all"},
    {"name": "any"},
    ...
  ],
  "features": [
    "rego_v1",
    "future.keywords.every",
    "future.keywords.in",
    "future.keywords.contains",
    "future.keywords.if"
  ],
  "wasm_abi_versions": []
}
```

---

## test

Fuehrt Rego-Tests aus (Regeln mit dem Praefix `test_`).

```bash
npa test [OPTIONEN] [PFADE...]
```

### Argumente

| Argument | Default | Beschreibung |
|----------|---------|-------------|
| `PFADE` | `.` (aktuelles Verzeichnis) | Rego-Dateien/Verzeichnisse mit Tests |

### Optionen

| Option | Kurz | Default | Beschreibung |
|--------|------|---------|-------------|
| `--verbose` | `-v` | `false` | Testnamen anzeigen |
| `--run` | `-r` | -- | Regex-Filter fuer Testnamen |

### Beispiele

```bash
# Alle Tests im aktuellen Verzeichnis
npa test

# Tests in bestimmtem Verzeichnis
npa test tests/

# Verbose-Modus
npa test -v tests/

# Nur bestimmte Tests
npa test -r "test_admin.*" tests/
```

**Beispielausgabe (verbose):**

```
  PASS test_rbac.test_admin_allowed
  PASS test_rbac.test_viewer_read
  FAIL test_rbac.test_deny_unknown: undefined

3 tests, 2 passed, 1 failed
```

### Test-Konventionen

- Tests sind Rego-Regeln, deren Name mit `test_` beginnt
- Test gilt als bestanden, wenn die Regel `true` ergibt
- Test schlaegt fehl, wenn die Regel `false`, `undefined` oder einen Fehler ergibt
- Neben `.rego`-Dateien werden `data.json`-Dateien im selben Verzeichnis automatisch geladen

---

## fmt

Formatiert Rego-Dateien.

```bash
npa fmt [OPTIONEN] PFADE...
```

### Argumente

| Argument | Beschreibung |
|----------|-------------|
| `PFADE` | Rego-Dateien oder Verzeichnisse |

### Optionen

| Option | Kurz | Default | Beschreibung |
|--------|------|---------|-------------|
| `--diff` | `-d` | `false` | Nur Diff anzeigen, nicht schreiben |
| `--check` | -- | `false` | Pruefen ob formatiert (Exit 1 wenn nicht) |

### Beispiele

```bash
# Dateien formatieren (in-place)
npa fmt policies/

# Nur Diff anzeigen
npa fmt -d policy.rego

# CI-Check: Sind alle Dateien formatiert?
npa fmt --check policies/
```

### Exit-Codes

| Code | Bedeutung |
|------|-----------|
| 0 | Alle Dateien formatiert / bereits korrekt |
| 1 | Dateien sind nicht formatiert (nur mit `--check`) |

---

## Globale Hinweise

### Rego-Datei-Erkennung

Alle Befehle, die Pfade akzeptieren, unterstuetzen:
- Einzelne `.rego`-Dateien
- Verzeichnisse (rekursiv nach `*.rego` durchsucht)
- Mehrere Pfade gleichzeitig

### Mehrfach-Optionen

Optionen wie `--data`, `--bundle` koennen mehrfach verwendet werden:

```bash
npa eval -d policies/ -d roles/ -d exceptions/ "data.authz.allow"
npa run -b ./authz -b ./rbac
```

### Ausgabeformate

| Format | Beschreibung |
|--------|-------------|
| `json` | Kompaktes JSON (Standard fuer die meisten Befehle) |
| `pretty` | Eingeruecktes, farbiges JSON (mit Rich) |
| `raw` | Rohausgabe des Python-Werts |
