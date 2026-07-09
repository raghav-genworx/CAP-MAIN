# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_GATEWAY_BASE_URL=/api
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_APP_ID

RUN --mount=type=secret,id=frontend_env,target=/app/.env \
  set -eu; \
  export VITE_API_GATEWAY_BASE_URL="${VITE_API_GATEWAY_BASE_URL}"; \
  if [ -n "${VITE_FIREBASE_API_KEY:-}" ]; then export VITE_FIREBASE_API_KEY="${VITE_FIREBASE_API_KEY}"; fi; \
  if [ -n "${VITE_FIREBASE_AUTH_DOMAIN:-}" ]; then export VITE_FIREBASE_AUTH_DOMAIN="${VITE_FIREBASE_AUTH_DOMAIN}"; fi; \
  if [ -n "${VITE_FIREBASE_PROJECT_ID:-}" ]; then export VITE_FIREBASE_PROJECT_ID="${VITE_FIREBASE_PROJECT_ID}"; fi; \
  if [ -n "${VITE_FIREBASE_APP_ID:-}" ]; then export VITE_FIREBASE_APP_ID="${VITE_FIREBASE_APP_ID}"; fi; \
  npm run build

FROM nginx:1.27-alpine

ENV API_GATEWAY_PROXY_URL=http://api-gateway-service:8000/api/v1

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
