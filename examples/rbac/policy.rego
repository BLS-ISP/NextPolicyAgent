# -------------------------------------------------------
# RBAC – Rollenbasierte Zugriffskontrolle
# -------------------------------------------------------
# Klassisches RBAC: Benutzer haben Rollen, Rollen haben
# Berechtigungen (in data.json definiert).
#
# Auswertung (CLI):
#   npa eval -d examples/rbac/ "data.rbac.authz.allow"
#
# Auswertung (API):
#   POST /v1/data/rbac/authz
#   Body: {"input": {"user": "alice", "action": "write", "resource": "reports"}}
# -------------------------------------------------------
package rbac.authz

import future.keywords.if
import future.keywords.in

# Standard: Zugriff verweigert
default allow = false

# Zugriff erlaubt, wenn eine Rollenbindung und Berechtigung passt
allow if {
    some binding in data.rbac.bindings
    binding.user == input.user
    some grant in data.rbac.grants[binding.role]
    grant.action == input.action
    grant.resource == input.resource
}

# Entscheidungsgrund als Text
reason = "Zugriff erlaubt" if {
    allow
} else = "Keine passende Berechtigung gefunden"
