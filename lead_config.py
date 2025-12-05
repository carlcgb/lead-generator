"""
Lead Generator Configuration - Generic target software/indicator configuration
"""
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict
import json
import os

@dataclass
class TargetIndicator:
    """Configuration for a target software/indicator to search for"""
    name: str  # e.g., "Avionté", "Mindscope"
    subdomain_pattern: Optional[str] = None  # e.g., "*.myavionte.com" or "*.mindscope.com"
    keywords: List[str] = None  # Keywords to search for in content
    link_patterns: List[str] = None  # URL patterns to look for (e.g., "avionte.com", "mindscope.com")
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []
        if self.link_patterns is None:
            self.link_patterns = []

# Default configuration - can be overridden via UI or config file
DEFAULT_INDICATORS = [
    TargetIndicator(
        name="Avionté",
        subdomain_pattern="*.myavionte.com",
        keywords=["avionte", "avionté", "myavionte"],
        link_patterns=["avionte.com", "myavionte.com", "avionté.com"]
    ),
    TargetIndicator(
        name="Mindscope",
        subdomain_pattern="*.mindscope.com",
        keywords=["mindscope"],
        link_patterns=["mindscope.com"]
    ),
    TargetIndicator(
        name="Bullhorn",
        subdomain_pattern="*.bullhorn.com",
        keywords=["bullhorn"],
        link_patterns=["bullhorn.com"]
    )
]

def load_indicators_from_file(filepath: str = None) -> List[TargetIndicator]:
    """Load indicators from JSON file"""
    if filepath is None:
        # Use relative path for Streamlit Cloud compatibility
        filepath = os.path.join(os.path.dirname(__file__), "indicators.json")
    
    if not os.path.exists(filepath):
        return DEFAULT_INDICATORS
    
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            return [TargetIndicator(**item) for item in data]
    except Exception as e:
        print(f"Error loading indicators: {e}")
        return DEFAULT_INDICATORS

def save_indicators_to_file(indicators: List[TargetIndicator], filepath: str = None):
    """Save indicators to JSON file"""
    if filepath is None:
        # Use relative path for Streamlit Cloud compatibility
        filepath = os.path.join(os.path.dirname(__file__), "indicators.json")
    
    try:
        data = [asdict(indicator) for indicator in indicators]
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving indicators: {e}")

def get_indicator_by_name(name: str, indicators: List[TargetIndicator] = None) -> Optional[TargetIndicator]:
    """Get indicator by name"""
    if indicators is None:
        indicators = DEFAULT_INDICATORS
    for indicator in indicators:
        if indicator.name.lower() == name.lower():
            return indicator
    return None

def check_subdomain_for_indicator(company_domain: str, indicator: TargetIndicator, timeout: int = 5) -> tuple[bool, Optional[str]]:
    """
    Check if a company uses the target software by verifying subdomain
    
    Args:
        company_domain: Company domain (e.g., "primlogix.com")
        indicator: TargetIndicator configuration
        timeout: Request timeout
    
    Returns:
        (found, subdomain_url)
    """
    if not indicator.subdomain_pattern or not company_domain:
        return False, None
    
    # Extract base domain and company name
    domain = company_domain.replace('www.', '').replace('https://', '').replace('http://', '').split('/')[0]
    company_name = domain.split('.')[0]
    
    # Extract subdomain pattern (e.g., "*.myavionte.com" -> "myavionte.com")
    subdomain_base = indicator.subdomain_pattern.replace('*.', '').replace('*', '')
    
    # Try multiple subdomain patterns
    subdomain_patterns = [
        f"{company_name}.{subdomain_base}",
        f"{company_name.lower()}.{subdomain_base}",
        f"{company_name.replace(' ', '').lower()}.{subdomain_base}",
        f"{company_name.replace('-', '').lower()}.{subdomain_base}",
        f"{company_name.replace('_', '').lower()}.{subdomain_base}",
    ]
    
    # Also try variations
    company_variations = [
        company_name,
        company_name.lower(),
        company_name.replace(' ', '').lower(),
        company_name.replace('-', '').lower(),
        company_name.replace('_', '').lower(),
        company_name.split()[0].lower() if ' ' in company_name else company_name.lower(),
    ]
    
    for variation in set(company_variations):  # Remove duplicates
        if variation:
            subdomain_patterns.append(f"{variation}.{subdomain_base}")
    
    # Remove duplicates
    subdomain_patterns = list(set(subdomain_patterns))
    
    import requests
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    for subdomain in subdomain_patterns:
        try:
            url = f"https://{subdomain}"
            # Use HEAD request first (faster, less bandwidth)
            response = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                return True, url
            # Also try GET if HEAD doesn't work
            response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                return True, url
        except requests.exceptions.RequestException:
            continue
        except Exception:
            continue
    
    return False, None

def check_links_for_indicator(url: str, indicator: TargetIndicator, timeout: int = 10) -> tuple[bool, Optional[str]]:
    """
    Check if a website contains links to the target software
    
    Args:
        url: Website URL to check
        indicator: TargetIndicator configuration
        timeout: Request timeout
    
    Returns:
        (found, evidence)
    """
    if not indicator.link_patterns:
        return False, None
    
    # Auto-add https:// if protocol is missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        response = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if response.status_code != 200:
            return False, None
        
        html = response.text.lower()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check all links for target patterns
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').lower()
            for pattern in indicator.link_patterns:
                if pattern.lower() in href:
                    # Extract context
                    link_text = link.get_text(strip=True)
                    return True, f"Link found: {href} ({link_text[:50]})"
        
        # Also check in page source
        for pattern in indicator.link_patterns:
            if pattern.lower() in html:
                return True, f"Reference found in page source: {pattern}"
        
        return False, None
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

def check_keywords_for_indicator(text: str, indicator: TargetIndicator) -> tuple[bool, Optional[str]]:
    """
    Check if text contains keywords for the target software
    
    Args:
        text: Text to check
        indicator: TargetIndicator configuration
    
    Returns:
        (found, evidence)
    """
    if not indicator.keywords:
        return False, None
    
    text_lower = text.lower()
    for keyword in indicator.keywords:
        if keyword.lower() in text_lower:
            # Extract context around keyword
            idx = text_lower.find(keyword.lower())
            start = max(0, idx - 50)
            end = min(len(text), idx + len(keyword) + 50)
            evidence = text[start:end].strip()
            return True, evidence
    
    return False, None

