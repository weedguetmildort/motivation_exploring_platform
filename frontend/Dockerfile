# Frontend - PROD (multi-stage)

# --- Build stage ---
FROM node:20.11.1-alpine AS builder

# set working directory
WORKDIR /app

# install dependencies first (cache-friendly)
COPY package*.json ./
RUN npm ci || npm install

# copy rest of the frontend
COPY . .

# Accept backend URL from build args
ARG BACKEND_URL
ENV BACKEND_URL=$BACKEND_URL

RUN npm run build

# --- Runtime stage ---
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Copy only what's needed to run "next start"
# COPY --from=builder /app/package*.json ./
# COPY --from=builder /app/node_modules ./node_modules
# COPY --from=builder /app/.next ./.next

# COPY --from=builder /app/.next/standalone ./
# COPY --from=builder /app/.next/static ./.next/static
# COPY --from=builder /app/public ./public

COPY --from=builder /app/.next/standalone /app
COPY --from=builder /app/.next/static /app/.next/static
COPY --from=builder /app/public /app/public

# Heroku (and many PaaS) inject $PORT; default to 3000 locally
ENV PORT=3000

# expose port
EXPOSE 3000

# CMD ["sh", "-lc", "npx next start -p ${PORT}"]
CMD ["node", "server.js"]
