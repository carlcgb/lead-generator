# Troubleshooting Guide

> **Tags:** `#troubleshooting` `#help` `#errors` `#playwright` `#api-keys`

## Common Issues and Solutions

### 1. Playwright NotImplementedError

**Error:**
```
NotImplementedError
File "...\asyncio\base_events.py", line 539, in _make_subprocess_transport
    raise NotImplementedError
```

**Cause:**
This is a known issue with Playwright on Windows, especially with Python 3.13+. Playwright's async subprocess execution may not work in certain environments.

**Solutions:**

1. **Fallback to Requests (Automatic)**
   - The app will automatically fall back to the `requests` library when Playwright fails
   - This works for most sites, but may not work for JavaScript-heavy sites

2. **Reinstall Playwright**
   ```bash
   pip uninstall playwright
   pip install playwright
   playwright install chromium
   ```

3. **Use Python 3.11 or 3.12**
   - Python 3.13+ has known compatibility issues with Playwright
   - Consider using Python 3.11 or 3.12 for better compatibility

4. **Use Website Checker Tab**
   - For JavaScript-heavy sites, use the "Website Checker" tab in "Discover Leads"
   - This uses a different approach that may work better

**What the app does:**
- Automatically detects Playwright failures
- Falls back to `requests` library
- Shows a warning message explaining the issue
- Continues working with limited functionality

---

### 2. Google Places API Billing Error

**Error:**
```
REQUEST_DENIED (You must enable Billing on the Google Cloud Project)
```

**Cause:**
Google Places API requires billing to be enabled on your Google Cloud project, even for free tier usage.

**Solution:**

1. **Enable Billing:**
   - Go to: https://console.cloud.google.com/project/_/billing/enable
   - Select your Google Cloud project
   - Add a payment method (credit card required)
   - **Note:** Google offers $200 free credit per month for Maps API
   - Most small projects stay within the free tier

2. **Verify API is Enabled:**
   - Go to: https://console.cloud.google.com/apis/library
   - Search for "Places API"
   - Ensure both "Places API" and "Places API (New)" are enabled

3. **Check API Key:**
   - Go to: https://console.cloud.google.com/apis/credentials
   - Verify your API key is active
   - Check that it has the correct API restrictions

**Free Tier Limits:**
- $200 free credit per month
- Places API: $17 per 1000 requests
- You can make ~11,700 requests per month for free
- Most lead discovery tasks stay well within this limit

---

### 3. 403 Forbidden Errors

**Error:**
```
403 Client Error: Forbidden
```

**Cause:**
Some websites block automated access or require JavaScript rendering.

**Solutions:**

1. **Playwright Fallback (if available)**
   - The app automatically tries Playwright when requests fail
   - If Playwright is not available, you'll see a warning

2. **Use Website Checker Tab**
   - Manually check websites using the "Website Checker" tab
   - This uses a different approach that may bypass some blocks

3. **Check robots.txt**
   - Ensure you're only scraping sites that allow it
   - Respect rate limits (the app includes delays)

---

### 4. Import Errors

**Error:**
```
ImportError: No module named 'googlemaps'
```

**Solution:**
```bash
pip install googlemaps
```

**Error:**
```
ImportError: No module named 'playwright'
```

**Solution:**
```bash
pip install playwright
playwright install chromium
```

---

### 5. Database Errors

**Error:**
```
sqlite3.OperationalError: no such column
```

**Solution:**
- The app automatically handles database migrations
- If you see this error, delete `leads.db` and restart the app
- The database will be recreated with the correct schema

---

## Getting Help

If you encounter other issues:

1. Check the error message in the Streamlit app
2. Check the terminal/console output for detailed errors
3. Review this troubleshooting guide
4. Check the `LEAD_DISCOVERY_README.md` for feature-specific help

## Performance Tips

1. **Rate Limiting:**
   - The app includes automatic rate limiting
   - Don't disable delays - they prevent getting blocked

2. **Batch Processing:**
   - Process leads in smaller batches
   - Use filters to focus on high-value leads

3. **API Quotas:**
   - Monitor your Google Places API usage
   - Set up billing alerts in Google Cloud Console

