FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 COGNITH_BOOTSTRAPPED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Cloud Run sets PORT. GEMINI_API_KEY comes from Secret Manager, never the image.
CMD exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}
