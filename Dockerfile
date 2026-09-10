FROM node:22-alpine AS web
WORKDIR /web
ARG BUILD_SHA=unknown
ARG BUILD_TIME=
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_OUTPUT=export
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_BUILD_SHA=$BUILD_SHA
RUN printf '{"sha":"%s","time":"%s"}\n' "$BUILD_SHA" "${BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}" > /build-info.json \
    && npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=web /build-info.json ./build-info.json
COPY --from=web /web/out ./frontend_out
COPY start.sh /start.sh
RUN chmod +x /start.sh
ENV PYTHONPATH=/app
ENV FRONTEND_DIR=/app/frontend_out
ENV SEED_DEMO=1
EXPOSE 8080
CMD ["/start.sh"]
