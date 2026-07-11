FROM python:3.12-slim

WORKDIR /app

# Install build deps for curl_cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent volume mount point for generated images
RUN mkdir -p /app/images

EXPOSE 8700

CMD ["python", "main.py"]
