# Generic Lead Generator

> **Tags:** `#lead-generation` `#web-scraping` `#streamlit` `#python` `#sales-tools`

A powerful, configurable lead generation tool that can discover companies using any target software or indicators you specify.

## Features

- **🔍 Multi-Source Discovery**: Find leads from Google Places, job boards, Reddit, news articles, directories, and more
- **⚙️ Configurable Targets**: Search for any software/indicator (Avionté, Mindscope, or custom)
- **🔗 Subdomain Verification**: Automatically check for subdomain patterns (e.g., `*.myavionte.com`)
- **📊 Lead Management**: Store, score, and track leads with analytics dashboard
- **🌐 Web Interface**: User-friendly Streamlit interface
- **💻 CLI Support**: Command-line interface for automation

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Configuration

1. **Configure Target Indicators**:
   - Launch the app: `streamlit run streamlit_app.py`
   - Navigate to "⚙️ Configure Targets" in the sidebar
   - Add/edit indicators (name, subdomain pattern, keywords, link patterns)

2. **Set Environment Variables** (optional):
   ```bash
   cp env_template.txt .env
   # Edit .env and add your Google Places API key
   ```

### Usage

#### Web Interface
```bash
streamlit run streamlit_app.py
```

#### Command Line
```bash
# Scrape review pages
python cli.py scrape --urls "https://g2.com/products/software/reviews"

# Check websites
python cli.py check --urls "company1.com" "company2.com"
```

## Configuration

### Default Indicators

The app comes with two default indicators:
- **Avionté**: `*.myavionte.com` subdomain pattern
- **Mindscope**: `*.mindscope.com` subdomain pattern

### Adding Custom Indicators

Via UI:
1. Go to "⚙️ Configure Targets"
2. Click "Add New Indicator"
3. Fill in the form and save

Via JSON:
Edit `indicators.json`:
```json
[
  {
    "name": "YourSoftware",
    "subdomain_pattern": "*.yoursoftware.com",
    "keywords": ["yoursoftware", "your-software"],
    "link_patterns": ["yoursoftware.com"]
  }
]
```

## Discovery Methods

- **📍 Google Places**: Search for businesses and check their websites
- **💼 Job Boards**: Find companies posting jobs mentioning target software
- **📱 Reddit**: Search Reddit posts for company mentions
- **📰 News Articles**: Find companies in news articles
- **📞 Directories**: Search industry directories (Yellow Pages, etc.)
- **🔗 Subdomain Checker**: Direct verification of subdomain patterns
- **🔍 Website Checker**: Check individual websites for indicators

## Lead Detection Methods

1. **Subdomain Checking** (Most Accurate)
   - Checks if `companyName.targetdomain.com` exists
   - 100% accurate confirmation

2. **Link Detection**
   - Scans websites for links to target software
   - Good for detecting mentions

3. **Keyword Search** (Optional)
   - Searches page content for keywords
   - Can have false positives

## Project Structure

```
.
├── streamlit_app.py          # Main Streamlit application
├── lead_config.py            # Configuration system for target indicators
├── lead_discovery.py         # Core discovery functions
├── enhanced_lead_discovery.py # Advanced discovery methods
├── cli.py                    # Command-line interface
├── requirements.txt          # Python dependencies
├── env_template.txt          # Environment variables template
├── docs/                     # Documentation directory
│   ├── README.md             # Documentation index
│   ├── GENERIC_LEAD_GENERATOR.md
│   ├── LEAD_DISCOVERY_README.md
│   ├── CLI_README.md
│   ├── ENHANCED_FEATURES.md
│   ├── SUBDOMAIN_CHECKING.md
│   ├── TROUBLESHOOTING.md
│   └── context.md            # Legacy context (historical)
└── .gitignore                # Git ignore rules
```

## Requirements

- Python 3.8+
- See `requirements.txt` for dependencies

## Documentation

All documentation is organized in the [`docs/`](docs/) directory:

- **[📖 Documentation Index](docs/README.md)** - Complete documentation index
- **[⚙️ Configuration Guide](docs/GENERIC_LEAD_GENERATOR.md)** - Configure target indicators
- **[🔍 Lead Discovery](docs/LEAD_DISCOVERY_README.md)** - Discovery features
- **[🚀 Enhanced Features](docs/ENHANCED_FEATURES.md)** - Advanced discovery methods
- **[🔗 Subdomain Checking](docs/SUBDOMAIN_CHECKING.md)** - Verification methods
- **[💻 CLI Guide](docs/CLI_README.md)** - Command-line usage
- **[🔧 Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions

## Deployment

### Streamlit Community Cloud (Free)

**Quick Deploy:**
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app"
4. Select repository: `carlcgb/lead-generator`
5. Main file: `streamlit_app.py`
6. Click "Deploy"

**Your app will be live at:** `https://lead-generator.streamlit.app`

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions and troubleshooting.

## License

MIT License

## Contributing

Contributions welcome! Please ensure code is clean and well-documented.

