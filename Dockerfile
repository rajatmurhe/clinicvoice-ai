FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY cloud-frontend/package*.json ./
RUN npm ci
COPY cloud-frontend/ ./
RUN npm run build

FROM node:22-bookworm-slim
WORKDIR /app/backend
COPY backend/package*.json ./
RUN npm ci --omit=dev
COPY backend/ ./
COPY python-agents/clinics/ /app/python-agents/clinics/
COPY --from=frontend /build/dist/ /app/cloud-frontend/dist/
EXPOSE 5050
CMD ["node", "server-cloud.js"]
