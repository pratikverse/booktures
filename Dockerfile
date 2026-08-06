FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY backend/ .

ENV PORT=7860
EXPOSE 7860

CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
