# Deployment Guide - Railway.app

This guide walks you through deploying the Energy Dashboard to Railway.app with automatic GitHub integration.

## What is Railway?

Railway is a modern deployment platform that:
- ✅ Supports full-stack apps (frontend + backend)
- ✅ Automatic deploys from GitHub (push to deploy)
- ✅ Includes PostgreSQL database
- ✅ Free tier with $5/month credit
- ✅ Simple environment variable management
- ✅ Production-ready monitoring & logs

## Prerequisites

1. GitHub account with your code pushed to a repository
2. Railway account (free at https://railway.app)
3. API keys ready:
   - EIA API key from https://www.eia.gov/opendata/
   - Hugging Face token (optional): https://huggingface.co/settings/tokens

## Step-by-Step Deployment

### 1. Push Code to GitHub

If not already done, push your Dashboard_v3 repository to GitHub:

```bash
git init
git add .
git commit -m "Initial commit: Energy Dashboard v3"
git remote add origin https://github.com/YOUR_USERNAME/Dashboard_v3.git
git branch -M main
git push -u origin main
```

### 2. Sign Up / Log In to Railway

- Go to https://railway.app
- Click "Start a New Project"
- Choose "Deploy from GitHub repo"

### 3. Connect GitHub Repository

- Authorize Railway to access your GitHub account
- Select your `Dashboard_v3` repository
- Select the `main` branch

### 4. Create Services

Railway will detect your project. Create two services:

#### Service 1: Frontend (React)
```
Name: dashboard-frontend
Type: Node.js
Build Command: cd frontend && npm install && npm run build
Start Command: npx serve -s frontend/dist -l 3000
Environment: VITE_API_URL=$BACKEND_URL
```

#### Service 2: Backend (FastAPI)
```
Name: dashboard-backend
Type: Python
Build Command: pip install -r backend/requirements.txt
Start Command: cd backend && python -m uvicorn main:app --host 0.0.0.0 --port $PORT
```

### 5. Add PostgreSQL Database

In Railway:
1. Click "Add Service" → "Add from Marketplace"
2. Select "PostgreSQL"
3. This creates a new database instance

### 6. Configure Environment Variables

Go to each service and add environment variables:

#### Backend Service Variables:
```
DATABASE_URL = ${{ Postgres.DATABASE_URL }}
EIA_API_KEY = your_eia_api_key
HF_API_KEY = your_hugging_face_key (optional)
PYTHONUNBUFFERED = 1
```

#### Frontend Service Variables:
```
VITE_API_URL = https://your-backend-url.railway.app
VITE_API_TIMEOUT = 30000
```

(Railway will provide your-backend-url after deployment)

### 7. Deploy

1. Click "Deploy" button
2. Watch the build logs to ensure no errors
3. Once deployed, you'll get:
   - Frontend URL: `https://dashboard-frontend.railway.app`
   - Backend URL: `https://dashboard-backend.railway.app`
   - API Docs: `https://dashboard-backend.railway.app/docs`

### 8. Update Frontend Configuration

After backend is deployed:
1. Get your backend URL from Railway
2. Update frontend's `VITE_API_URL` environment variable
3. Re-deploy frontend

## Alternative: Deploy Backend Only + Frontend to Vercel

If you prefer using Vercel for the frontend:

### Frontend on Vercel:
```bash
cd frontend
npm install
npm run build
# Then connect to Vercel via GitHub
```

Set environment variable on Vercel:
```
VITE_API_URL = https://your-backend-url.railway.app
```

### Backend on Railway:
(Follow steps above for backend only)

## Monitoring & Logs

In Railway dashboard:
- Click service → "Logs" tab to see real-time logs
- Click "Metrics" to monitor CPU, memory, network usage
- Alerts can be set up for deployment failures

## Troubleshooting

### Build Fails with Python Errors
- Ensure `backend/requirements.txt` is up to date
- Check that Python version is 3.11+ in build logs

### Frontend Can't Connect to Backend
- Verify `VITE_API_URL` is set correctly (includes https://)
- Check CORS is enabled in `backend/main.py`
- Check backend service is running (green status in Railway)

### Database Connection Error
- Verify `DATABASE_URL` is properly set from PostgreSQL service
- Check database is initialized (first deploy may need table creation)

### 503 Service Unavailable
- Check backend service logs for errors
- Ensure all required environment variables are set

## Costs

- **Starter Plan (Free)**: $0 with $5/month credit
  - Suitable for development and small deployments
  - PostgreSQL included
  - 500 hours runtime/month limit

- **Usage-Based Pricing**: Pay for what you use
  - After free credits, typically $5-15/month for a dashboard

## Custom Domain

To add your custom domain:
1. Go to Railway service settings
2. Click "Domains"
3. Add custom domain (requires DNS configuration at your domain provider)
4. Follow Railway's CNAME instructions

## Auto-Deployment Updates

Every time you push to GitHub main branch:
1. Railway automatically triggers a new build
2. Services rebuild and redeploy
3. No manual intervention needed
4. Previous versions kept for rollback

## Next Steps

1. Monitor logs in Railway dashboard daily first week
2. Set up uptime monitoring (Railway provides this)
3. Consider adding backup strategy for database
4. Plan for database migrations as project grows

---

**Questions?** Check Railway documentation at https://docs.railway.app
