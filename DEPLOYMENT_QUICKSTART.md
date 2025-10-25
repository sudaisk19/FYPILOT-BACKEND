# ⚡ Quick Start - Deploy to Render in 15 Minutes

The fastest way to get your FYPilot backend live!

---

## 🎯 Prerequisites (5 minutes)

1. **Gather credentials** - Open `ENV_VARIABLES_CHECKLIST.md` and collect all values
2. **Push code to GitHub** - Make sure your latest code is pushed
3. **Sign up for Render** - Create account at [render.com](https://render.com)

---

## 🚀 Deploy Now (10 minutes)

### Step 1: Create Blueprint (2 min)

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **"New +"** → **"Blueprint"**
3. Connect **GitHub repo**: `fypilot_backend`
4. Render finds `render.yaml` automatically

### Step 2: Add Secrets (3 min)

Click on the blueprint, then add these environment variables:

```bash
SUPABASE_URL=your_value_here
SUPABASE_KEY=your_value_here
MAILTRAP_SMTP_USER=your_value_here
MAILTRAP_SMTP_PASS=your_value_here
GOOGLE_CLIENT_ID=your_value_here
GOOGLE_CLIENT_SECRET=your_value_here
FRONTEND_APP_URL=your_value_here
```

### Step 3: Deploy (5 min)

1. Click **"Apply"**
2. Wait for build (watch the logs)
3. Copy your URL: `https://fypilot-backend-XXXX.onrender.com`

### Step 4: Run Migrations (1 min)

1. Go to your service → **"Shell"** tab
2. Run: `alembic upgrade head`
3. Done! ✅

---

## ✅ Test It

Visit: `https://fypilot-backend-XXXX.onrender.com/docs`

Try:
- ✅ Signup a test user
- ✅ Login with credentials
- ✅ Check `/api/health`

---

## 🔄 Update OAuth Redirects

### Google OAuth:
1. [Google Console](https://console.cloud.google.com) → Credentials
2. Add redirect URI: `https://your-render-url.onrender.com/auth/oauth/google/callback`

### GitHub OAuth:
1. [GitHub OAuth Apps](https://github.com/settings/developers)
2. Update callback URL: `https://your-render-url.onrender.com/auth/oauth/github/callback`

---

## 📱 Update Frontend

```bash
# In your frontend .env
NEXT_PUBLIC_API_URL=https://fypilot-backend-XXXX.onrender.com
```

---

## 🎉 Done!

Your API is live at: `https://fypilot-backend-XXXX.onrender.com`

**Need more details?** See `DEPLOYMENT_GUIDE.md` for complete instructions.

---

## 🆘 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| Build fails | Check logs → verify `requirements.txt` |
| 500 errors | Check environment variables are set |
| Database error | Run `alembic upgrade head` in Shell |
| OAuth fails | Update redirect URIs in OAuth providers |
| CORS error | Add frontend URL to CORS in `app/main.py` |

---

## 📊 What's Next?

- [ ] Test all endpoints in Swagger
- [ ] Connect frontend to production API  
- [ ] Set up monitoring/alerts
- [ ] Consider upgrading to paid plan for production
- [ ] Set up custom domain (optional)

---

**Questions?** Check `DEPLOYMENT_GUIDE.md` for detailed help!


