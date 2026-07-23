# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_GATEWAY_BASE_URL=/api
ARG VITE_FIREBASE_API_KEY=
ARG VITE_FIREBASE_AUTH_DOMAIN=
ARG VITE_FIREBASE_PROJECT_ID=
ARG VITE_FIREBASE_APP_ID=

ENV VITE_API_GATEWAY_BASE_URL=$VITE_API_GATEWAY_BASE_URL

RUN --mount=type=secret,id=frontend_env,target=/tmp/frontend.env,required=false \
    sh -eu -c 'api_base="$VITE_API_GATEWAY_BASE_URL"; \
      if [ -f /tmp/frontend.env ]; then set -a; . /tmp/frontend.env; set +a; fi; \
      export VITE_API_GATEWAY_BASE_URL="$api_base"; \
      : "${VITE_FIREBASE_API_KEY:?VITE_FIREBASE_API_KEY is required}"; \
      : "${VITE_FIREBASE_AUTH_DOMAIN:?VITE_FIREBASE_AUTH_DOMAIN is required}"; \
      : "${VITE_FIREBASE_PROJECT_ID:?VITE_FIREBASE_PROJECT_ID is required}"; \
      : "${VITE_FIREBASE_APP_ID:?VITE_FIREBASE_APP_ID is required}"; \
      export VITE_FIREBASE_API_KEY VITE_FIREBASE_AUTH_DOMAIN VITE_FIREBASE_PROJECT_ID VITE_FIREBASE_APP_ID; \
      npm run build'

FROM nginx:1.27-alpine

ENV API_GATEWAY_PROXY_URL=http://api-gateway-service:8000/api/v1

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
