# 🚀 FYPilot Backend - Render Deployment Guide

Complete step-by-step guide to deploy your FastAPI backend to Render.

---

## 📋 Pre-Deployment Checklist

Before starting, make sure you have:

- [x] GitHub account with your code pushed
- [x] Render account (sign up at [render.com](https://render.com))
- [x] Supabase account and project (get URL and Key)
- [x] Mailtrap account (get SMTP credentials)
- [x] Google OAuth credentials (Client ID and Secret)
- [x] Frontend deployed (or at least know the URL)

---

## 🎯 Step-by-Step Deployment

### Step 1: Prepare Your GitHub Repository

1. **Make sure all changes are committed:**
   ```bash
   git add .
   git commit -m "Ready for deployment"
   git push origin main
   ```

2. **Verify these files exist:**
   - ✅ `render.yaml` (just created!)
   - ✅ `requirements.txt`
   - ✅ `app/main.py`
   - ✅ `alembic/` folder

---

### Step 2: Sign Up / Login to Render

1. Go to [https://render.com](https://render.com)
2. Sign up using your **GitHub account** (easiest)
3. Authorize Render to access your repositories

---

### Step 3: Create New Blueprint

1. **Click** the **"New +"** button (top right)
2. Select **"Blueprint"**
3. **Connect your GitHub repository:**
   - Search for: `fypilot_backend`
   - Click **"Connect"**
4. Render will auto-detect `render.yaml`
5. **Review the blueprint:**
   - You should see: `fypilot-backend` (Web Service)
   - You should see: `fypilot-db` (PostgreSQL Database)

---

### Step 4: Configure Environment Variables

⚠️ **IMPORTANT:** Before clicking "Apply", you need to add the missing environment variables that are marked `sync: false` in `render.yaml`.

1. **Click on the Blueprint** (don't click Apply yet!)
2. **Find the Web Service** (`fypilot-backend`)
3. **Click "Environment Variables"**
4. **Add these MANUALLY:**

#### Required Environment Variables:

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-public-key

# Mailtrap SMTP Credentials
MAILTRAP_SMTP_USER=your_mailtrap_username
MAILTRAP_SMTP_PASS=your_mailtrap_password

# Google OAuth Credentials
GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Frontend URL (UPDATE THIS!)
FRONTEND_APP_URL=https://your-frontend-app.vercel.app
```

#### Optional (If using GitHub OAuth):

```bash
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
```

5. **Update the OAuth Redirect Origin** (we'll do this after deployment)

---

### Step 5: Deploy!

1. **Click "Apply"** button
2. **Wait 5-10 minutes** for:
   - ✅ Database creation
   - ✅ Web service build
   - ✅ Application start

3. **Monitor the deployment:**
   - Click on `fypilot-backend` service
   - Watch the **Logs** tab
   - Look for: `Application startup complete`

---

### Step 6: Get Your API URL

1. **Go to your web service dashboard**
2. **Copy your URL:** `https://fypilot-backend-XXXX.onrender.com`
3. **Save this URL** - you'll need it!

---

### Step 7: Run Database Migrations

Your database is empty! You need to run Alembic migrations:

**Option A: Using Render Shell (Recommended)**

1. Go to your web service → **"Shell"** tab
2. Click **"Launch Shell"**
3. Run:
   ```bash
   alembic upgrade head
   ```
4. Wait for migrations to complete
5. Type `exit` to close shell

**Option B: Using One-time Job**

1. Go to Dashboard → **"New +"** → **"Job"**
2. **Name:** `run-migrations`
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `alembic upgrade head`
5. Click **"Create Job"**

---

### Step 8: Update OAuth Redirect Origin

Now that you have your Render URL, update the environment variable:

1. **Go to:** Web Service → **Environment** tab
2. **Find:** `OAUTH_REDIRECT_ORIGIN`
3. **Set to:** `https://fypilot-backend-XXXX.onrender.com` (your actual URL)
4. **Save Changes**
5. Service will auto-redeploy

---

### Step 9: Configure OAuth Providers

#### Google OAuth Setup:

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Select your project
3. Go to **APIs & Services** → **Credentials**
4. Edit your **OAuth 2.0 Client**
5. **Add Authorized Redirect URIs:**
   ```
   https://fypilot-backend-XXXX.onrender.com/auth/oauth/google/callback
   ```
6. **Save**

#### GitHub OAuth Setup (Optional):

1. Go to [GitHub Settings](https://github.com/settings/developers)
2. Click **OAuth Apps** → Your App
3. **Update Authorization Callback URL:**
   ```
   https://fypilot-backend-XXXX.onrender.com/auth/oauth/github/callback
   ```
4. **Save**

---

### Step 10: Test Your Deployment

1. **Health Check:**
   ```
   https://fypilot-backend-XXXX.onrender.com/api/health
   ```
   Expected: `{"status": "healthy"}`

2. **API Documentation:**
   ```
   https://fypilot-backend-XXXX.onrender.com/docs
   ```
   Should show Swagger UI

3. **Test Signup:**
   - Go to Swagger
   - Try `POST /auth/signup`
   - Create a test user

4. **Test Login:**
   - Try `POST /auth/login`
   - Verify you get a token

---

## 🔄 Next Steps & Best Practices

### 1. Update Your Frontend

Update your frontend environment variables:

```bash
# .env.production or .env
NEXT_PUBLIC_API_URL=https://fypilot-backend-XXXX.onrender.com
```

### 2. Set Up Custom Domain (Optional)

1. Go to Service → **Settings** → **Custom Domain**
2. Add your domain: `api.yourdomain.com`
3. Update DNS records as instructed
4. Update all OAuth redirect URLs

### 3. Enable Auto-Deploy

Already enabled! Every time you push to `main` branch, Render auto-deploys.

### 4. Monitor Your Application

- **Logs:** Dashboard → Your Service → Logs
- **Metrics:** Dashboard → Your Service → Metrics
- **Alerts:** Set up in Settings → Notifications

### 5. Database Backups

⚠️ Free tier has limited backups!

- Manual backup: `pg_dump` from Shell
- Automated: Upgrade to Starter plan ($7/month)

### 6. Upgrade for Production

Free tier limitations:
- ⚠️ Spins down after 15 min of inactivity (slow first request)
- ⚠️ Limited resources
- ⚠️ No guaranteed uptime

**For Production, upgrade to:**
- **Web Service:** Starter ($7/month) or Standard ($25/month)
- **Database:** Starter ($7/month) for backups and better performance

---

## 🐛 Troubleshooting

### Issue: Service Won't Start

**Check Logs:**
1. Go to Logs tab
2. Look for error messages
3. Common issues:
   - Missing environment variables
   - Database connection failed
   - Port binding error

**Solution:**
- Verify all environment variables are set
- Check DATABASE_URL is correct
- Ensure using `--port $PORT` in start command

### Issue: Database Connection Error

**Error:** `connection refused` or `connection timeout`

**Solution:**
1. Use the **External Connection String** (not Internal)
2. Verify database is in same region as web service
3. Check database is "Available" status

### Issue: OAuth Callback Error

**Error:** `redirect_uri_mismatch`

**Solution:**
1. Update OAuth provider callback URLs
2. Use exact URL from Render (including https://)
3. No trailing slashes

### Issue: CORS Error from Frontend

**Error:** `Access-Control-Allow-Origin`

**Solution:**
Update `app/main.py`:
```python
origins = [
    "https://your-frontend.vercel.app",  # Add your actual frontend URL
]
```
Redeploy!

### Issue: Slow First Request

**Cause:** Free tier spins down after 15 minutes

**Solution:**
- Upgrade to paid plan for always-on service
- Or use a cron job to ping your API every 10 minutes

---

## 📊 Monitoring & Maintenance

### Health Checks

Render automatically checks `/api/health` endpoint every 30 seconds.

### View Logs

```bash
# In Render Dashboard
Service → Logs → View Live Logs
```

### Database Migrations (Future Updates)

When you update your models:

1. Create migration locally:
   ```bash
   alembic revision --autogenerate -m "description"
   ```

2. Push to GitHub:
   ```bash
   git add .
   git commit -m "Add migration"
   git push
   ```

3. After auto-deploy, run migration:
   - Go to Shell
   - Run: `alembic upgrade head`

---

## 🎉 Success Checklist

- [ ] Database created and migrations run
- [ ] Web service deployed and healthy
- [ ] Environment variables configured
- [ ] OAuth redirect URLs updated
- [ ] Test endpoints working (`/api/health`, `/docs`)
- [ ] Test signup/login working
- [ ] Frontend connected to production API
- [ ] CORS configured correctly

---

## 💰 Cost Breakdown

### Free Tier (Current):
- Web Service: **Free** (with limitations)
- PostgreSQL: **Free** (with limitations)
- **Total: $0/month**

### Production Tier (Recommended):
- Web Service Starter: **$7/month**
- PostgreSQL Starter: **$7/month**
- **Total: $14/month**

### Enterprise Tier:
- Web Service Standard: **$25/month**
- PostgreSQL Standard: **$20/month**
- **Total: $45/month**

---

## 📞 Support

- **Render Docs:** [render.com/docs](https://render.com/docs)
- **Render Community:** [community.render.com](https://community.render.com)
- **FastAPI Docs:** [fastapi.tiangolo.com](https://fastapi.tiangolo.com)

---

## 🔐 Security Reminders

- ✅ Never commit `.env` file to GitHub
- ✅ Use Render's environment variables for secrets
- ✅ Enable HTTPS only (Render does this automatically)
- ✅ Regularly rotate JWT_SECRET and SESSION_SECRET
- ✅ Keep dependencies updated (`pip list --outdated`)
- ✅ Enable Render's security headers (already in config)

---

**Your backend is now live! 🎉**

API URL: `https://fypilot-backend-XXXX.onrender.com`
Docs: `https://fypilot-backend-XXXX.onrender.com/docs`


