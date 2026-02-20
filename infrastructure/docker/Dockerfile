FROM python:3.11-slim

# System deps for crawl4ai browser automation
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates fonts-liberation libnss3 libatk-bridge2.0-0 \
    libdrm2 libxkbcommon0 libgbm1 libasound2 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Copy crawl4ai source (with seo_audit layer)
# NOTE: The deploy script copies crawl4ai/ into this directory before build.
# See infrastructure/deploy.sh
COPY crawl4ai/ ./crawl4ai/

# Copy the HTTP server
COPY server.py .

EXPOSE 8000

CMD ["python", "server.py"]
