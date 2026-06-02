#!/bin/bash

# Build script for Railway deployment
# Installs dependencies for both frontend and backend

echo "📦 Installing backend dependencies..."
pip install -r backend/requirements.txt

echo "📦 Installing frontend dependencies..."
cd frontend
npm install

echo "🔨 Building frontend..."
npm run build

echo "✅ Build complete!"
echo "Backend ready at port 8000"
echo "Frontend built in frontend/dist"
