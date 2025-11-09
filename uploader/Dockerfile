FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared configuration files
COPY config.py /config.py
COPY logging_config.py /logging_config.py

# Copy requirements and install Python dependencies
COPY uploader/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY uploader/ .

# Create temp directory for video processing
RUN mkdir -p /tmp/uploads

EXPOSE 8082

CMD ["python", "main.py"]