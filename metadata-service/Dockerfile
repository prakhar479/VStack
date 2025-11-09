FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared configuration files
COPY config.py /config.py
COPY logging_config.py /logging_config.py

# Copy requirements and install Python dependencies
COPY metadata-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY metadata-service/ .

# Create data directory for SQLite database
RUN mkdir -p /data

EXPOSE 8080

CMD ["python", "main.py"]