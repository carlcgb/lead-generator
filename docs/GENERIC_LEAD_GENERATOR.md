# Generic Lead Generator - Configuration Guide

> **Tags:** `#configuration` `#getting-started` `#setup` `#target-indicators`

## Overview

The lead generator has been refactored to be **completely generic** - it can search for any target software or indicators you configure. No more hardcoded Avionté references!

## Key Features

### ✅ Configurable Target Indicators
- Add any software/indicator to search for (Avionté, Mindscope, etc.)
- Configure subdomain patterns (e.g., `*.myavionte.com`, `*.mindscope.com`)
- Configure keywords to search for
- Configure link patterns to detect

### ✅ Multiple Detection Methods
1. **Subdomain Checking** - Checks if `companyName.targetdomain.com` exists
2. **Link Detection** - Scans websites for links to target software
3. **Keyword Search** - Searches page content for keywords

### ✅ Generic Discovery
- All discovery methods work with any configured indicators
- No hardcoded software names
- Easy to add new targets

## Configuration

### Using the UI

1. Navigate to **"⚙️ Configure Targets"** in the sidebar
2. View/edit existing indicators
3. Add new indicators with:
   - **Name**: e.g., "Avionté", "Mindscope"
   - **Subdomain Pattern**: e.g., `*.myavionte.com`
   - **Keywords**: One per line (e.g., `avionte`, `avionté`)
   - **Link Patterns**: One per line (e.g., `avionte.com`, `myavionte.com`)

### Using Configuration File

Create or edit `indicators.json`:

```json
[
  {
    "name": "Avionté",
    "subdomain_pattern": "*.myavionte.com",
    "keywords": ["avionte", "avionté", "myavionte"],
    "link_patterns": ["avionte.com", "myavionte.com", "avionté.com"]
  },
  {
    "name": "Mindscope",
    "subdomain_pattern": "*.mindscope.com",
    "keywords": ["mindscope"],
    "link_patterns": ["mindscope.com"]
  }
]
```

## Default Configuration

The system comes with two default indicators:
- **Avionté** - `*.myavionte.com` subdomain pattern
- **Mindscope** - `*.mindscope.com` subdomain pattern

## How It Works

### 1. Subdomain Checking
For each company found, the system checks if subdomains exist:
- `companyName.myavionte.com`
- `companyName.mindscope.com`
- And variations (lowercase, no spaces, etc.)

### 2. Link Detection
Scans company websites for links containing:
- `avionte.com`
- `mindscope.com`
- Any configured link patterns

### 3. Keyword Search
Searches page content for configured keywords (optional, can be disabled)

## Usage Examples

### Example 1: Search for Avionté Users
1. Configure Avionté indicator (already configured by default)
2. Use Google Places discovery
3. System automatically checks all companies for Avionté subdomains
4. Only companies with confirmed subdomains are saved as leads

### Example 2: Search for Mindscope Users
1. Configure Mindscope indicator (already configured by default)
2. Use any discovery method
3. System checks for `*.mindscope.com` subdomains
4. Companies with Mindscope links or subdomains are identified

### Example 3: Add New Software
1. Go to "⚙️ Configure Targets"
2. Click "Add New Indicator"
3. Enter:
   - Name: "NewSoftware"
   - Subdomain: `*.newsoftware.com`
   - Keywords: `newsoftware`, `new-software`
   - Links: `newsoftware.com`
4. Save and use in discovery

## Discovery Methods

All discovery methods now work generically:

- **Google Places** - Checks all found companies for configured indicators
- **Job Boards** - Checks companies posting jobs
- **Reddit** - Checks companies mentioned in posts
- **News Articles** - Checks companies in articles
- **Directories** - Checks all directory listings
- **Website Checker** - Direct checking of specific websites

## Lead Data Structure

### CompanyLead
```python
CompanyLead(
    company_name="ABC Staffing",
    website="https://abcstaffing.com",
    target_indicators={
        "Avionté": True,
        "Mindscope": False
    },
    indicator_evidence={
        "Avionté": "https://abcstaffing.myavionte.com"
    }
)
```

## Benefits

### ✅ Flexibility
- Search for any software/indicator
- Easy to add new targets
- No code changes needed

### ✅ Accuracy
- Subdomain checking is 100% accurate
- Multiple detection methods
- Configurable verification

### ✅ Scalability
- Add unlimited indicators
- Each company checked against all indicators
- Results show which indicators were found

## Migration Notes

### Backward Compatibility
- Old functions still work (`check_avionte_subdomain`, `check_website_for_avionte`)
- They now use the generic system internally
- No breaking changes to existing code

### Database
- Existing leads are not affected
- New leads use generic indicator system
- Can filter by indicator in UI

## Best Practices

1. **Start with Subdomain Patterns** - Most accurate method
2. **Add Link Patterns** - Good for detecting website mentions
3. **Use Keywords Sparingly** - Can have false positives
4. **Test Indicators** - Verify they work before bulk discovery
5. **Update Regularly** - Keep indicators current

## Troubleshooting

### Indicator Not Found
- Check subdomain pattern is correct
- Verify company domain format
- Try different company name variations

### Too Many False Positives
- Use subdomain checking (most accurate)
- Avoid keyword-only detection
- Refine link patterns

### No Results
- Verify indicator configuration
- Check company websites are accessible
- Try different discovery methods

## Next Steps

1. Configure your target indicators
2. Test with a few companies
3. Run discovery across all sources
4. Review and filter results
5. Export to CRM

