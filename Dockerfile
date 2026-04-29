FROM python:3.11-slim

# Metadata
LABEL maintainer="Dinesh"
LABEL description="JARVIS Personal AI Companion"

# Security: non-root user
RUN groupadd -r jarvis && useradd -r -g jarvis jarvis

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    git \
    openssh-client \
    sshpass \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=jarvis:jarvis . .

# Switch to non-root user
USER jarvis

# Expose port
EXPOSE 8000

# Health check — hits /api/v1/health every 30s
# Allows 60s start period for Qdrant connection
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Production server
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--log-level", "info"]
