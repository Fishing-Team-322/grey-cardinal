# syntax=docker/dockerfile:1.7
FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM caddy:2-alpine

COPY --from=build /app/dist /srv
EXPOSE 5173
CMD ["caddy", "file-server", "--listen", ":5173", "--root", "/srv"]
