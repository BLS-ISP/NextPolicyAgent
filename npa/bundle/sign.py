"""Bundle signing and verification using JWT (JWS).

Compatible with OPA bundle signing format.
"""

from __future__ import annotations

import json
from typing import Any

import jwt


class SigningError(Exception):
    pass


class VerificationError(Exception):
    pass


def sign_bundle(
    content_hash: str,
    signing_key: str,
    algorithm: str = "RS256",
    key_id: str | None = None,
    claims: dict[str, Any] | None = None,
) -> str:
    """Sign a bundle content hash and return a JWS token.

    Args:
        content_hash: SHA-256 hash of the bundle contents
        signing_key: PEM-encoded private key (for RSA/EC) or secret (for HMAC)
        algorithm: JWT algorithm (RS256, ES256, HS256, etc.)
        key_id: Optional key ID for the JWT header
        claims: Additional claims to include

    Returns:
        JWS compact serialization string
    """
    payload: dict[str, Any] = {
        "files": [{"name": "bundle", "hash": content_hash, "algorithm": "SHA-256"}],
    }
    if claims:
        payload.update(claims)

    headers: dict[str, Any] = {}
    if key_id:
        headers["kid"] = key_id

    try:
        return jwt.encode(payload, signing_key, algorithm=algorithm, headers=headers or None)
    except Exception as e:
        raise SigningError(f"Failed to sign bundle: {e}") from e


def verify_bundle(
    token: str,
    verification_key: str,
    algorithms: list[str] | None = None,
    expected_hash: str | None = None,
) -> dict[str, Any]:
    """Verify a bundle signature and return the claims.

    Args:
        token: JWS compact serialization string
        verification_key: PEM-encoded public key or HMAC secret
        algorithms: Allowed algorithms (default: RS256)
        expected_hash: If provided, verify the content hash matches

    Returns:
        Decoded claims dict

    Raises:
        VerificationError: If signature or hash verification fails
    """
    algorithms = algorithms or ["RS256"]

    try:
        claims = jwt.decode(token, verification_key, algorithms=algorithms)
    except jwt.ExpiredSignatureError as e:
        raise VerificationError("Signature expired") from e
    except jwt.InvalidTokenError as e:
        raise VerificationError(f"Invalid signature: {e}") from e

    if expected_hash:
        files = claims.get("files", [])
        if not files:
            raise VerificationError("No file hashes in signature")

        found = False
        for f in files:
            if f.get("hash") == expected_hash:
                found = True
                break

        if not found:
            raise VerificationError("Content hash mismatch")

    return claims


def create_signatures_json(token: str) -> str:
    """Create the .signatures.json file content for a bundle."""
    return json.dumps({"signatures": [token]}, separators=(",", ":"))
