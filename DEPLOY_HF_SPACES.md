# Deploy to Hugging Face Spaces - FREE

Deploy your Energy Dashboard to Hugging Face Spaces in minutes — completely free, just like the example you shared.

## Quick Start (3 Steps)

### 1. Create Hugging Face Account

- Go to https://huggingface.co/join
- Sign up (free, no credit card needed)
- Verify email

### 2. Create New Space

- Go to https://huggingface.co/spaces
- Click "Create new Space"
- **Space name:** `energy-dashboard` (or your choice)
- **License:** Choose any (or select your preference)
- **Space SDK:** Select "Docker"
- **Space hardware:** "CPU basic" (free)
- **Private:** Select as needed
- Click "Create Space"

### 3. Deploy Your Code

Hugging Face Spaces will create a git repository. Push your code:

```bash
# Navigate to your project
cd Dashboard_v3

# Initialize git if not already done
git init
git add .
git commit -m "Initial deployment"

# Add Hugging Face as remote (you'll see this in your Space)
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/energy-dashboard

# Push to Hugging Face
git push hf main
```

**Done!** Your app will be live at:
```
https://YOUR_USERNAME-energy-dashboard.hf.space
```

---

## Why Hugging Face Spaces?

✅ **Completely Free**
- Docker containers supported
- Unlimited public spaces
- No credit card needed
- No storage limits for code

✅ **Easy Deployment**
- Git-based (just git push)
- Automatic builds from Dockerfile
- Auto-restarts if app crashes
- Logs visible in web UI

✅ **Perfect for This Project**
- Full Docker support for Python + Node
- Built for ML/data science (good fit for finance dashboard)
- Community-friendly
- Easy to share with URL

---

## Detailed Setup Guide

### Step 1: Create Hugging Face Account

1. Go to https://huggingface.co/join
2. Fill in email, password, username
3. Verify your email
4. Accept terms

### Step 2: Create New Space

1. Go to https://huggingface.co/new-space
2. Fill in:
   - **Owner:** Select your account
   - **Space name:** `energy-dashboard` (lowercase, hyphens ok)
   - **Space SDK:** Select "Docker" (important!)
   - **Space hardware:** "CPU basic" (free option)
   - **Select the Space visibility:** "Public" or "Private"
3. Click "Create Space"

Hugging Face creates a git repository and shows you the commands.

### Step 3: Set Up Your Local Repository

In your project root:

```bash
# Initialize git (if not already initialized)
git init
git add .
git commit -m "Initial commit: Energy Dashboard"

# Add Hugging Face remote (copy URL from your Space page)
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/energy-dashboard.git

# Push to Hugging Face (first time)
git push -u hf main
```

The `-u hf main` sets up tracking. Future pushes are just `git push hf`.

### Step 4: Set Environment Variables

1. Go to your Space: https://huggingface.co/spaces/YOUR_USERNAME/energy-dashboard
2. Click "Settings" (top right)
3. Scroll to "Repository secrets"
4. Click "Add a secret" and add:

```
Name: EIA_API_KEY
Value: your_eia_api_key_here
```

```
Name: HF_API_KEY
Value: your_hugging_face_token_here
```

These are automatically injected as environment variables when your container runs.

### Step 5: Wait for Build

1. Go to "App" tab (in your Space)
2. Watch the build logs
3. Once it says "Running", your app is live!

---

## What's Included in Free Tier

| Feature | Status |
|---------|--------|
| Docker hosting | ✅ Yes |
| CPU compute | ✅ Shared (free) |
| Storage | ✅ Unlimited for code |
| Bandwidth | ✅ Unlimited |
| Custom domain | ❌ Uses hf.space subdomain |
| Concurrent users | ✅ Limited, but good for dashboard |
| Auto-restart | ✅ Yes |
| HTTPS | ✅ Included |

---

## Update Your App (Push New Code)

Every time you update your code:

```bash
git add .
git commit -m "Update: fix dashboard layout"
git push hf
```

Hugging Face automatically rebuilds and redeploys.

---

## File Structure (What Hugging Face Needs)

Your existing Dockerfile should work! Hugging Face will:
1. Read `Dockerfile` 
2. Build the image
3. Expose port (set in Dockerfile)
4. Run your container

The existing setup is already compatible.

---

## Troubleshooting

### Build Fails

Check the build logs in your Space:
1. Go to Space → "App" tab
2. Scroll down to see build output
3. Look for error messages

Common issues:
- **Missing requirements:** Check `backend/requirements.txt` is complete
- **Python version:** Dockerfile uses Python 3.11 (should be fine)
- **Port mismatch:** Ensure Dockerfile exposes port 8000

### App Won't Start

Check runtime logs:
1. Space → "App" tab
2. Look for runtime errors
3. Scroll down for application logs

### Slow Performance

Free tier has limited CPU. If slow:
- Consider upgrading Space hardware (paid option)
- Or optimize your backend queries

### Need to Restart

Click "Restart" in the Space interface.

---

## Custom Domain (Optional)

Hugging Face Spaces doesn't support direct custom domains on free tier, but you can:
1. Use a URL shortener (short.link)
2. Upgrade Space (paid feature)
3. Use subdomain forwarding through DNS provider

---

## Advanced: GitHub Integration

For automatic deploys when you push to GitHub:

1. Push code to GitHub repo
2. In HF Space settings → "Linked Repositories"
3. Link your GitHub repo
4. Enable "Auto-sync from GitHub"

Now every push to GitHub automatically deploys to Spaces!

---

## Limits & Quotas

Free tier limits (very generous):
- **Storage:** Unlimited
- **Build time:** 1 hour per build
- **Concurrent connections:** Shared (but good for dashboard)
- **Compute:** CPU basic (sufficient for your needs)

You can always upgrade hardware if needed.

---

## Your Live URL

Once deployed, your dashboard will be at:

```
https://YOUR_USERNAME-energy-dashboard.hf.space
```

Example:
```
https://aayush-energy-dashboard.hf.space
```

Share this URL directly with anyone!

---

## Quick Reference

```bash
# First time setup
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/energy-dashboard.git
git push -u hf main

# Update code (after setup)
git add .
git commit -m "Your message"
git push hf

# Check status
# Go to: https://huggingface.co/spaces/YOUR_USERNAME/energy-dashboard
```

---

## Comparison: HF Spaces vs Others

| Platform | Free | Setup | Best For |
|----------|------|-------|----------|
| **HF Spaces** | ✅ Yes | Easy | ML/Finance dashboards, Docker apps |
| **Fly.io** | ✅ Yes | Medium | Full-stack production apps |
| **Railway** | ✅ Yes | Medium | Full-stack with PostgreSQL |
| **Vercel** | ✅ Yes | Easy | Frontend only |

---

## Support

- **HF Spaces Docs:** https://huggingface.co/docs/hub/spaces
- **Docker Support:** https://huggingface.co/docs/hub/spaces-sdks-docker
- **HF Community:** https://huggingface.co/discussions/spaces

---

## Next Steps

1. Create account at https://huggingface.co
2. Create new Space (Docker SDK)
3. Push your code with git
4. Set environment variables in Space settings
5. Wait for build to complete
6. Share your live URL: `https://your-username-energy-dashboard.hf.space`

Done! 🚀
