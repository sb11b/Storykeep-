FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG API_ORIGIN=http://127.0.0.1:18741
ENV API_ORIGIN=$API_ORIGIN
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app ./
EXPOSE 8080
CMD ["sh", "-c", "npx next start --hostname 0.0.0.0 --port ${PORT:-8080}"]
