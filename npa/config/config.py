"""NPA configuration using Pydantic Settings.

All configuration can be provided via environment variables (NPA_ prefix),
config file, or programmatically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings


class TLSConfig(BaseSettings):
    """TLS/HTTPS configuration — enabled by default."""
    model_config = {"env_prefix": "NPA_TLS_"}

    enabled: bool = True
    cert_file: Path | None = None
    key_file: Path | None = None
    min_version: str = "TLSv1.2"
    auto_generate: bool = True  # Auto-generate self-signed cert for dev


class ServerConfig(BaseSettings):
    model_config = {"env_prefix": "NPA_SERVER_"}

    addr: str = "0.0.0.0"
    port: int = 8443
    workers: int = 1
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    rate_limit: int = 1000  # requests per minute per client
    request_timeout: float = 30.0
    max_request_size: int = 10 * 1024 * 1024  # 10MB


class AuthConfig(BaseSettings):
    model_config = {"env_prefix": "NPA_AUTH_"}

    enabled: bool = False
    token_type: str = "bearer"  # "bearer" or "client_cert"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    api_keys: list[str] = Field(default_factory=list)

    # Web UI login (always enforced for dashboard access)
    ui_username: str = "admin"
    ui_password: str = "admin"


class StorageConfig(BaseSettings):
    model_config = {"env_prefix": "NPA_STORAGE_"}

    backend: str = "memory"  # "memory" or "disk"
    disk_path: Path = Path("npa_data.db")


class BundleSourceConfig(BaseSettings):
    model_config = {"env_prefix": "NPA_BUNDLE_"}

    name: str = "default"
    url: str = ""
    polling_interval: int = 60  # seconds
    auth_token: str = ""


class LoggingConfig(BaseSettings):
    model_config = {"env_prefix": "NPA_LOG_"}

    level: str = "INFO"
    format: str = "json"  # "json" or "text"
    decision_log: bool = False


class NpaConfig(BaseSettings):
    """Root configuration for NPA."""
    model_config = {"env_prefix": "NPA_"}

    tls: TLSConfig = Field(default_factory=TLSConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    bundles: list[BundleSourceConfig] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str | Path) -> NpaConfig:
        """Load configuration from a YAML/JSON file."""
        import json
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(text)
        else:
            data = json.loads(text)
        return cls(**data) if data else cls()
