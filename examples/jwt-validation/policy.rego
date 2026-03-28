# JWT Token Validation Policy
# ============================
# Validates JWT tokens: checks trusted issuers, expiry, and extracts claims.
#
# Test: npa eval -d examples/jwt-validation/ -i examples/jwt-validation/input.json "data.jwt.validation"

package jwt.validation

# ── Default ──────────────────────────────────────────────
default allow = false

# ── Claims extraction ────────────────────────────────────
# Decode the token and expose the payload as "claims"
claims := io.jwt.decode(input.token)[1]

# ── Main decision ────────────────────────────────────────
# Allow if the issuer is trusted and the token is not expired
allow if {
    token := io.jwt.decode(input.token)
    # Check issuer against trusted list
    some issuer in data.jwt.trusted_issuers
    token[1].iss == issuer
    # Check token is not expired (exp > threshold)
    token[1].exp > 1700000000
}

# ── Convenience outputs ──────────────────────────────────
token_issuer := io.jwt.decode(input.token)[1].iss

token_subject := io.jwt.decode(input.token)[1].sub

token_role := io.jwt.decode(input.token)[1].role

token_expired = true if {
    io.jwt.decode(input.token)[1].exp < 1700000000
} else = false

# ── Human-readable reason ────────────────────────────────
reason = "Token gueltig - Zugriff erlaubt" if {
    allow
} else = "Token abgelaufen oder Issuer nicht vertrauenswuerdig"
