# Command Line Interface (CLI) Guide

> **Tags:** `#cli` `#command-line` `#automation` `#scripting`

The CLI allows you to run the lead generator from the command line without the Streamlit UI.

## Installation

Make sure all dependencies are installed:
```bash
pip install -r requirements.txt
```

## Usage

### Scrape Review Pages

Scrape review sites for negative Avionté reviews:

```bash
# Single URL
python cli.py scrape --urls "https://g2.com/products/avionte-staffing-and-payroll/reviews"

# Multiple URLs
python cli.py scrape --urls "https://g2.com/products/avionte-staffing-and-payroll/reviews" "https://www.getapp.com/hr-employee-management-software/a/avionte/"

# From file
python cli.py scrape --file urls.txt

# Export to CSV
python cli.py scrape --urls "url1" --export leads.csv

# Don't save to database
python cli.py scrape --urls "url1" --no-save
```

### Check Websites for Avionté

Check individual websites for Avionté mentions:

```bash
# Single website
python cli.py check --urls "primlogix.com"

# Multiple websites
python cli.py check --urls "primlogix.com" "example-staffing.com"

# From file
python cli.py check --file websites.txt
```

## Examples

### Example 1: Scrape G2 Reviews
```bash
python cli.py scrape --urls "https://g2.com/products/avionte-staffing-and-payroll/reviews" --export g2_leads.csv
```

### Example 2: Check Multiple Websites
```bash
python cli.py check --urls "staffing-agency-1.com" "staffing-agency-2.com" "staffing-agency-3.com"
```

### Example 3: Batch Scrape from File
Create `urls.txt`:
```
https://g2.com/products/avionte-staffing-and-payroll/reviews
https://www.getapp.com/hr-employee-management-software/a/avionte/
https://www.trustradius.com/products/avionte/reviews
```

Then run:
```bash
python cli.py scrape --file urls.txt --export all_leads.csv
```

## Output

The CLI provides:
- Progress indicators for each URL
- Summary statistics
- Top leads by score
- Error messages if something fails
- CSV export (if requested)
- Database storage (by default)

## Notes

- URLs can be with or without `https://` (auto-added)
- Capterra URLs are automatically skipped (forbids automation)
- Results are saved to `leads.db` by default
- Use `--no-save` to skip database storage
- Use `--export` to save results to CSV

## Troubleshooting

**"Module not found" errors:**
- Make sure you're in the project directory
- Install dependencies: `pip install -r requirements.txt`

**"Playwright not available" warnings:**
- This is normal on Windows with Python 3.13+
- The CLI will fall back to requests library
- For JavaScript-heavy sites, use the Streamlit UI instead

**"403 Forbidden" errors:**
- Site is blocking automated access
- Try using the Streamlit UI with Playwright
- Or use the website checker for manual verification

