# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS dependencies

WORKDIR /app

COPY package*.json ./
RUN npm ci

FROM dependencies AS development

ENV VITE_API_GATEWAY_BASE_URL=/api

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

FROM dependencies AS builder

COPY . .

ARG VITE_API_GATEWAY_BASE_URL=/api

ENV VITE_API_GATEWAY_BASE_URL=$VITE_API_GATEWAY_BASE_URL

RUN --mount=type=secret,id=frontend_env,target=/app/.env npm run build

FROM nginx:1.27-alpine

# The backend serves /api/v1/core itself since the gateway was folded in.
# Override back to the gateway URL to roll the cutover back.
ENV API_GATEWAY_PROXY_URL=http://core-assessment-platform-service:8000/api/v1

COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
