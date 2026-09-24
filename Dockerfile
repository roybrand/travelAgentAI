# Wayfinder AI: one image, one process, one port. The backend serves the built React app itself.
#   docker build -t wayfinder .
#   docker run -p 8000:8000 --env-file backend/.env -v wayfinder-data:/app/backend/data -v wayfinder-logs:/app/backend/logs wayfinder
# Secrets come in at run time (--env-file or the host's secret store); they are never baked into the image.

FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN useradd --create-home wayfinder && mkdir -p data logs .cache && chown -R wayfinder data logs .cache
USER wayfinder
# The SQLite database, uploaded photos and activity logs must outlive a redeploy: mount volumes here.
VOLUME ["/app/backend/data", "/app/backend/logs"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
