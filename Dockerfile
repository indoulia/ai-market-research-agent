FROM python:3.11-slim

# xgboost requires libgomp1 (OpenMP) at runtime on Debian slim images.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY api/ api/
COPY scripts/ scripts/
COPY alembic.ini .
COPY migrations/ migrations/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
