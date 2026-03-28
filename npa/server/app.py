"""FastAPI application factory for NPA.

Creates the HTTPS-enabled REST API with all OPA-compatible routes,
middleware, and security features.  Serves the web UI at /.
"""

from __future__ import annotations

import ipaddress
import ssl
import tempfile
import time
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import JSONResponse

from npa.config.config import NpaConfig
from npa.storage.base import Storage
from npa.storage.inmemory import InMemoryStorage
from npa.storage.disk import DiskStorage

logger = structlog.get_logger(__name__)

# Path to bundled static assets (HTML/CSS/JS for the web UI)
_STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: NpaConfig | None = None) -> FastAPI:
    """Create and configure the NPA FastAPI application."""
    config = config or NpaConfig()

    app = FastAPI(
        title="NPA – Next Policy Agent",
        description="OPA-compatible policy engine with HTTPS-first design",
        version="0.1.0",
        docs_url="/v1/docs",
        redoc_url="/v1/redoc",
    )

    # --- Storage ---
    storage: Storage
    if config.storage.backend == "disk":
        storage = DiskStorage(config.storage.disk_path)
    else:
        storage = InMemoryStorage()

    app.state.config = config
    app.state.storage = storage
    app.state.compiler = None  # Initialized on first policy load
    app.state.evaluator = None
    app.state.start_time = time.time()

    # Decision log (in-memory ring buffer for the web UI)
    from npa.server.routes.ui_api import DecisionLog
    app.state.decision_log = DecisionLog()

    # --- Plugin manager ---
    from npa.plugins.manager import (
        PluginManager, BundlePlugin, DecisionLogPlugin, StatusPlugin, DiscoveryPlugin,
    )
    plugin_manager = PluginManager()
    plugin_manager.store = storage
    plugin_manager.info = {"labels": config.labels, "version": "0.1.0"}

    # Register built-in plugins (configured via config or env)
    bundle_cfg: dict[str, Any] = {}
    for bs in config.bundles:
        bundle_cfg[bs.name] = {"url": bs.url, "polling": {"min_delay_seconds": bs.polling_interval}}
    if bundle_cfg:
        plugin_manager.register(BundlePlugin({"bundles": bundle_cfg}))

    if config.logging.decision_log:
        plugin_manager.register(DecisionLogPlugin({"console": True}))

    plugin_manager.register(StatusPlugin())
    plugin_manager.register(DiscoveryPlugin())

    app.state.plugin_manager = plugin_manager

    @app.on_event("startup")
    async def _start_plugins() -> None:
        await plugin_manager.start_all()

    @app.on_event("shutdown")
    async def _stop_plugins() -> None:
        await plugin_manager.stop_all()

    # --- GZip compression (Accept-Encoding: gzip) ---
    app.add_middleware(GZipMiddleware, minimum_size=256)

    # --- CORS ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.server.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Security headers ---
    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Use a permissive CSP for UI pages (allows CodeMirror CDN);
        # Swagger/ReDoc need CDN + inline; strict CSP for API responses.
        path = request.url.path
        if path == "/" or path.startswith("/static"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
                "font-src 'self' https://cdnjs.cloudflare.com; "
                "img-src 'self' data:; "
                "connect-src 'self'"
            )
        elif path in ("/v1/docs", "/v1/redoc", "/openapi.json"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://cdn.jsdelivr.net https://fastapi.tiangolo.com; "
                "worker-src 'self' blob:"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response

    # --- Auth middleware ---
    if config.auth.enabled:
        from npa.server.auth import AuthMiddleware
        app.add_middleware(AuthMiddleware, config=config.auth)

    # --- UI session guard (protects dashboard + UI API, not programmatic API) ---
    from npa.server.routes.ui_api import check_ui_session

    _UI_AUTH_EXEMPT = {"/v1/ui/login", "/v1/ui/session", "/health",
                       "/health/live", "/health/ready",
                       "/v1/docs", "/v1/redoc", "/openapi.json"}

    @app.middleware("http")
    async def ui_session_guard(request: Request, call_next: Any) -> Response:
        path = request.url.path

        # Static assets, health probes, login endpoint -> always allowed
        if path in _UI_AUTH_EXEMPT or path.startswith("/static"):
            return await call_next(request)

        # The root page (/) and UI API (/v1/ui/*) require an active session
        needs_session = (path == "/" or path.startswith("/v1/ui"))
        if needs_session and not check_ui_session(request):
            if path == "/":
                # Serve the HTML anyway — the JS will show the login screen
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )

        return await call_next(request)

    # --- Import routes ---
    from npa.server.routes.data import router as data_router
    from npa.server.routes.data import v0_router as data_v0_router
    from npa.server.routes.policy import router as policy_router
    from npa.server.routes.query import router as query_router
    from npa.server.routes.health import router as health_router
    from npa.server.routes.ui_api import router as ui_router
    from npa.server.routes.config import router as config_router
    from npa.server.routes.metrics import router as metrics_router
    from npa.server.routes.bundles import router as bundles_router

    app.include_router(health_router)
    app.include_router(data_router, prefix="/v1")
    app.include_router(data_v0_router, prefix="/v0")
    app.include_router(policy_router, prefix="/v1")
    app.include_router(query_router, prefix="/v1")
    app.include_router(config_router, prefix="/v1")
    app.include_router(bundles_router, prefix="/v1")
    app.include_router(metrics_router)
    app.include_router(ui_router)

    # --- Web UI ---
    @app.get("/", include_in_schema=False)
    async def serve_ui():
        """Serve the NPA web interface."""
        return FileResponse(str(_STATIC_DIR / "index.html"))

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app


def _generate_self_signed_cert(cert_dir: Path) -> tuple[str, str]:
    """Generate a self-signed certificate for development."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "NPA Development"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NPA"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path = cert_dir / "npa-dev.crt"
    key_path = cert_dir / "npa-dev.key"

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))

    return str(cert_path), str(key_path)


def run_server(config: NpaConfig | None = None) -> None:
    """Start the NPA server with optional HTTPS."""
    config = config or NpaConfig()
    app = create_app(config)

    ssl_kwargs: dict[str, Any] = {}
    if config.tls.enabled:
        if config.tls.cert_file and config.tls.key_file:
            ssl_kwargs["ssl_certfile"] = str(config.tls.cert_file)
            ssl_kwargs["ssl_keyfile"] = str(config.tls.key_file)
        elif config.tls.auto_generate:
            cert_dir = Path(tempfile.mkdtemp(prefix="npa-certs-"))
            cert_file, key_file = _generate_self_signed_cert(cert_dir)
            ssl_kwargs["ssl_certfile"] = cert_file
            ssl_kwargs["ssl_keyfile"] = key_file
            logger.info("Auto-generated dev TLS certificate", cert_dir=str(cert_dir))

    scheme = "https" if config.tls.enabled else "http"
    logger.info(
        f"Starting NPA server",
        addr=config.server.addr,
        port=config.server.port,
        scheme=scheme,
    )

    uvicorn.run(
        app,
        host=config.server.addr,
        port=config.server.port,
        workers=config.server.workers,
        timeout_keep_alive=int(config.server.request_timeout),
        log_level="info",
        **ssl_kwargs,
    )
