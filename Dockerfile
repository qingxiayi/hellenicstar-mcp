FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends     build-essential gcc     librsvg2-bin nodejs fonts-noto-cjk fonts-noto-core fonts-noto-extra     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY . .

RUN useradd --create-home mcp && mkdir -p /app/data /app/cache && chown -R mcp:mcp /app
USER mcp

EXPOSE 5000

CMD ["python", "-m", "uvicorn", "mcp_server:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
