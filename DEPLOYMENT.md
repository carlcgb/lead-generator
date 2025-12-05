# Streamlit Community Cloud Deployment Guide

## Quick Deploy

1. **Go to [share.streamlit.io](https://share.streamlit.io)**
2. **Sign in** with your GitHub account
3. **Click "New app"**
4. **Select repository**: `carlcgb/lead-generator`
5. **Set main file path**: `streamlit_app.py`
6. **Click "Deploy"**

That's it! Your app will be live in minutes.

## Configure Secrets (Optional)

**Important:** Never commit API keys to the repository. Use Streamlit Cloud secrets instead.

If you want to use Google Places API:

1. In Streamlit Cloud, go to your app
2. Click **"⚙️ Settings"** → **"Secrets"**
3. Add your API key in TOML format:

```toml
GOOGLE_PLACES_API_KEY = "your-api-key-here"
```

**How it works:**
- Streamlit Cloud: Uses `st.secrets` (from GitHub secrets)
- Local development: Uses `.env` file (gitignored, never committed)
- The app automatically detects which to use

## What Gets Deployed

- ✅ Main app: `streamlit_app.py`
- ✅ All Python modules (lead_config.py, lead_discovery.py, etc.)
- ✅ Dependencies from `requirements.txt`
- ✅ Configuration files

## Database Storage

The app uses SQLite (`leads.db`) which is stored in the app's file system.
**Note:** Data persists between app restarts but may be reset if you redeploy.

## Troubleshooting

### App Won't Deploy
- Ensure `streamlit_app.py` is in the root directory
- Check `requirements.txt` is correct
- View build logs for errors

### Playwright Warning
- This is normal - Playwright doesn't work in Streamlit Cloud
- The app automatically uses `requests` library instead
- Some sites may not work without Playwright (that's okay)

### API Keys
- Add secrets in Streamlit Cloud dashboard (Settings → Secrets)
- Or enter them manually in the app UI

## Your App URL

After deployment, your app will be available at:
`https://lead-generator.streamlit.app`

(Or a custom URL if you set one up)
