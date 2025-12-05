# Lead Discovery Features

This module adds multi-source lead discovery capabilities to find potential Avionté users beyond review sites.

## Features

### 1. Google Places API Integration
- Search for staffing agencies using Google Places API
- Automatically check company websites for Avionté mentions
- Extract contact information (email, phone, address)

### 2. Job Board Scraper
- Search Indeed job postings for Avionté mentions
- Find companies posting jobs that require Avionté experience
- Identify active Avionté users

### 3. Website Checker
- Check individual company websites for Avionté mentions
- Extract contact information
- Verify Avionté usage

## Setup

### 1. Install Dependencies
```bash
pip install googlemaps
```

### 2. Get Google Places API Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable "Places API" and "Places API (New)"
4. Create credentials (API Key)
5. Add the API key to your `.env` file:
   ```
   GOOGLE_PLACES_API_KEY=your_api_key_here
   ```

### 3. Usage in Streamlit App

Navigate to **"🌐 Discover Leads"** in the sidebar:

#### Google Places Tab
1. Enter search queries (e.g., "staffing agency", "temporary staffing")
2. Enter location (e.g., "United States", "New York")
3. Enter your Google Places API key
4. Set max results per query
5. Check "Check websites for Avionté mentions" to automatically verify
6. Click "🔍 Discover from Google Places"

#### Job Boards Tab
1. Enter search queries (e.g., "Avionté", "Avionte staffing software")
2. Enter location
3. Set max results
4. Click "🔍 Discover from Job Boards"

#### Website Checker Tab
1. Enter website URLs (one per line)
2. Click "🔍 Check Websites"
3. Review results and save Avionté users as leads

## How It Works

1. **Google Places Discovery**:
   - Searches Google Places for staffing agencies
   - Retrieves company details (name, website, phone, address)
   - Checks company websites for Avionté mentions
   - Creates leads for companies using Avionté

2. **Job Board Discovery**:
   - Searches Indeed for job postings mentioning Avionté
   - Extracts company names from job postings
   - Creates leads for companies actively using Avionté

3. **Website Checker**:
   - Checks individual websites for Avionté mentions
   - Extracts contact information
   - Allows manual verification before saving

## Lead Scoring

Discovered leads are automatically scored:
- Base score for discovery leads
- Higher score if Avionté mention is strong
- Contact information availability increases score

## Rate Limiting

The module includes rate limiting to respect API limits:
- Google Places: 0.1s between requests
- Website checks: 1s between requests
- Job board searches: 2s between queries

## Notes

- Google Places API has usage limits (check your quota)
- Some websites may block automated access
- Job board scraping may be limited by anti-bot measures
- Always verify leads before contacting

## Troubleshooting

**"Lead discovery module not available"**
- Install googlemaps: `pip install googlemaps`

**"No companies found"**
- Try different search queries
- Check your API key is valid
- Verify location format

**"403 Forbidden" errors**
- Website may be blocking automated access
- Try using Playwright for JavaScript-heavy sites

