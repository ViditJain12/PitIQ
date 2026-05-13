# Stage 1: Build React app
FROM node:20-slim AS builder
WORKDIR /app
COPY frontend/package*.json .
RUN npm ci
COPY frontend .

# Empty VITE_API_URL → relative URLs → nginx proxies to backend
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
