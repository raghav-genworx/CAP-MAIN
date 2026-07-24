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

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
