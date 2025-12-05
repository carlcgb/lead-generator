"""
Lead Discovery Module - Multi-source lead generation
Generic lead generator that can search for any target software/indicators
"""
import os
import re
import time
import requests
from typing import List, Optional, Dict
from bs4 import BeautifulSoup
from dataclasses import dataclass
from datetime import datetime
import urllib.parse

# Import configuration
try:
    from lead_config import (
        TargetIndicator, DEFAULT_INDICATORS,
        check_subdomain_for_indicator,
        check_links_for_indicator,
        check_keywords_for_indicator
    )
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    print("Warning: lead_config not available, using defaults")

# Google Places API
try:
    import googlemaps
    GOOGLE_PLACES_AVAILABLE = True
except ImportError:
    GOOGLE_PLACES_AVAILABLE = False

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

@dataclass
class CompanyLead:
    """Represents a potential lead company"""
    company_name: str
    website: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    description: Optional[str] = None
    target_indicators: Dict[str, bool] = None  # e.g., {"Avionté": True, "Mindscope": False}
    indicator_evidence: Dict[str, str] = None  # e.g., {"Avionté": "https://company.myavionte.com"}
    source: str = "unknown"
    scraped_at: str = None
    lead_score: float = 0.0
    
    def __post_init__(self):
        if self.target_indicators is None:
            self.target_indicators = {}
        if self.indicator_evidence is None:
            self.indicator_evidence = {}
    
    def has_any_indicator(self) -> bool:
        """Check if company has any target indicators"""
        return any(self.target_indicators.values())
    
    def get_indicators(self) -> List[str]:
        """Get list of confirmed indicators"""
        return [name for name, found in self.target_indicators.items() if found]

def search_google_places(query: str, location: str = "United States", api_key: Optional[str] = None, max_results: int = 20) -> List[CompanyLead]:
    """
    Search Google Places API for staffing agencies
    
    Args:
        query: Search query (e.g., "staffing agency", "temporary staffing")
        location: Location to search (default: "United States")
        api_key: Google Places API key (from env if not provided)
        max_results: Maximum number of results to return
    
    Returns:
        List of CompanyLead objects
    """
    if not GOOGLE_PLACES_AVAILABLE:
        return []
    
    # Try Streamlit secrets first (for Streamlit Cloud), then environment variable
    try:
        import streamlit as st
        api_key = api_key or st.secrets.get('GOOGLE_PLACES_API_KEY', None)
    except:
        pass
    
    # Try Streamlit secrets first (for Streamlit Cloud), then environment variable
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get('GOOGLE_PLACES_API_KEY', None)
        except:
            pass
    
    api_key = api_key or os.getenv('GOOGLE_PLACES_API_KEY')
    if not api_key:
        return []
    
    try:
        gmaps = googlemaps.Client(key=api_key)
        
        # Search for staffing agencies
        search_query = f"{query} {location}"
        places_result = gmaps.places(query=search_query, type='establishment')
        
        # Check for API errors
        if places_result.get('status') == 'REQUEST_DENIED':
            error_msg = places_result.get('error_message', 'Unknown error')
            if 'billing' in error_msg.lower() or 'REQUEST_DENIED' in str(error_msg):
                raise ValueError(
                    "Google Places API requires billing to be enabled.\n\n"
                    "To fix this:\n"
                    "1. Go to https://console.cloud.google.com/project/_/billing/enable\n"
                    "2. Enable billing for your Google Cloud project\n"
                    "3. Google offers $200 free credit per month for Maps API\n"
                    "4. Most small projects stay within the free tier\n\n"
                    f"Error: {error_msg}"
                )
            else:
                raise ValueError(f"Google Places API error: {error_msg}")
        
        leads = []
        for place in places_result.get('results', [])[:max_results]:
            name = place.get('name', '')
            website = None
            phone = None
            address = place.get('formatted_address', '')
            
            # Get place details for website and phone
            if 'place_id' in place:
                try:
                    details = gmaps.place(place_id=place['place_id'], fields=['website', 'formatted_phone_number', 'international_phone_number'])
                    result = details.get('result', {})
                    website = result.get('website')
                    phone = result.get('formatted_phone_number') or result.get('international_phone_number')
                except Exception as detail_error:
                    # Check if it's a billing error
                    if 'REQUEST_DENIED' in str(detail_error) or 'billing' in str(detail_error).lower():
                        raise ValueError(
                            "Google Places API requires billing to be enabled.\n\n"
                            "To fix this:\n"
                            "1. Go to https://console.cloud.google.com/project/_/billing/enable\n"
                            "2. Enable billing for your Google Cloud project\n"
                            "3. Google offers $200 free credit per month for Maps API\n"
                            "4. Most small projects stay within the free tier"
                        )
                    pass
            
            lead = CompanyLead(
                company_name=name,
                website=website,
                address=address,
                phone=phone,
                source="google_places",
                scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
            )
            leads.append(lead)
            
            time.sleep(0.1)  # Rate limiting
        
        return leads
    except ValueError as e:
        # Re-raise ValueError (billing errors) so they can be displayed to user
        raise
    except Exception as e:
        error_str = str(e)
        if 'REQUEST_DENIED' in error_str or 'billing' in error_str.lower():
            raise ValueError(
                "Google Places API requires billing to be enabled.\n\n"
                "To fix this:\n"
                "1. Go to https://console.cloud.google.com/project/_/billing/enable\n"
                "2. Enable billing for your Google Cloud project\n"
                "3. Google offers $200 free credit per month for Maps API\n"
                "4. Most small projects stay within the free tier\n\n"
                f"Error: {error_str}"
            )
        print(f"Error searching Google Places: {e}")
        return []

def check_company_for_indicators(
    company_domain: str,
    indicators: List[TargetIndicator] = None,
    check_subdomain: bool = True,
    check_links: bool = True,
    check_keywords: bool = False,
    timeout: int = 10
) -> Dict[str, Dict[str, any]]:
    """
    Check if a company uses any target software by checking subdomains, links, and keywords
    
    Args:
        company_domain: Company domain (e.g., "primlogix.com")
        indicators: List of TargetIndicator to check (defaults to DEFAULT_INDICATORS)
        check_subdomain: Whether to check subdomains
        check_links: Whether to check for links in website
        check_keywords: Whether to check for keywords in website content
        timeout: Request timeout
    
    Returns:
        Dict mapping indicator name to {"found": bool, "evidence": str, "method": str}
    """
    if indicators is None:
        if CONFIG_AVAILABLE:
            indicators = DEFAULT_INDICATORS
        else:
            return {}
    
    results = {}
    
    # Extract domain from URL if needed
    if not company_domain:
        return results
    
    domain = company_domain.replace('www.', '').replace('https://', '').replace('http://', '').split('/')[0]
    website_url = f"https://{domain}" if not domain.startswith(('http://', 'https://')) else domain
    
    for indicator in indicators:
        found = False
        evidence = None
        method = None
        
        # Check subdomain
        if check_subdomain and indicator.subdomain_pattern:
            found, subdomain_url = check_subdomain_for_indicator(domain, indicator, timeout)
            if found:
                evidence = subdomain_url
                method = "subdomain"
        
        # Check links in website
        if not found and check_links and indicator.link_patterns:
            found, link_evidence = check_links_for_indicator(website_url, indicator, timeout)
            if found:
                evidence = link_evidence
                method = "link"
        
        # Check keywords in website (if links not found)
        if not found and check_keywords and indicator.keywords:
            try:
                response = requests.get(website_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
                if response.status_code == 200:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')
                    text = soup.get_text()
                    found, keyword_evidence = check_keywords_for_indicator(text, indicator)
                    if found:
                        evidence = keyword_evidence
                        method = "keyword"
            except:
                pass
        
        results[indicator.name] = {
            "found": found,
            "evidence": evidence,
            "method": method
        }
    
    return results

# Backward compatibility functions
def check_avionte_subdomain(company_domain: str, timeout: int = 5) -> tuple[bool, Optional[str]]:
    """Backward compatibility - checks for Avionté subdomain"""
    if not CONFIG_AVAILABLE:
        return False, None
    
    avionte_indicator = None
    for ind in DEFAULT_INDICATORS:
        if ind.name.lower() == "avionté" or ind.name.lower() == "avionte":
            avionte_indicator = ind
            break
    
    if avionte_indicator:
        return check_subdomain_for_indicator(company_domain, avionte_indicator, timeout)
    return False, None

def check_website_for_avionte(url: str, timeout: int = 10) -> tuple[bool, Optional[str]]:
    """Backward compatibility - checks website for Avionté"""
    if not url:
        return False, None
    
    from urllib.parse import urlparse
    parsed = urlparse(url if url.startswith(('http://', 'https://')) else f'https://{url}')
    domain = parsed.netloc.replace('www.', '')
    
    results = check_company_for_indicators(domain, check_subdomain=True, check_links=True, timeout=timeout)
    
    # Check for Avionté in results
    for name, result in results.items():
        if "avionté" in name.lower() or "avionte" in name.lower():
            if result["found"]:
                return True, result["evidence"]
    
    return False, None

def scrape_company_website(url: str) -> Optional[Dict]:
    """
    Scrape company website for contact info
    
    Returns:
        Dict with company info (email, phone, description)
    """
    if not url:
        return None
    
    # Auto-add https:// if protocol is missing
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        if response.status_code != 200:
            return {
                'email': None,
                'phone': None,
                'description': None
            }
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract contact information
        email = None
        phone = None
        
        # Get all text from the page
        text = soup.get_text()
        
        # Also check in href attributes for mailto: and tel:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').lower()
            if href.startswith('mailto:'):
                email_candidate = href.replace('mailto:', '').split('?')[0].strip()
                if '@' in email_candidate and not any(x in email_candidate.lower() for x in ['example', 'test', 'noreply', 'no-reply']):
                    email = email_candidate
                    break
            elif href.startswith('tel:'):
                phone_candidate = href.replace('tel:', '').replace('+', '').replace('-', '').replace(' ', '').strip()
                if phone_candidate and len(phone_candidate) >= 10:
                    phone = phone_candidate
                    break
        
        # Find email in text if not found in links
        if not email:
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, text)
            if emails:
                # Filter out common non-contact emails
                valid_emails = [e for e in emails if not any(x in e.lower() for x in ['example', 'test', 'noreply', 'no-reply', 'email', 'contact'])]
                if valid_emails:
                    email = valid_emails[0]
        
        # Find phone in text if not found in links
        if not phone:
            phone_patterns = [
                r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
                r'\d{3}[-.\s]?\d{3}[-.\s]?\d{4}',
                r'\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            ]
            for pattern in phone_patterns:
                phones = re.findall(pattern, text)
                if phones:
                    # Take the first phone that looks valid
                    for p in phones:
                        digits_only = re.sub(r'\D', '', p)
                        if len(digits_only) >= 10:
                            phone = p.strip()
                            break
                    if phone:
                        break
        
        return {
            'email': email,
            'phone': phone,
            'description': soup.find('meta', attrs={'name': 'description'})
        }
    except Exception as e:
        return None

def search_indeed_jobs(query: str = "Avionté", location: str = "United States", max_results: int = 50) -> List[CompanyLead]:
    """
    Search Indeed job postings for companies using Avionté
    
    Returns:
        List of CompanyLead objects
    """
    leads = []
    
    try:
        # Indeed search URL
        base_url = "https://www.indeed.com/jobs"
        params = {
            'q': query,
            'l': location,
            'start': 0
        }
        
        # Use Playwright if available for JavaScript rendering
        # For now, try basic requests
        response = requests.get(base_url, params=params, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Indeed job cards
            job_cards = soup.find_all('div', class_=lambda x: x and 'job_seen_beacon' in x)
            
            for card in job_cards[:max_results]:
                try:
                    # Extract company name
                    company_el = card.find('span', class_=lambda x: x and 'companyName' in str(x))
                    if not company_el:
                        company_el = card.find('a', attrs={'data-testid': 'company-name'})
                    
                    if company_el:
                        company_name = company_el.get_text(strip=True)
                        
                        # Extract job title/link for context
                        job_title_el = card.find('a', attrs={'data-jk': True}) or card.find('h2', class_=lambda x: x and 'jobTitle' in str(x))
                        job_title = job_title_el.get_text(strip=True) if job_title_el else ""
                        
                        # Add all companies - will check for indicators later
                        lead = CompanyLead(
                            company_name=company_name,
                            description=f"Job posting: {job_title}",
                            source="indeed_jobs",
                            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                        )
                        leads.append(lead)
                except:
                    continue
    except Exception as e:
        print(f"Error searching Indeed: {e}")
    
    return leads

def search_linkedin_companies(query: str = "staffing agency", max_results: int = 20) -> List[CompanyLead]:
    """
    Search LinkedIn for staffing agencies (basic scraping)
    Note: LinkedIn has strict anti-scraping, so this is limited
    
    Returns:
        List of CompanyLead objects
    """
    leads = []
    
    # LinkedIn search URL (public search)
    try:
        search_url = f"https://www.linkedin.com/search/results/companies/"
        params = {
            'keywords': query,
        }
        
        # LinkedIn requires authentication for most content
        # This is a placeholder - would need LinkedIn API or authenticated session
        # For now, return empty list
        return leads
    except:
        return leads

def discover_leads_from_google_places(
    search_queries: List[str],
    location: str = "United States",
    check_websites: bool = True,
    api_key: Optional[str] = None,
    indicators: List[TargetIndicator] = None
) -> List[CompanyLead]:
    """
    Discover leads from Google Places and check their websites for target indicators
    
    Args:
        search_queries: List of search queries (e.g., ["staffing agency", "temporary staffing"])
        location: Location to search
        check_websites: Whether to check company websites for target indicators
        api_key: Google Places API key
        indicators: List of TargetIndicator to check (defaults to DEFAULT_INDICATORS)
    
    Returns:
        List of CompanyLead objects
    """
    if indicators is None and CONFIG_AVAILABLE:
        indicators = DEFAULT_INDICATORS
    
    all_leads = []
    
    for query in search_queries:
        places_leads = search_google_places(query, location, api_key)
        
        if check_websites and indicators:
            for lead in places_leads:
                if lead.website:
                    # Check for all target indicators
                    results = check_company_for_indicators(
                        lead.website,
                        indicators,
                        check_subdomain=True,
                        check_links=True,
                        check_keywords=False
                    )
                    
                    # Update lead with indicator results
                    for ind_name, result in results.items():
                        lead.target_indicators[ind_name] = result["found"]
                        if result["found"]:
                            lead.indicator_evidence[ind_name] = result["evidence"] or ""
                    
                    # Also enrich with contact info
                    website_data = scrape_company_website(lead.website)
                    if website_data:
                        if website_data.get('email') and not lead.email:
                            lead.email = website_data['email']
                        if website_data.get('phone') and not lead.phone:
                            lead.phone = website_data['phone']
                    
                    time.sleep(0.5)  # Rate limiting
        
        all_leads.extend(places_leads)
        time.sleep(0.5)  # Rate limiting between queries
    
    return all_leads

def discover_leads_from_job_boards(
    queries: List[str] = ["Avionté", "Avionte staffing software"],
    location: str = "United States"
) -> List[CompanyLead]:
    """
    Discover leads from job boards (Indeed, etc.)
    
    Returns:
        List of CompanyLead objects
    """
    all_leads = []
    
    for query in queries:
        indeed_leads = search_indeed_jobs(query, location)
        all_leads.extend(indeed_leads)
        time.sleep(2)  # Rate limiting
    
    return all_leads

def convert_company_lead_to_review_lead(company_lead: CompanyLead, LeadReview_class, calculate_lead_score_func) -> Optional:
    """
    Convert a CompanyLead to a LeadReview format for database storage
    
    Args:
        company_lead: CompanyLead to convert
        LeadReview_class: LeadReview dataclass class
        calculate_lead_score_func: Function to calculate lead score
    
    Returns:
        LeadReview object or None
    """
    # Only convert if any indicator found
    if not company_lead.has_any_indicator():
        return None
    
    # Get the indicator to use
    indicators = company_lead.get_indicators()
    if not indicators:
        return None
    
    # Use first found indicator
    target_indicator = indicators[0]
    evidence = company_lead.indicator_evidence.get(target_indicator, "Indicator found")
    
    # Create a review-like lead from company discovery
    review_text = f"Company discovered using {target_indicator}. Evidence: {evidence}"
    
    lead = LeadReview_class(
        company_name=company_lead.company_name,
        reviewer_name="Discovery",
        review_title=f"{target_indicator} User: {company_lead.company_name}",
        review_text=review_text,
        rating=None,  # No rating from discovery
        pain_tags=f"discovery,{target_indicator.lower()}",  # Tag as discovered lead
        source_url=company_lead.website or f"discovery:{company_lead.source}",
        scraped_at=company_lead.scraped_at or datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    
    # Calculate score (discovery leads get base score)
    lead.lead_score = calculate_lead_score_func(lead)
    
    return lead

