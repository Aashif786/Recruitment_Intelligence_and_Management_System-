FROM python:3.11-slim

WORKDIR /app

# Install all necessary system dependencies for AI, Database, and PDF generation
RUN apt-get update && apt-get install -y \
    curl \
    libpq-dev \
    gcc \
    g++ \
    python3-dev \
    pkg-config \
    libcairo2-dev \
    libffi-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Upgrade pip first
RUN pip install --upgrade pip

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 10000

ENV BACKEND_START_MODE=docker

RUN addgroup --system app && adduser --system --ingroup app app
USER app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]
