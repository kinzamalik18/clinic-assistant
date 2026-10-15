# Build the React app.
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Run the API, which also serves the built frontend.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 app
WORKDIR /app/backend

COPY backend/pyproject.toml ./
COPY backend/app ./app
# Editable install keeps the code next to its data folder, which the app locates
# relative to its own source files.
RUN pip install -e . && mkdir -p var && chown app:app var
COPY backend/data ./data
COPY --from=frontend /build/dist /app/frontend/dist

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)"

# Most hosts set PORT. --proxy-headers only trusts addresses listed in FORWARDED_ALLOW_IPS.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
