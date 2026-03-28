# -------------------------------------------------------
# HTTP API Autorisierung
# -------------------------------------------------------
# Schützt REST-Endpunkte basierend auf HTTP-Methode,
# Pfad und Benutzerrolle.
#
# Auswertung (CLI):
#   npa eval -d examples/http-api-authz/ "data.httpapi.authz"
#
# Auswertung (API):
#   POST /v1/data/httpapi/authz
#   Body: {"input": {"method": "GET", "path": ["api","v1","health"]}}
# -------------------------------------------------------
package httpapi.authz

import future.keywords.if
import future.keywords.in

default allow = false

# Öffentliche Endpunkte (kein Token nötig)
allow if {
    input.method == "GET"
    input.path == ["api", "v1", "health"]
}

allow if {
    input.method == "GET"
    input.path == ["api", "v1", "docs"]
}

# Authentifizierte Benutzer dürfen GET auf /users
allow if {
    input.method == "GET"
    input.path == ["api", "v1", "users"]
    count(input.token) > 10
}

# Nur Admins dürfen schreiben
allow if {
    input.method in ["POST", "PUT", "DELETE"]
    input.path == ["api", "v1", "users"]
    count(input.token) > 10
    some admin in data.httpapi.admins
    admin == input.user
}

# Benutzer darf eigenes Profil lesen/bearbeiten
allow if {
    input.method in ["GET", "PUT"]
    input.path[0] == "api"
    input.path[1] == "v1"
    input.path[2] == "users"
    input.path[3] == input.user
    count(input.token) > 10
}

# HTTP Status-Code je nach Situation
status_code = 200 if {
    allow
} else = 403
