# Use lightweight python base image supporting ARM64 natively
FROM python:3.11-slim

# Install system dependencies needed for compiling PyNaCl & Discord voice support
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libopus-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY . .

CMD ["python", "main.py"]
