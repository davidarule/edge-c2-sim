FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_CESIUM_ION_TOKEN
ARG VITE_WS_URL=ws://localhost:8765
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Geodata is mounted as a volume or copied at compose level
EXPOSE 3000
