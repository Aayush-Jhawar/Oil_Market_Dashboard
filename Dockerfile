# Multi-stage build for minimal image size
FROM python:3.11-slim as backend

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Build frontend separately then serve from backend
FROM node:20-alpine as frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# Final stage - combine everything
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from backend stage
COPY --from=backend /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend /app/backend ./backend/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Copy full source
COPY . .

# Setup runtime databases from deploy seeds
RUN cp backend/energy_deploy.db backend/energy.db || true
RUN cp DB/bars_15min_deploy.db DB/bars_15min_latest.db || true

EXPOSE 7860

ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# No Docker HEALTHCHECK: HF Spaces does its own port-based readiness probe on
# 7860. A custom healthcheck here can keep the Space pinned at "Starting" even
# when the app is serving, so we let HF handle readiness.

# Serve frontend as static files + API backend
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860", "--app-dir", "backend"]
