# ──────────────────────────────────────────────────────────
# NPA – Next Policy Agent  |  Fedora-based Container
# ──────────────────────────────────────────────────────────
# Multi-stage build:
#   1) builder  – install deps in venv
#   2) runtime  – lean Fedora image with only what's needed
#
# Build:
#   docker build -t npa .
#
# Run:
#   docker run -p 8443:8443 npa
#   docker run -p 8443:8443 -v ./policies:/policies -v ./data:/data npa
#   docker compose up
# ──────────────────────────────────────────────────────────

# ── Stage 1: Builder ─────────────────────────────────────
FROM registry.fedoraproject.org/fedora:41 AS builder

RUN dnf install -y python3 python3-pip python3-devel gcc && \
    dnf clean all

WORKDIR /build

# Install dependencies first (layer caching)
COPY pyproject.toml README.md ./
RUN python3 -m venv /opt/npa-venv && \
    /opt/npa-venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/npa-venv/bin/pip install --no-cache-dir .

# Copy source and reinstall with actual code
COPY npa/ ./npa/
RUN /opt/npa-venv/bin/pip install --no-cache-dir .


# ── Stage 2: Runtime ─────────────────────────────────────
FROM registry.fedoraproject.org/fedora:41

LABEL maintainer="NPA Team" \
      description="Next Policy Agent – OPA-compatible policy engine" \
      org.opencontainers.image.source="https://github.com/BLS-ISP/NextPolicyAgent"

# Minimal runtime deps only
RUN dnf install -y python3 && \
    dnf clean all && \
    rm -rf /var/cache/dnf

# Copy venv from builder
COPY --from=builder /opt/npa-venv /opt/npa-venv

# Add venv to PATH
ENV PATH="/opt/npa-venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user
RUN useradd --system --create-home --shell /usr/sbin/nologin npa

# Create directories for policies, data, bundles and certs
RUN mkdir -p /policies /data /bundles /certs && \
    chown -R npa:npa /policies /data /bundles /certs

# Copy examples
COPY --chown=npa:npa examples/ /examples/

WORKDIR /home/npa

# Switch to non-root user
USER npa

# NPA default port (HTTPS)
EXPOSE 8443

# Health check via the health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request, ssl; ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE; urllib.request.urlopen('https://localhost:8443/health', context=ctx)" || exit 1

# Default: start NPA server with auto-generated self-signed TLS cert
# Override with environment variables or mount config/certs
ENTRYPOINT ["python3", "-m", "npa", "run"]
CMD ["--addr", "0.0.0.0:8443", "--log-level", "info"]
