# mochi-web: the web app, built with Node and served by nginx, which also proxies /api, /ws and
# /healthz to the backend (nginx/default.conf.template). Build context: apps/web.
#   docker build -t mochi-web apps/web
#   docker run --rm -p 8080:8080 -e BACKEND_URL=https://<backend> mochi-web
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
ENV PORT=8080 BACKEND_URL=http://host.docker.internal:8000 NGINX_ENVSUBST_FILTER="^(PORT|BACKEND_URL|BACKEND_HOST)$"
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY nginx/15-backend-host.envsh /docker-entrypoint.d/15-backend-host.envsh
RUN chmod +x /docker-entrypoint.d/15-backend-host.envsh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
