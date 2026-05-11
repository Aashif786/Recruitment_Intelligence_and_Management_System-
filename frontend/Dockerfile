# Stage 1: Build
FROM node:20-slim AS builder

# Install build tools
RUN apt-get update && apt-get install -y \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package*.json ./
COPY patch-lightswind.js ./

# Force a fresh install for the current platform
RUN npm install

COPY . .
RUN npm run build

# Stage 2: Runtime
FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*


COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
