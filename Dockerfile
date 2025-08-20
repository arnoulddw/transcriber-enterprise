# ./Dockerfile
# Defines the Docker image build process

# Use an official Python runtime as base image.
FROM python:3.11-slim-bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC
# Specify Node.js LTS version major
ENV NODE_VERSION=18

# Install system dependencies:
# - ffmpeg: Required by pydub
# - tini: Minimal init system
# - default-mysql-client: MySQL CLI
# - curl: To fetch Node.js setup script
# - nodejs: Node.js runtime and npm
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        tini \
        default-mysql-client \
        curl \
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and group for security
# Set home directory to /app
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser -d /app -s /sbin/nologin -c "App User" appuser

# Create necessary directories and set base ownership
# These directories are for runtime data and logs, which might be mounted as volumes.
RUN mkdir -p /app/uploads /app/database /app/logs /app/runtime && \
    chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser
WORKDIR /app

# Copy package manager files first to leverage Docker layer caching for Node.js dependencies
COPY --chown=appuser:appuser ./package.json ./
COPY --chown=appuser:appuser ./package-lock.json* ./
# Install Node.js dependencies. Use 'npm ci' if package-lock.json exists for reproducible builds.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Copy Python requirements file and install Python dependencies
COPY --chown=appuser:appuser ./requirements.txt ./
# Install Python packages for the appuser. This will install to /app/.local
RUN pip install --no-cache-dir --user -r requirements.txt
# Prepend the user's local bin directory to PATH
ENV PATH="/app/.local/bin:${PATH}"

# Copy the entire application source code (including Tailwind configs, input CSS)
COPY --chown=appuser:appuser . .

# Build Tailwind CSS for production
RUN npm run build:css:prod

# Compile translation files
RUN /app/.local/bin/pybabel compile -d app/translations

# Expose the port the application will run on
EXPOSE 5004

# Use Tini as the entrypoint
ENTRYPOINT ["/usr/bin/tini", "--"]

# Define the default command to run the application using Gunicorn
# Use the full path to gunicorn installed in the user's local bin (relative to their HOME /app)
CMD ["/app/.local/bin/gunicorn", \
     "--bind", "0.0.0.0:5004", \
     "--workers", "4", \
     "--timeout", "120", \
     "--forwarded-allow-ips", "*", \
     "--log-level", "info", \
     "app:create_app()"]