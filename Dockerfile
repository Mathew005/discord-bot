# Use lightweight python base image supporting ARM64 natively
FROM python:3.11-slim

# Install system dependencies, Java 17 for Lavalink, and curl
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libopus-dev \
    ffmpeg \
    openjdk-17-jre-headless \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Download Lavalink v4.2.2 jar file
RUN curl -L -o /app/Lavalink.jar https://github.com/lavalink-devs/Lavalink/releases/download/4.2.2/Lavalink.jar

# Copy dependency manifest and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY . .

# Ensure entrypoint is executable
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
