# Use a lightweight Python base image
FROM python:3.11-slim

# Prevent Python from creating .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system-level dependencies (add more if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user for better security
RUN useradd -ms /bin/bash appuser

# Set the working directory
WORKDIR /app

# Copy and install Python dependencies first to leverage Docker layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the application code
COPY . /app

# Switch to the non-root user
USER appuser

# Default command (Docker Compose will override mode)
CMD ["python", "main.py"]
