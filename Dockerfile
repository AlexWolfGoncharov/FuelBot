# Multi-stage build for optimized image size
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libheif-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/dependencies -r requirements.txt

# Runtime stage - use even slimmer base
FROM python:3.11-slim

WORKDIR /app

# Install ONLY runtime dependencies for HEIF support
RUN apt-get update && apt-get install -y --no-install-recommends \
    libheif1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy only installed packages from builder (not the whole site-packages)
COPY --from=builder /app/dependencies /usr/local/lib/python3.11/site-packages

# Copy application code
COPY . .

# Create directories for data and logs
RUN mkdir -p /app/data /app/logs

# Create non-root user and set permissions
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# No VOLUME here — Railway forbids VOLUME in Dockerfiles; use Railway volumes or Postgres.
# Local Docker: mount ./data in docker-compose.yml if you need persistent SQLite.

# Default SQLite path (Railway: set DATABASE_URL from Postgres — overrides this).
ENV DATABASE_URL=sqlite+aiosqlite:///./data/fuel_tracker.db

# Run the bot
CMD ["python", "bot/main.py"]
