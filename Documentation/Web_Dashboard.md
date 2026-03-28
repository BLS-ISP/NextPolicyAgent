# NPA Web-Dashboard -- Benutzerhandbuch

Das NPA Web-Dashboard ist eine integrierte Single-Page-Applikation (SPA) zum
Verwalten und Ueberwachen des Policy-Servers direkt im Browser. Es bietet
sieben Seiten fuer alle gaengigen Aufgaben -- von der Live-Uebersicht bis
zum interaktiven Rego-Playground.

**URL:** `https://localhost:8443/` (Standard)

---

## Inhaltsverzeichnis

1. [Voraussetzungen](#1-voraussetzungen)
2. [Login und Session](#2-login-und-session)
3. [Navigation und Aufbau](#3-navigation-und-aufbau)
4. [Dashboard (Startseite)](#4-dashboard-startseite)
5. [Policy-Editor](#5-policy-editor)
6. [Query Playground](#6-query-playground)
7. [Data Browser](#7-data-browser)
8. [Bundle Management](#8-bundle-management)
9. [Decision Logs](#9-decision-logs)
10. [Configuration](#10-configuration)
11. [Tastenkuerzel](#11-tastenkuerzel)
12. [UI-API-Endpunkte](#12-ui-api-endpunkte)
13. [Tipps und Fehlerbehebung](#13-tipps-und-fehlerbehebung)

---

## 1. Voraussetzungen

- NPA-Server laeuft (z. B. `npa run` oder via Docker)
- Moderner Browser (Chrome, Firefox, Edge, Safari)
- JavaScript aktiviert
- Netzwerkverbindung zum Server (Standard: Port 8443, HTTPS)

CodeMirror 5.65.16 wird als Rego-/JSON-Editor per CDN geladen. Ohne
Internet-Zugang funktioniert der Editor trotzdem -- er faellt auf ein
einfaches Textarea zurueck.

---

## 2. Login und Session

### Anmeldung

Beim Oeffnen der URL erscheint ein Login-Formular:

| Feld | Standard |
|------|----------|
| **Benutzername** | `admin` |
| **Passwort** | `admin` |

Anpassbar ueber Umgebungsvariablen:

```bash
export NPA_AUTH_UI_USERNAME=mein_user
export NPA_AUTH_UI_PASSWORD=sicheres_passwort
```

### Session-Verwaltung

- Sessions werden als **HttpOnly-Cookie** gespeichert (8 h Lebensdauer)
- Bei Inaktivitaet oder Session-Ablauf leitet das Dashboard automatisch
  zum Login zurueck
- Ein **Logout-Button** befindet sich unten in der Seitenleiste
- Der Server prueft die Session alle 15 Sekunden per Health-Check --
  bei Verbindungsverlust zeigt der Status-Indikator "Disconnected" an

---

## 3. Navigation und Aufbau

Das Dashboard nutzt Hash-basiertes Routing (`#/dashboard`, `#/policies`, ...).

```
+-----+-----------------------------------+
| Nav |  Hauptbereich (Seiteninhalt)      |
|     |                                   |
| 📊  |  [je nach gewaehlter Seite]       |
| 📜  |                                   |
| ▶️  |                                   |
| 🗄️  |                                   |
| 📦  |                                   |
| 📋  |                                   |
| --- |                                   |
| ⚙️  |                                   |
|     |                                   |
| 🟢  |                                   |
| xit |                                   |
+-----+-----------------------------------+
```

**Seitenleiste (Sidebar):**

| Icon | Seite | Route |
|------|-------|-------|
| 📊 | Dashboard | `#/dashboard` |
| 📜 | Policies | `#/policies` |
| ▶️ | Playground | `#/playground` |
| 🗄️ | Data Browser | `#/data` |
| 📦 | Bundles | `#/bundles` |
| 📋 | Decision Logs | `#/logs` |
| ⚙️ | Configuration | `#/config` |

Unter der Navigation befindet sich ein **Server-Status-Indikator** (gruen =
verbunden, gelb = verbindet, rot = getrennt) sowie der **Logout-Button**.

**Toast-Benachrichtigungen** erscheinen oben rechts bei Erfolg, Fehler oder
Hinweisen. **Modale Dialoge** ueberlagern den Inhalt fuer Detailansichten
und Bestaetigungen.

---

## 4. Dashboard (Startseite)

Zeigt eine Live-Uebersicht ueber den gesamten Server.

### Statistik-Karten (8 Stueck)

| Karte | Beschreibung |
|-------|-------------|
| 🏥 Server Health | Aktueller Gesundheitsstatus |
| 📜 Policies Loaded | Anzahl geladener Policies |
| 🗄️ Data Documents | Anzahl der Datendokumente im Store |
| ⏱️ Uptime | Server-Laufzeit (formatiert: Tage/Stunden/Min/Sek) |
| 📊 Total Decisions | Gesamtzahl der bisherigen Evaluierungen |
| 💾 Memory (RSS) | Aktueller Speicherverbrauch (RAM) |
| ⚡ Avg Query Time | Durchschnittliche Antwortzeit pro Query |
| 📦 Bundles | Anzahl geladener Bundles |

### Weitere Bereiche

- **Server Info** -- Tabelle mit Version, Python-Version, Hostname,
  PID, Start-Zeitpunkt, Storage-Backend, Config-Datei
- **Loaded Policies** -- Liste aller geladenen Policies mit Link zum
  Policy-Editor
- **Bundle Status** -- Aktive Bundles mit Metadaten
- **Recent Decisions** -- Die letzten Evaluierungen mit Timestamp,
  Query, Dauer und Ergebnis-Status

### Auto-Refresh

Die Seite aktualisiert sich automatisch alle **30 Sekunden**. Zusaetzlich
gibt es einen manuellen **Refresh-Button**.

---

## 5. Policy-Editor

Vollwertiger Rego-Editor mit Syntax-Highlighting, Formatierung und Tests.

### Layout

Die Seite ist zweigeteilt:

- **Links:** Policy-Liste mit allen geladenen Policies (ID und Zeilenzahl)
- **Rechts:** CodeMirror-Editor mit Syntax-Highlighting (Material Darker Theme)

### Funktionen

| Aktion | Button | Beschreibung |
|--------|--------|-------------|
| Neue Policy | **+ New Policy** | Leere Policy mit benutzerdefinierter ID erstellen |
| Formatieren | 🎨 **Fmt** | Rego-Code automatisch formatieren |
| Pruefen | ✓ **Check** | Syntax-Pruefung ohne Speichern |
| AST anzeigen | 🌳 **AST** | Abstract Syntax Tree als JSON anzeigen |
| Speichern | 💾 **Save** | Policy an den Server senden (PUT) |
| Loeschen | 🗑️ **Delete** | Policy entfernen (mit Bestaetigungsdialog) |
| Tests | 🧪 **Run Tests** | Alle `test_`-Regeln ausfuehren und Ergebnis anzeigen |

### Workflow-Beispiel

1. Klick auf **+ New Policy**
2. Einen Policy-Pfad angeben, z. B. `authz/rbac`
3. Rego-Code eingeben:
   ```rego
   package authz.rbac

   default allow := false

   allow if {
       input.role == "admin"
   }
   ```
4. Mit 🎨 **Fmt** formatieren
5. Mit ✓ **Check** pruefen
6. Mit 💾 **Save** speichern
7. Optional: 🧪 **Run Tests** ausfuehren

### Hinweise

- Der Editor zeigt den **Parse-Status** in der Fusszeile an (OK oder Fehler
  mit Zeile/Spalte)
- Die AST-Ansicht oeffnet sich unterhalb des Editors und kann geschlossen
  werden
- Policies werden unter ihrem Pfad als ID gespeichert (z. B. `authz/rbac`)

---

## 6. Query Playground

Interaktive Konsole fuer Rego-Queries mit Erklaerungsmodus und Metriken.

### Layout (3 Spalten)

1. **Query-Editor** -- Rego-Ausdruck (z. B. `data.authz.allow`)
2. **Input-Editor** -- Optionales JSON-Input-Dokument
3. **Result** -- Ergebnisanzeige mit Tabs (Result / Explanation / Metrics)

### Toolbar-Optionen

| Option | Funktion |
|--------|----------|
| **Explain** | Erklaerungsmodus: Off, Notes, Fails, Full, Debug |
| **Metrics** | Zeitmessungen fuer Parser, Compiler, Evaluator anzeigen |
| **Instrument** | Detaillierte Instrumentierung aktivieren |
| **Strict Builtins** | Strenge Built-in-Fehlerbehandlung |

### Erklaerungsmodi im Detail

| Modus | Beschreibung |
|-------|-------------|
| **Off** | Keine Erklaerung |
| **Notes** | Nur Hinweise und Anmerkungen |
| **Fails** | Gescheiterte Regeln und deren Ursache |
| **Full** | Vollstaendiger Evaluation-Trace |
| **Debug** | Maximale Detail-Tiefe mit allen Zwischenschritten |

### Query-History

- Die letzten 50 Queries werden im **localStorage** gespeichert
- Abrufbar ueber das History-Dropdown
- Bleibt ueber Browser-Sitzungen hinweg erhalten

### Beispiel-Queries

```
data                          -- Gesamten Store anzeigen
1 + 1                         -- Einfache Berechnung
data.authz.allow              -- Policy evaluieren
x := data.users[_].name       -- Daten abfragen
```

### Compile-Modus

Ueber den **Compile-Button** kann ein Query partiell evaluiert werden. Der
Server gibt den optimierten AST zurueck, nuetzlich fuer Debugging und
Performance-Analyse.

### Tastenkuerzel

- **Ctrl+Enter** -- Query ausfuehren (auch im Editor-Fokus)

---

## 7. Data Browser

Hierarchischer Baum-Browser fuer alle Daten im Storage mit integriertem
JSON-Editor.

### Layout

- **Links:** Aufklappbare Baumstruktur (max. 10 Ebenen tief)
- **Rechts:** JSON-Editor (CodeMirror) fuer das ausgewaehlte Dokument

### Baum-Symbole

| Symbol | Bedeutung |
|--------|----------|
| 📂 | Ordner / Objekt mit Kindern |
| 📝 | String-Wert |
| 🔢 | Zahlenwert |
| ✅ | Boolean-Wert |
| 📄 | Sonstiger Wert / Array |

### Funktionen

| Aktion | Beschreibung |
|--------|-------------|
| **Knoten anklicken** | Dokument im JSON-Editor anzeigen |
| **Ordner aufklappen** | Klick auf Pfeil links neben dem Ordner-Symbol |
| **+ Add Document** | Neues Datendokument unter beliebigem Pfad anlegen |
| 💾 **Save** | Geaendertes Dokument speichern (PUT) |
| 🗑️ **Delete** | Dokument loeschen (mit Bestaetigung) |
| ↻ **Refresh** | Baumstruktur neu laden |

### Workflow-Beispiel

1. Klick auf **+ Add Document**
2. Pfad eingeben, z. B. `users/alice`
3. JSON eingeben:
   ```json
   {
       "name": "Alice",
       "role": "admin",
       "active": true
   }
   ```
4. 💾 **Save** -- Dokument wird unter `data.users.alice` gespeichert
5. Im Baum erscheint ein neuer Knoten `users > alice`

---

## 8. Bundle Management

Bundles hochladen, inspizieren und verwalten.

### Aktive Bundles

Eine Tabelle zeigt alle geladenen Bundles mit:

- **Name** -- Bundle-Identifikator
- **Quelle** -- Local/API oder Remote-URL
- **Policies** -- Anzahl enthaltener Policies
- **Data Roots** -- Daten-Pfade im Bundle
- **Status** -- Active / Inactive
- **Aktionen** -- Inspect (Detailansicht), Delete

### Bundle hochladen

1. **Bundle Name** eingeben (z. B. `authz-bundle`)
2. Entweder:
   - `.tar.gz`-Datei per **Drag & Drop** auf den Upload-Bereich ziehen
   - Oder **Browse Files** klicken und Datei auswaehlen
3. Upload startet automatisch (Binary PUT an `/v1/bundles/{name}`)
4. Erfolgsmeldung per Toast-Nachricht

### Bundle-Format

| Eigenschaft | Wert |
|------------|------|
| Dateiformat | `.tar.gz` |
| Inhalt | `.rego`-Dateien und/oder `data.json` |
| Polling | Konfigurierbares Intervall (Standard: 60s) |
| Verifikation | JWT-basierte Bundle-Signaturen |

### Inspect / Detailansicht

Per Klick auf **Inspect** oeffnet sich ein modaler Dialog mit dem
vollstaendigen Bundle-Inhalt als JSON.

---

## 9. Decision Logs

Durchsuchbares Protokoll aller Policy-Evaluierungen mit Export.

### Toolbar

| Element | Funktion |
|---------|----------|
| **Suchfeld** | Freitext-Suche ueber Query-String und Pfad |
| **Status-Filter** | Alle / Nur OK / Nur Fehler |
| **Limit** | 50, 100 (Standard), 200 oder 500 Eintraege |

### Tabelle

Jeder Eintrag zeigt:

- **#** -- Laufende Nummer
- **Timestamp** -- Zeitpunkt der Evaluierung
- **Query** -- Ausgefuehrter Rego-Query bzw. Pfad
- **Duration** -- Bearbeitungsdauer
- **Status** -- OK (gruen) oder Error (rot)
- **Details** -- Klick oeffnet Modal mit vollstaendigem Request/Response

### Export

| Button | Format | Beschreibung |
|--------|--------|-------------|
| 📥 **JSON** | `.json` | Alle sichtbaren Eintraege als JSON-Array |
| 📥 **CSV** | `.csv` | Komma-separierte Werte fuer Tabellenkalkulationen |

### Weitere Aktionen

- ↻ **Refresh** -- Sofort neu laden
- **Clear All** -- Alle Eintraege loeschen (mit Bestaetigung)
- **Auto-Refresh** -- Aktualisiert sich automatisch alle **10 Sekunden**

### Speicher

Decision Logs werden serverseitig in einem Ringpuffer gespeichert
(max. 1.000 Eintraege). Aeltere Eintraege werden automatisch verdraengt.

---

## 10. Configuration

Server-Konfiguration, Live-Metriken, Capabilities und API-Referenz auf
einen Blick.

### 5 Informations-Karten

#### Server Status

Tabelle mit Statusinformationen:

- Health, Version, Python-Version
- Hostname, PID, Uptime
- Anzahl Policies und Daten-Schluessel

#### Live Metrics

Echtzeit-Metriken mit **Auto-Refresh alle 10 Sekunden**:

- Gesamtzahl Requests, aktive Sessions
- Policy-Evaluierungen, aktive Bundles
- Speicherverbrauch, CPU-Auslastung
- Durchschnittliche Antwortzeit, gestartete Timer

#### Capabilities

Aufklappbare Liste aller unterstuetzten Built-in-Funktionen (192+), gruppiert
nach Kategorie. Jeder Eintrag zeigt den Funktionsnamen.

#### Server Configuration

Vollstaendige Server-Konfiguration als formatiertes JSON (Nur-Lese-Ansicht).

#### API Reference

Interaktive Tabelle aller REST-API-Endpunkte mit:

- HTTP-Methode (farbcodiert: GET=gruen, POST=blau, PUT=gelb, DELETE=rot)
- Pfad
- Beschreibung

Ausserdem Links zu:

- **Swagger UI** (`/docs`)
- **ReDoc** (`/redoc`)

---

## 11. Tastenkuerzel

| Kuerzel | Kontext | Aktion |
|---------|---------|--------|
| **Ctrl+Enter** | Playground | Query ausfuehren |
| **Enter** | Login-Formular | Anmelden |
| **Esc** | Modal | Dialog schliessen |

---

## 12. UI-API-Endpunkte

Das Dashboard kommuniziert mit dem Server ueber spezielle UI-Endpunkte
(zusaetzlich zur OPA-kompatiblen REST-API):

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| POST | `/v1/ui/login` | Anmeldung (setzt Session-Cookie) |
| POST | `/v1/ui/logout` | Abmeldung (loescht Session) |
| GET | `/v1/ui/session` | Session-Gueltigkeit pruefen |
| GET | `/v1/ui/status` | Server-Status (Health, Policies, Data, Uptime) |
| GET | `/v1/ui/metrics` | Live-Metriken (Requests, Memory, CPU) |
| GET | `/v1/ui/decisions` | Decision-Log-Eintraege abrufen |
| DELETE | `/v1/ui/decisions` | Alle Decision-Log-Eintraege loeschen |
| GET | `/v1/ui/data-tree` | Hierarchische Baumstruktur der Daten |
| POST | `/v1/ui/fmt` | Rego-Code formatieren |
| POST | `/v1/ui/check` | Rego-Syntax pruefen |
| POST | `/v1/ui/parse` | Rego zu AST parsen |
| POST | `/v1/ui/test` | Rego-Tests ausfuehren |
| GET | `/v1/ui/capabilities` | Unterstuetzte Built-in-Funktionen |

> Alle UI-Endpunkte erfordern eine gueltige Session (HttpOnly-Cookie).

---

## 13. Tipps und Fehlerbehebung

### Dashboard zeigt "Disconnected"

- Server laeuft nicht oder ist nicht erreichbar
- Pruefen: `curl -sk https://localhost:8443/health`
- Firewall oder Port-Weiterleitung kontrollieren

### Login schlaegt fehl

- Standard-Credentials: `admin` / `admin`
- Umgebungsvariablen `NPA_AUTH_UI_USERNAME` / `NPA_AUTH_UI_PASSWORD` pruefen
- Browser-Cookies muessen aktiviert sein

### CodeMirror-Editor fehlt (nur Textarea)

- CDN nicht erreichbar (z. B. Offline-Umgebung)
- Funktionalitaet bleibt erhalten, nur ohne Syntax-Highlighting
- Fuer Offline-Nutzung: CDN-Dateien lokal bereitstellen

### Queries liefern leere Ergebnisse

- Wurden Daten und Policies geladen? -> Dashboard pruefen
- Im Playground: Input-Dokument korrekt als JSON angeben
- Pfad pruefen: `data.meinpaket.meineregel`

### Performance

- Decision Logs verbrauchen Speicher (max. 1.000 Eintraege im Ringpuffer)
- Auto-Refresh-Intervalle:
  - Dashboard: 30 Sekunden
  - Decision Logs: 10 Sekunden
  - Configuration / Metrics: 10 Sekunden
  - Server Health Check: 15 Sekunden

### Browser-Kompatibilitaet

- Chrome 80+, Firefox 78+, Edge 80+, Safari 14+
- ES-Module und `fetch()` erforderlich
- localStorage fuer Query-History noetig

---

## Technische Details

### Architektur

- **SPA** mit Hash-Routing (`window.onhashchange`)
- **7 JavaScript-Module** (je eine Datei pro Seite unter `static/js/pages/`)
- **API-Client** (`API`-Klasse in `app.js`) mit `fetch()` und automatischer
  JSON-Verarbeitung
- **CodeMirror 5.65.16** mit Material Darker Theme und Bracket-Matching
- **Dark Theme** (CSS-Variablen in `npa.css`, >500 Zeilen)

### Theming

Das Dashboard verwendet ein dunkles Farbschema (inspiriert von GitHub Dark):

| Variable | Wert | Verwendung |
|----------|------|-----------|
| `--bg-primary` | `#0d1117` | Hintergrund |
| `--bg-secondary` | `#161b22` | Karten, Panels |
| `--bg-tertiary` | `#21262d` | Eingabefelder |
| `--text-primary` | `#f0f6fc` | Haupttext |
| `--accent-primary` | `#58a6ff` | Links, aktive Elemente |
| `--success` | `#3fb950` | Erfolg-Badges |
| `--danger` | `#f85149` | Fehler, Delete-Buttons |

### Datei-Struktur

```
npa/server/static/
  index.html              -- SPA-Shell (Login, Sidebar, Content-Container)
  css/
    npa.css               -- Komplettes Dark-Theme (500+ Zeilen)
  js/
    app.js                -- Kern: Router, API-Client, Toasts, Modals, Editor
    pages/
      dashboard.js        -- Startseite mit Statistiken
      policies.js         -- Policy-Editor mit CodeMirror
      playground.js       -- Query-Playground
      databrowser.js      -- Daten-Browser mit Baum
      bundles.js          -- Bundle-Verwaltung
      logs.js             -- Decision Logs
      config.js           -- Konfiguration und API-Referenz
```
