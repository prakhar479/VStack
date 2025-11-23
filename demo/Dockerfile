FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir aiohttp aiofiles

# Copy demo files
COPY demo/ .

EXPOSE 8085

CMD ["python", "server.py"]