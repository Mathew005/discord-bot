# Use lightweight python base image supporting ARM64 natively
FROM python:3.11-slim

# Install system dependencies needed for compiling PyNaCl
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno (preferred JS runtime for yt-dlp EJS)
ENV DENO_INSTALL=/usr/local
RUN curl -fsSL https://deno.land/install.sh | sh

WORKDIR /app

# Copy dependency manifest and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY . .

CMD ["python", "main.py"]
