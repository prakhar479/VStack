FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy shared configuration files
COPY config.py /config.py
COPY logging_config.py /logging_config.py

# Copy requirements and install Python dependencies
COPY client/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY client/ .

EXPOSE 8086

CMD ["python", "server.py"]