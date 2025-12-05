# Streamlit Community Cloud Deployment Guide

## Prerequisites

1. GitHub account
2. Streamlit Community Cloud account (free)
3. Repository pushed to GitHub

## Deployment Steps

### 1. Prepare Your Repository

Ensure your repository has:
- ✅ `streamlit_app.py` (main app file)
- ✅ `requirements.txt` (dependencies)
- ✅ `.streamlit/config.toml` (optional, for theme)
- ✅ All necessary Python modules

### 2. Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click "New app"
3. Connect your GitHub account if not already connected
4. Select your repository: `carlcgb/lead-generator`
5. Set main file path: `streamlit_app.py`
6. Click "Deploy"

### 3. Configure Secrets (API Keys)

For Google Places API and other secrets:

1. In Streamlit Cloud, go to your app settings
2. Click "Secrets" in the sidebar
3. Add your secrets in TOML format:

```toml
GOOGLE_PLACES_API_KEY = "your-api-key-here"
```

**Note:** The app will automatically use Streamlit secrets if available, falling back to environment variables.

### 4. Database Storage

The app uses SQLite (`leads.db`) which is stored in the app's file system. 
**Important:** Data persists between deployments but may be reset if the app is redeployed.

For persistent storage, consider:
- Using an external database (PostgreSQL, MySQL)
- Exporting data regularly
- Using Streamlit's built-in session state for temporary storage

### 5. Configuration Files

The app will automatically create `indicators.json` in the app directory when you configure targets via the UI.

## Environment Variables

The app supports both:
- **Streamlit Secrets** (recommended for Cloud): Set in Streamlit Cloud dashboard
- **Environment Variables**: Set in `.env` file (for local development)

## Troubleshooting

### App Won't Deploy

- Check that `streamlit_app.py` exists in the root directory
- Verify `requirements.txt` is correct
- Check build logs for errors

### API Keys Not Working

- Ensure secrets are set in Streamlit Cloud dashboard
- Check secret names match exactly (case-sensitive)
- Verify API keys are valid

### Database Issues

- SQLite works in Streamlit Cloud but data may reset
- For production, consider external database
- Export data regularly for backup

### Playwright Issues

- Playwright may not work in Streamlit Cloud (limited support)
- The app will automatically fall back to `requests` library
- Some sites may not work without Playwright

## Post-Deployment

1. **Test the app** - Verify all features work
2. **Configure targets** - Set up your target indicators
3. **Set API keys** - Add Google Places API key if needed
4. **Share the link** - Your app will be available at `https://your-app-name.streamlit.app`

## Custom Domain (Optional)

Streamlit Cloud supports custom domains:
1. Go to app settings
2. Click "Custom domain"
3. Follow the instructions

## Monitoring

- View app logs in Streamlit Cloud dashboard
- Monitor usage and errors
- Check API rate limits if using Google Places

## Best Practices

1. **Keep secrets secure** - Never commit API keys to git
2. **Test locally first** - Ensure app works before deploying
3. **Monitor usage** - Watch for API rate limits
4. **Backup data** - Export leads regularly
5. **Update dependencies** - Keep requirements.txt updated

