FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy source code
COPY pyproject.toml .
COPY simulator/ simulator/
COPY scripts/ scripts/

# Install package with all dependencies
RUN pip install --no-cache-dir .

# Copy remaining files (config, geodata, etc.)
COPY config/ config/
COPY geodata/ geodata/

CMD ["edge-c2-sim", "--scenario", "config/scenarios/demo_combined.yaml", "--speed", "1", "--transport", "ws,console"]
