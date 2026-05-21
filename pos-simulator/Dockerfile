# =============================================================================
# POS Simulator / Event Gateway
# =============================================================================
FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY app.py .

EXPOSE 9090
ENV PYTHONUNBUFFERED=1

CMD ["python", "app.py"]
