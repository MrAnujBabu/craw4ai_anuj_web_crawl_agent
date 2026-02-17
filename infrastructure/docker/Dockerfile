FROM python:3.11-slim

# Install system deps for crawl4ai (browser automation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates fonts-liberation libnss3 libatk-bridge2.0-0 \
    libdrm2 libxkbcommon0 libgbm1 libasound2 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install crawl4ai and deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Copy crawl4ai source (with seo_audit layer)
COPY crawl4ai/ ./crawl4ai/

# Copy the runner script
COPY infrastructure/docker/run_audit.py .

ENTRYPOINT ["python", "run_audit.py"]
