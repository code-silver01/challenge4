# Stage 1: Build the React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

# Stage 2: Build the FastAPI backend and serve static files
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Copy built frontend static files to backend/static
COPY --from=frontend-builder /app/frontend/dist /app/static

EXPOSE 8000

# Railway sets PORT dynamically, but Uvicorn needs to listen on it. 
# We'll use 8000 as default if PORT is not set.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
