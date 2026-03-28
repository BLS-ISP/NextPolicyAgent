# NPA Rego-Sprachreferenz

Vollstaendige Referenz der Rego-Policy-Sprache in NPA.
Rego ist eine deklarative Sprache, die speziell fuer Policy-Entscheidungen entwickelt wurde.

---

## Inhaltsverzeichnis

1. [Grundlagen](#grundlagen)
2. [Regeln](#regeln)
3. [Kontrollstrukturen](#kontrollstrukturen)
4. [Comprehensions](#comprehensions)
5. [Funktionen](#funktionen)
6. [Imports](#imports)
7. [Built-in Funktionen](#built-in-funktionen)
8. [Operatoren](#operatoren)

---

## Grundlagen

### Pakete

Jede Policy beginnt mit einer Paket-Deklaration:

```rego
package authz
```

Pakete definieren den Namespace im Datenbaum. `package authz` bedeutet,
dass Regeln unter `data.authz` erreichbar sind.

### Kommentare

```rego
# Dies ist ein Kommentar
```

### Datentypen

| Typ | Beispiele |
|-----|-----------|
| Boolean | `true`, `false` |
| Number | `42`, `3.14`, `-1` |
| String | `"hello"`, `` `raw string` `` |
| Null | `null` |
| Array | `[1, "two", true]` |
| Object | `{"key": "value", "n": 42}` |
| Set | `{1, 2, 3}` |

### Variablen

Variablen werden durch Vereinheitlichung (Unification) gebunden:

```rego
x := "hello"          # Zuweisung
x == "hello"          # Vergleich / Unification
[x, y] := [1, 2]     # Destrukturierung
```

### Referenzen

Zugriff auf verschachtelte Daten:

```rego
data.users.alice.role            # Punkt-Notation
data.users["alice"]["role"]      # Klammer-Notation
input.request.method             # Input-Referenz
```

---

## Regeln

### Einfache Regeln (Complete Rules)

Definieren einen einzelnen Wert:

```rego
default allow = false

allow if {
    input.role == "admin"
}
```

### Inkrementelle Regeln (Partial Rules)

Mehrere Definitionen derselben Regel (OR-Verknuepfung):

```rego
allow if { input.role == "admin" }
allow if { input.role == "superuser" }
```

### Regeln mit Werten

```rego
greeting := msg if {
    msg := concat(" ", ["Hello", input.name])
}
```

### Set-Regeln

Erzeugen eine Menge von Werten:

```rego
violations contains msg if {
    some user in input.users
    not user.email
    msg := sprintf("User %s has no email", [user.name])
}
```

### Object-Regeln

Erzeugen ein Objekt mit Schluessel-Wert-Paaren:

```rego
user_roles[name] := role if {
    some user in data.users
    name := user.name
    role := user.role
}
```

### Default-Werte

```rego
default allow = false
default priority = 0
```

---

## Kontrollstrukturen

### if / else

```rego
level := "high" if {
    input.score > 90
} else := "medium" if {
    input.score > 50
} else := "low"
```

### some ... in (Iteration)

```rego
# Ueber Array iterieren
allow if {
    some role in input.roles
    role == "admin"
}

# Ueber Object iterieren
allow if {
    some key, value in data.permissions
    key == input.action
    value == true
}

# Ueber Set iterieren
allowed_users contains name if {
    some name in data.admin_set
}
```

### every (Universelle Quantifizierung)

```rego
all_approved if {
    every request in input.requests {
        request.approved == true
    }
}
```

### with (Daten-Override)

Temporaeres Ueberschreiben von Input oder Daten:

```rego
allow if {
    data.authz.is_admin with input as {"role": "admin"}
}

# In Tests besonders nuetzlich
test_allow if {
    allow with input as {"role": "admin", "action": "read"}
    not allow with input as {"role": "guest", "action": "write"}
}
```

### not (Negation)

```rego
deny if {
    not input.authenticated
}

deny if {
    not data.whitelist[input.user]
}
```

---

## Comprehensions

### Array Comprehension

```rego
names := [name | some user in data.users; name := user.name]

# Mit Filter
admin_names := [name |
    some user in data.users
    user.role == "admin"
    name := user.name
]
```

### Set Comprehension

```rego
unique_roles := {role | some user in data.users; role := user.role}
```

### Object Comprehension

```rego
role_map := {name: role |
    some user in data.users
    name := user.name
    role := user.role
}
```

---

## Funktionen

Benutzerdefinierte Funktionen:

```rego
package authz

is_admin(user) if {
    data.roles[user] == "admin"
}

has_permission(user, action) if {
    perms := data.permissions[user]
    action in perms
}

# Funktion mit Rueckgabewert
full_name(user) := name if {
    name := sprintf("%s %s", [user.first, user.last])
}

# Verwendung
allow if {
    is_admin(input.user)
}
```

---

## Imports

### Standard-Imports

```rego
import data.roles               # Zugriff auf data.roles als "roles"
import data.utils.helpers        # Zugriff als "helpers"
import input.request             # Zugriff als "request"
```

### Future Keywords

```rego
import future.keywords.if        # Aktiviert "if" Keyword
import future.keywords.in        # Aktiviert "in" Keyword
import future.keywords.every     # Aktiviert "every" Keyword
import future.keywords.contains  # Aktiviert "contains" Keyword
```

### Rego v1

Alle Future Keywords sind in Rego v1 standardmaessig aktiv:

```rego
import rego.v1                   # Aktiviert alle Keywords
```

---

## Built-in Funktionen

NPA implementiert 192+ Built-in Funktionen, kompatibel mit OPA.

### Vergleich

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `equal(a, b)` | Gleichheit (==) | `equal("a", "a")` -> `true` |
| `neq(a, b)` | Ungleichheit (!=) | `neq(1, 2)` -> `true` |
| `lt(a, b)` | Kleiner als (<) | `lt(1, 2)` -> `true` |
| `lte(a, b)` | Kleiner oder gleich (<=) | `lte(1, 1)` -> `true` |
| `gt(a, b)` | Groesser als (>) | `gt(2, 1)` -> `true` |
| `gte(a, b)` | Groesser oder gleich (>=) | `gte(2, 2)` -> `true` |

### Arithmetik

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `plus(a, b)` | Addition | `plus(1, 2)` -> `3` |
| `minus(a, b)` | Subtraktion | `minus(5, 3)` -> `2` |
| `mul(a, b)` | Multiplikation | `mul(3, 4)` -> `12` |
| `div(a, b)` | Division | `div(10, 3)` -> `3.33...` |
| `rem(a, b)` | Modulo | `rem(10, 3)` -> `1` |
| `abs(x)` | Absolutwert | `abs(-5)` -> `5` |
| `ceil(x)` | Aufrunden | `ceil(3.2)` -> `4` |
| `floor(x)` | Abrunden | `floor(3.8)` -> `3` |
| `round(x)` | Runden | `round(3.5)` -> `4` |
| `numbers.range(a, b)` | Bereich erzeugen | `numbers.range(1, 4)` -> `[1,2,3,4]` |
| `numbers.range_step(a, b, s)` | Bereich mit Schritt | `numbers.range_step(0, 10, 3)` -> `[0,3,6,9]` |

### Bitweise Operationen

| Funktion | Beschreibung |
|----------|-------------|
| `bits.and(a, b)` | Bitweises AND |
| `bits.or(a, b)` | Bitweises OR |
| `bits.xor(a, b)` | Bitweises XOR |
| `bits.negate(a)` | Bitweise Negation |
| `bits.lsh(a, n)` | Links-Shift |
| `bits.rsh(a, n)` | Rechts-Shift |

### Aggregation

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `count(x)` | Anzahl Elemente | `count([1,2,3])` -> `3` |
| `sum(x)` | Summe | `sum([1,2,3])` -> `6` |
| `product(x)` | Produkt | `product([2,3,4])` -> `24` |
| `max(x)` | Maximum | `max([1,5,3])` -> `5` |
| `min(x)` | Minimum | `min([1,5,3])` -> `1` |
| `any(x)` | Mindestens ein true | `any([false, true])` -> `true` |
| `all(x)` | Alle true | `all([true, true])` -> `true` |
| `sort(x)` | Sortieren | `sort([3,1,2])` -> `[1,2,3]` |

### Arrays

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `array.concat(a, b)` | Arrays verketten | `array.concat([1],[2])` -> `[1,2]` |
| `array.slice(a, start, end)` | Teilarray | `array.slice([0,1,2,3], 1, 3)` -> `[1,2]` |
| `array.reverse(a)` | Umkehren | `array.reverse([1,2,3])` -> `[3,2,1]` |
| `array.flatten(a)` | Verschachtelt -> flach | `array.flatten([[1],[2,3]])` -> `[1,2,3]` |

### Mengen (Sets)

| Funktion | Beschreibung |
|----------|-------------|
| `intersection(sets)` | Schnittmenge mehrerer Sets |
| `union(sets)` | Vereinigung mehrerer Sets |
| `set_diff(a, b)` | Differenz zweier Sets |

### Strings

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `concat(delim, arr)` | Verbinden | `concat(", ", ["a","b"])` -> `"a, b"` |
| `contains(s, sub)` | Enthalten? | `contains("hello", "ell")` -> `true` |
| `startswith(s, pre)` | Beginnt mit? | `startswith("hello", "he")` -> `true` |
| `endswith(s, suf)` | Endet mit? | `endswith("hello", "lo")` -> `true` |
| `lower(s)` | Kleinbuchstaben | `lower("HELLO")` -> `"hello"` |
| `upper(s)` | Grossbuchstaben | `upper("hello")` -> `"HELLO"` |
| `split(s, delim)` | Aufteilen | `split("a.b.c", ".")` -> `["a","b","c"]` |
| `join(delim, arr)` | Verbinden | `join("-", ["a","b"])` -> `"a-b"` |
| `trim(s, cutset)` | Zeichen entfernen | `trim(" hi ", " ")` -> `"hi"` |
| `trim_left(s, cutset)` | Links trimmen | |
| `trim_right(s, cutset)` | Rechts trimmen | |
| `trim_prefix(s, pre)` | Praefix entfernen | `trim_prefix("foobar", "foo")` -> `"bar"` |
| `trim_suffix(s, suf)` | Suffix entfernen | |
| `trim_space(s)` | Whitespace entfernen | `trim_space("  hi  ")` -> `"hi"` |
| `replace(s, old, new)` | Ersetzen | `replace("aab", "a", "b")` -> `"bbb"` |
| `indexof(s, sub)` | Position finden | `indexof("hello", "ll")` -> `2` |
| `indexof_n(s, sub)` | Alle Positionen | `indexof_n("abab", "ab")` -> `[0,2]` |
| `substring(s, off, len)` | Teilstring | `substring("hello", 1, 3)` -> `"ell"` |
| `sprintf(fmt, args)` | Formatieren | `sprintf("Hi %s", ["Bob"])` -> `"Hi Bob"` |
| `strings.reverse(s)` | Umkehren | `strings.reverse("abc")` -> `"cba"` |
| `strings.count(s, sub)` | Vorkommen zaehlen | `strings.count("aab","a")` -> `2` |
| `strings.any_prefix_match(strs, pre)` | Praefix-Match in Liste | |
| `strings.any_suffix_match(strs, suf)` | Suffix-Match in Liste | |
| `strings.replace_n(patterns, s)` | Mehrfach-Ersetzen | |
| `strings.render_template(tmpl, vars)` | Template rendern | |

### Regex

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `regex.match(pat, s)` | Regex-Match | `regex.match("^h.*o$", "hello")` -> `true` |
| `regex.is_valid(pat)` | Pattern gueltig? | `regex.is_valid("[a-z]+")` -> `true` |
| `regex.split(pat, s)` | Regex-Split | `regex.split("[,;]", "a,b;c")` -> `["a","b","c"]` |
| `regex.find_n(pat, s, n)` | Matches finden | `regex.find_n("[0-9]+", "a1b2", -1)` -> `["1","2"]` |
| `regex.find_all_string_submatch_n(...)` | Submatch finden | |
| `regex.replace(s, pat, repl)` | Regex-Ersetzen | |
| `regex.template_match(pat, s, delimiters)` | Template-Match | |
| `regex.globs_match(glob, s)` | Glob-Pattern Match | |
| `re_match(pat, s)` | Legacy regex.match | |

### Objekte

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `object.get(obj, key, default)` | Sicherer Zugriff | `object.get({"a":1}, "b", 0)` -> `0` |
| `object.keys(obj)` | Schluessel | `object.keys({"a":1,"b":2})` -> `{"a","b"}` |
| `object.values(obj)` | Werte | `object.values({"a":1})` -> `[1]` |
| `object.union(a, b)` | Zusammenfuegen | `object.union({"a":1},{"b":2})` -> `{"a":1,"b":2}` |
| `object.union_n(objs)` | N Objekte zusammen | |
| `object.remove(obj, keys)` | Schluessel entfernen | `object.remove({"a":1,"b":2}, {"b"})` -> `{"a":1}` |
| `object.filter(obj, keys)` | Nur bestimmte Keys | `object.filter({"a":1,"b":2}, {"a"})` -> `{"a":1}` |
| `object.subset(super, sub)` | Teilmenge pruefen | |

### Typ-Pruefung

| Funktion | Beschreibung |
|----------|-------------|
| `is_null(x)` | Null? |
| `is_boolean(x)` | Boolean? |
| `is_number(x)` | Zahl? |
| `is_string(x)` | String? |
| `is_array(x)` | Array? |
| `is_set(x)` | Set? |
| `is_object(x)` | Object? |
| `type_name(x)` | Gibt den Typnamen zurueck |

### Encoding / Decoding

| Funktion | Beschreibung |
|----------|-------------|
| `base64.encode(s)` | Base64-Kodierung |
| `base64.decode(s)` | Base64-Dekodierung |
| `base64.is_valid(s)` | Gueltig? |
| `base64url.encode(s)` | URL-safe Base64 |
| `base64url.decode(s)` | URL-safe Base64 dekodieren |
| `base64url.encode_no_pad(s)` | Ohne Padding |
| `json.marshal(x)` | JSON-Serialisierung |
| `json.unmarshal(s)` | JSON-Deserialisierung |
| `json.is_valid(s)` | Gueltiges JSON? |
| `json.filter(obj, paths)` | JSON filtern |
| `json.remove(obj, paths)` | JSON-Pfade entfernen |
| `json.patch(obj, patches)` | JSON Patch (RFC 6902) |
| `json.marshal_with_options(x, opts)` | Mit Optionen serialisieren |
| `json.verify_schema(schema)` | JSON-Schema validieren |
| `json.match_schema(doc, schema)` | Dokument gegen Schema pruefen |
| `yaml.marshal(x)` | YAML-Serialisierung |
| `yaml.unmarshal(s)` | YAML-Deserialisierung |
| `yaml.is_valid(s)` | Gueltiges YAML? |
| `urlquery.encode(s)` | URL-Query kodieren |
| `urlquery.decode(s)` | URL-Query dekodieren |
| `urlquery.encode_object(obj)` | Object -> Query-String |
| `urlquery.decode_object(s)` | Query-String -> Object |
| `hex.encode(s)` | Hex-Kodierung |
| `hex.decode(s)` | Hex-Dekodierung |

### Kryptografie

| Funktion | Beschreibung |
|----------|-------------|
| `crypto.sha256(s)` | SHA-256 Hash |
| `crypto.sha512(s)` | SHA-512 Hash |
| `crypto.sha1(s)` | SHA-1 Hash |
| `crypto.md5(s)` | MD5 Hash |
| `crypto.hmac.sha256(data, key)` | HMAC-SHA256 |
| `crypto.hmac.sha512(data, key)` | HMAC-SHA512 |
| `crypto.hmac.md5(data, key)` | HMAC-MD5 |
| `crypto.hmac.sha1(data, key)` | HMAC-SHA1 |
| `crypto.hmac.equal(a, b)` | Konstanter Vergleich |
| `crypto.x509.parse_certificates(pem)` | X.509-Zertifikate parsen |
| `crypto.x509.parse_and_verify_certificates(pem)` | Parsen und verifizieren |
| `crypto.x509.parse_certificate_request(pem)` | CSR parsen |
| `crypto.x509.parse_keypair(cert, key)` | Schluesselpaar parsen |
| `crypto.x509.parse_rsa_private_key(pem)` | RSA-Key parsen |
| `crypto.parse_private_keys(pem)` | Private Keys parsen |

### JWT (JSON Web Token)

| Funktion | Beschreibung |
|----------|-------------|
| `io.jwt.decode(token)` | JWT dekodieren (ohne Verifikation) |
| `io.jwt.decode_verify(token, constraints)` | Dekodieren + Verifizieren |
| `io.jwt.encode_sign(headers, payload, key)` | JWT erzeugen + signieren |
| `io.jwt.encode_sign_raw(h, p, k)` | JWT aus Roh-Strings erzeugen |

### Zeit

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `time.now_ns()` | Aktuelle Zeit (ns) | `time.now_ns()` -> `1711612800000000000` |
| `time.parse_ns(layout, s)` | Zeit parsen (ns) | |
| `time.parse_rfc3339_ns(s)` | RFC3339 parsen | `time.parse_rfc3339_ns("2024-01-01T00:00:00Z")` |
| `time.parse_duration_ns(s)` | Dauer parsen | `time.parse_duration_ns("1h30m")` |
| `time.date(ns)` | Datum extrahieren | `time.date(ns)` -> `[2024, 1, 15]` |
| `time.clock(ns)` | Uhrzeit extrahieren | `time.clock(ns)` -> `[14, 30, 0]` |
| `time.weekday(ns)` | Wochentag | `time.weekday(ns)` -> `"Monday"` |
| `time.add_date(ns, y, m, d)` | Datum addieren | |
| `time.diff(ns1, ns2)` | Zeitdifferenz | -> `[years, months, days, hours, mins, secs]` |
| `time.format(ns)` | Zeit formatieren | |

### Netzwerk

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `net.cidr_contains(cidr, ip)` | IP in CIDR? | `net.cidr_contains("10.0.0.0/8", "10.1.2.3")` -> `true` |
| `net.cidr_intersects(a, b)` | CIDRs ueberlappen? | |
| `net.cidr_is_valid(cidr)` | CIDR gueltig? | |
| `net.cidr_expand(cidr)` | Alle IPs im CIDR | |
| `net.cidr_merge(cidrs)` | CIDRs zusammenfuegen | |
| `net.cidr_contains_matches(cidrs, ips)` | Batch-Match | |
| `net.cidr_overlap(a, b)` | CIDR-Ueberlappung (legacy) | |
| `net.lookup_ip_addr(host)` | DNS-Lookup | |

### UUID

| Funktion | Beschreibung |
|----------|-------------|
| `uuid.rfc4122(seed)` | UUID v4 generieren |
| `uuid.parse(s)` | UUID parsen |

### Semantic Versioning

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `semver.is_valid(s)` | Gueltig? | `semver.is_valid("1.2.3")` -> `true` |
| `semver.compare(a, b)` | Vergleichen | `semver.compare("1.2.0", "1.3.0")` -> `-1` |

### Glob

| Funktion | Beschreibung |
|----------|-------------|
| `glob.match(pattern, delimiters, s)` | Glob-Pattern matchen |
| `glob.quote_meta(s)` | Sonderzeichen escapen |

### Graph

| Funktion | Beschreibung |
|----------|-------------|
| `graph.reachable(graph, start)` | Erreichbare Knoten |
| `graph.reachable_paths(graph, start)` | Erreichbare Pfade |

### GraphQL

| Funktion | Beschreibung |
|----------|-------------|
| `graphql.is_valid(query, schema)` | Query gueltig? |
| `graphql.parse(query, schema)` | Query parsen |
| `graphql.parse_and_verify(query, schema)` | Parsen + verifizieren |
| `graphql.parse_query(query)` | Nur Query parsen |
| `graphql.parse_schema(schema)` | Nur Schema parsen |
| `graphql.schema_is_valid(schema)` | Schema gueltig? |

### HTTP

| Funktion | Beschreibung |
|----------|-------------|
| `http.send(request)` | HTTP-Request senden |

**http.send Request-Objekt:**

```rego
resp := http.send({
    "method": "GET",
    "url": "https://api.example.com/data",
    "headers": {"Authorization": "Bearer token123"},
    "timeout": "5s",
    "tls_insecure_skip_verify": false
})

# resp.status_code, resp.body, resp.headers
```

### Einheiten (Units)

| Funktion | Beschreibung | Beispiel |
|----------|-------------|---------|
| `units.parse(s)` | Einheit parsen | `units.parse("10Ki")` -> `10240` |
| `units.parse_bytes(s)` | Bytes parsen | `units.parse_bytes("1GB")` -> `1000000000` |

### Typ-Konvertierung

| Funktion | Beschreibung |
|----------|-------------|
| `to_number(x)` | In Zahl konvertieren |
| `format_int(x, base)` | Zahl formatieren (Basis 2, 8, 10, 16) |
| `cast_array(x)` | Zu Array casten |
| `cast_set(x)` | Zu Set casten |
| `cast_string(x)` | Zu String casten |
| `cast_boolean(x)` | Zu Boolean casten |
| `cast_null(x)` | Zu Null casten |
| `cast_object(x)` | Zu Object casten |

### Sonstige

| Funktion | Beschreibung |
|----------|-------------|
| `walk(x)` | Rekursiv durch Datenstruktur laufen |
| `print(...)` | Debug-Ausgabe |
| `trace(msg)` | Trace-Nachricht |
| `opa.runtime()` | Runtime-Info |
| `rand.intn(seed, n)` | Zufallszahl (deterministisch) |
| `rego.parse_module(name, src)` | Rego-Modul parsen |
| `rego.metadata.rule()` | Regel-Metadaten |
| `rego.metadata.chain()` | Metadaten-Kette |
| `internal.member_2(x, coll)` | Mitgliedschaftspruefung |
| `internal.member_3(k, v, coll)` | Key-Value Mitgliedschaft |
| `internal.print(...)` | Interner Print |

---

## Operatoren

### Vergleichsoperatoren

| Operator | Beschreibung | Beispiel |
|----------|-------------|---------|
| `==` | Gleich (Unification) | `x == 5` |
| `!=` | Ungleich | `x != 0` |
| `<` | Kleiner | `x < 10` |
| `<=` | Kleiner oder gleich | `x <= 10` |
| `>` | Groesser | `x > 0` |
| `>=` | Groesser oder gleich | `x >= 1` |

### Arithmetische Operatoren

| Operator | Beschreibung |
|----------|-------------|
| `+` | Addition |
| `-` | Subtraktion |
| `*` | Multiplikation |
| `/` | Division |
| `%` | Modulo |

### Zuweisungsoperatoren

| Operator | Beschreibung | Beispiel |
|----------|-------------|---------|
| `:=` | Lokale Zuweisung | `x := 5` |
| `=` | Unification | `x = input.value` |

### Logische Operatoren

| Operator | Beschreibung | Beispiel |
|----------|-------------|---------|
| `not` | Negation | `not input.blocked` |
| `;` | OR (in Comprehensions) | `[x \| x := 1; x := 2]` |
| Mehrere Ausdruecke | AND (implizit) | `a > 0` gefolgt von `b > 0` |

### Mitgliedschaft

| Operator | Beschreibung | Beispiel |
|----------|-------------|---------|
| `in` | Element enthalten? | `"admin" in input.roles` |
| `some x in coll` | Iteration | `some x in [1,2,3]` |
| `some k, v in obj` | Key-Value Iteration | `some k, v in {"a": 1}` |

---

## Rego v1 Kompatibilitaet

NPA unterstuetzt folgende Rego v1 Features:

- `import rego.v1` (aktiviert alle future keywords)
- `import future.keywords.if`
- `import future.keywords.in`
- `import future.keywords.every`
- `import future.keywords.contains`
- Set-Regeln mit `contains`
- `if` in Regel-Bodies
- `some ... in` Iteration
- `every ... in` universelle Quantifizierung
