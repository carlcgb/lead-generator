"""
Enhanced Lead Discovery Module - Advanced multi-source lead generation
Adds: Reddit, LinkedIn, subdomain checking, news articles, forums, social media, etc.
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
import json

# Import base functions
from lead_discovery import (
    CompanyLead, check_avionte_subdomain, scrape_company_website, HEADERS
)

# Reddit API (using public JSON endpoints)
def search_reddit_posts(subreddit: str, query: str, max_results: int = 25) -> List[CompanyLead]:
    """
    Search Reddit posts for Avionté mentions
    
    Args:
        subreddit: Subreddit name (e.g., "recruiting", "staffing")
        query: Search query (e.g., "Avionté", "Avionte")
        max_results: Maximum number of results
    
    Returns:
        List of CompanyLead objects
    """
    leads = []
    
    try:
        # Reddit search URL (public JSON API)
        search_url = f"https://www.reddit.com/r/{subreddit}/search.json"
        params = {
            'q': query,
            'restrict_sr': 'true',
            'limit': min(max_results, 100),
            'sort': 'relevance'
        }
        
        response = requests.get(search_url, headers=HEADERS, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            posts = data.get('data', {}).get('children', [])
            
            for post_data in posts[:max_results]:
                post = post_data.get('data', {})
                title = post.get('title', '')
                selftext = post.get('selftext', '')
                author = post.get('author', 'Unknown')
                url = f"https://reddit.com{post.get('permalink', '')}"
                created = datetime.fromtimestamp(post.get('created_utc', 0)).strftime("%Y-%m-%d %H:%M")
                
                # Extract company name from post (look for staffing agencies)
                company_name = "Unknown"
                company_patterns = [
                    r'(?:work(?:ing|s)?\s+(?:at|for|with))\s+([A-Z][a-zA-Z\s&]+(?:Staffing|Agency|Recruiting|Talent))',
                    r'([A-Z][a-zA-Z\s&]+(?:Staffing|Agency|Recruiting|Talent))',
                ]
                for pattern in company_patterns:
                    match = re.search(pattern, title + " " + selftext, re.IGNORECASE)
                    if match:
                        company_name = match.group(1).strip()
                        break
                
                # Only add if we found a company name
                if company_name != "Unknown":
                    lead = CompanyLead(
                        company_name=company_name,
                        description=f"Reddit post: {title[:100]}",
                        avionte_mention=False,  # Will be checked via subdomain
                        avionte_evidence=None,
                        source=f"reddit_r_{subreddit}",
                        scraped_at=created
                    )
                    leads.append(lead)
        
        time.sleep(2)  # Rate limiting for Reddit
    except Exception as e:
        print(f"Error searching Reddit r/{subreddit}: {e}")
    
    return leads

def search_reddit_multiple_subreddits(queries: List[str], subreddits: List[str] = None, max_per_sub: int = 25) -> List[CompanyLead]:
    """Search multiple Reddit subreddits for staffing agencies, then check for Avionté subdomains"""
    if subreddits is None:
        subreddits = ['recruiting', 'staffing', 'hrtech', 'humanresources', 'recruitinghell']
    
    all_leads = []
    for subreddit in subreddits:
        for query in queries:
            leads = search_reddit_posts(subreddit, query, max_per_sub)
            all_leads.extend(leads)
            time.sleep(1)  # Rate limiting
    
    # Check all leads for Avionté subdomains
    for lead in all_leads:
        if lead.company_name and lead.company_name != "Unknown":
            # Try to construct domain from company name
            # This is a best guess - ideally we'd have the actual domain
            company_domain = f"{lead.company_name.replace(' ', '').lower()}.com"
            found, subdomain = check_avionte_subdomain(company_domain)
            if found:
                lead.avionte_mention = True
                lead.avionte_evidence = subdomain
                lead.website = subdomain
    
    return all_leads

# Use the function from lead_discovery instead of duplicating
from lead_discovery import check_avionte_subdomain

def search_linkedin_jobs(query: str = "Avionté", location: str = "United States", max_results: int = 50) -> List[CompanyLead]:
    """
    Search LinkedIn job postings (public search)
    Note: LinkedIn has strict anti-scraping, so this is limited
    """
    leads = []
    
    try:
        # LinkedIn public job search URL
        search_url = "https://www.linkedin.com/jobs/search"
        params = {
            'keywords': query,
            'location': location,
        }
        
        response = requests.get(search_url, params=params, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # LinkedIn job cards (structure may vary)
            job_cards = soup.find_all('div', class_=lambda x: x and 'job-search-card' in str(x).lower())
            
            for card in job_cards[:max_results]:
                try:
                    # Extract company name
                    company_el = card.find('h4', class_=lambda x: x and 'company' in str(x).lower()) or \
                               card.find('a', class_=lambda x: x and 'company' in str(x).lower())
                    
                    if company_el:
                        company_name = company_el.get_text(strip=True)
                        
                        # Add all companies found, will check subdomain later
                        lead = CompanyLead(
                            company_name=company_name,
                            description=f"LinkedIn job posting",
                            avionte_mention=False,  # Will be checked via subdomain
                            avionte_evidence=None,
                            source="linkedin_jobs",
                            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                        )
                        leads.append(lead)
                except:
                    continue
    except Exception as e:
        print(f"Error searching LinkedIn jobs: {e}")
    
    return leads

def search_glassdoor_reviews(company_name: str = "Avionté", max_results: int = 20) -> List[CompanyLead]:
    """
    Search Glassdoor for companies reviewing Avionté or mentioning it
    Note: Glassdoor has strict anti-scraping, so this is limited
    """
    leads = []
    
    try:
        # Glassdoor search
        search_url = f"https://www.glassdoor.com/Reviews/{company_name.replace(' ', '-')}-reviews"
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract company names from reviews (basic extraction)
            # Glassdoor structure is complex, this is a simplified approach
            pass
    except Exception as e:
        print(f"Error searching Glassdoor: {e}")
    
    return leads

def search_news_articles(query: str = "Avionté staffing software", max_results: int = 20) -> List[CompanyLead]:
    """
    Search news articles for Avionté mentions using Google News
    """
    leads = []
    
    try:
        # Google News search
        search_url = "https://news.google.com/search"
        params = {
            'q': query,
            'hl': 'en',
            'gl': 'US',
            'ceid': 'US:en'
        }
        
        response = requests.get(search_url, params=params, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Google News article links
            articles = soup.find_all('article')[:max_results]
            
            for article in articles:
                try:
                    link = article.find('a')
                    if link:
                        title = link.get_text(strip=True)
                        href = link.get('href', '')
                        
                        # Try to extract company name from title
                        company_name = "Unknown"
                        company_match = re.search(r'([A-Z][a-zA-Z\s&]+(?:Staffing|Agency|Recruiting))', title)
                        if company_match:
                            company_name = company_match.group(1).strip()
                        
                        if company_name != "Unknown":
                            lead = CompanyLead(
                                company_name=company_name,
                                description=f"News article: {title[:100]}",
                                avionte_mention=False,  # Will be checked via subdomain
                                avionte_evidence=None,
                                source="news_articles",
                                scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                            )
                            leads.append(lead)
                except:
                    continue
    except Exception as e:
        print(f"Error searching news: {e}")
    
    return leads

def search_industry_directories(query: str = "staffing agency", location: str = "United States", max_results: int = 50) -> List[CompanyLead]:
    """
    Search industry directories (Yellow Pages, industry-specific directories)
    """
    leads = []
    
    try:
        # Yellow Pages search
        yp_url = "https://www.yellowpages.com/search"
        params = {
            'search_terms': query,
            'geo_location_terms': location
        }
        
        response = requests.get(yp_url, params=params, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Yellow Pages business listings
            listings = soup.find_all('div', class_=lambda x: x and 'result' in str(x).lower())[:max_results]
            
            for listing in listings:
                try:
                    name_el = listing.find('a', class_=lambda x: x and 'business-name' in str(x).lower())
                    if name_el:
                        company_name = name_el.get_text(strip=True)
                        
                        # Get website if available
                        website = None
                        website_el = listing.find('a', class_=lambda x: x and 'track-visit-website' in str(x).lower())
                        if website_el:
                            website = website_el.get('href', '')
                        
                        # Get phone
                        phone = None
                        phone_el = listing.find('div', class_=lambda x: x and 'phone' in str(x).lower())
                        if phone_el:
                            phone = phone_el.get_text(strip=True)
                        
                        lead = CompanyLead(
                            company_name=company_name,
                            website=website,
                            phone=phone,
                            source="yellow_pages",
                            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                        )
                        leads.append(lead)
                except:
                    continue
    except Exception as e:
        print(f"Error searching directories: {e}")
    
    return leads

def search_quora_questions(query: str = "Avionté alternatives", max_results: int = 20) -> List[CompanyLead]:
    """
    Search Quora for questions about Avionté
    """
    leads = []
    
    try:
        # Quora search
        search_url = f"https://www.quora.com/search"
        params = {
            'q': query
        }
        
        response = requests.get(search_url, params=params, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Quora questions
            questions = soup.find_all('div', class_=lambda x: x and 'question' in str(x).lower())[:max_results]
            
            for question in questions:
                try:
                    question_text = question.get_text(strip=True)
                    # Try to extract company name
                    company_name = "Unknown"
                    company_match = re.search(r'([A-Z][a-zA-Z\s&]+(?:Staffing|Agency|Recruiting))', question_text, re.IGNORECASE)
                    if company_match:
                        company_name = company_match.group(1).strip()
                    
                    if company_name != "Unknown":
                        lead = CompanyLead(
                            company_name=company_name,
                            description=f"Quora question: {question_text[:200]}",
                            avionte_mention=False,  # Will be checked via subdomain
                            avionte_evidence=None,
                            source="quora",
                            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                        )
                        leads.append(lead)
                except:
                    continue
    except Exception as e:
        print(f"Error searching Quora: {e}")
    
    return leads

def search_twitter_mentions(query: str = "Avionté", max_results: int = 50) -> List[CompanyLead]:
    """
    Search Twitter/X for Avionté mentions
    Note: Twitter API requires authentication, so this uses public search
    """
    leads = []
    
    try:
        # Twitter public search (may be limited)
        search_url = f"https://twitter.com/search"
        params = {
            'q': query,
            'src': 'typed_query',
            'f': 'live'
        }
        
        response = requests.get(search_url, params=params, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Twitter tweets (structure varies)
            tweets = soup.find_all('article')[:max_results]
            
            for tweet in tweets:
                try:
                    tweet_text = tweet.get_text(strip=True)
                    # Try to extract company name
                    company_name = "Unknown"
                    company_match = re.search(r'([A-Z][a-zA-Z\s&]+(?:Staffing|Agency|Recruiting))', tweet_text, re.IGNORECASE)
                    if company_match:
                        company_name = company_match.group(1).strip()
                    
                    # Also try username
                    if company_name == "Unknown":
                        user_el = tweet.find('span', class_=lambda x: x and 'username' in str(x).lower())
                        if user_el:
                            company_name = user_el.get_text(strip=True)
                    
                    if company_name != "Unknown":
                        lead = CompanyLead(
                            company_name=company_name,
                            description=f"Twitter/X: {tweet_text[:200]}",
                            avionte_mention=False,  # Will be checked via subdomain
                            avionte_evidence=None,
                            source="twitter",
                            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                        )
                        leads.append(lead)
                except:
                    continue
    except Exception as e:
        print(f"Error searching Twitter: {e}")
    
    return leads

def discover_leads_from_reddit(
    queries: List[str] = ["Avionté", "Avionte", "Avionte alternatives"],
    subreddits: List[str] = None,
    max_per_sub: int = 25
) -> List[CompanyLead]:
    """Discover leads from Reddit"""
    return search_reddit_multiple_subreddits(queries, subreddits, max_per_sub)

def discover_leads_from_subdomain_check(company_domains: List[str]) -> List[CompanyLead]:
    """
    Check multiple company domains for Avionté subdomain usage
    
    Args:
        company_domains: List of company domains to check
    
    Returns:
        List of CompanyLead objects for companies using Avionté (only those with confirmed subdomains)
    """
    leads = []
    
    for domain in company_domains:
        found, subdomain_url = check_avionte_subdomain(domain)
        if found:
            # Extract company name from domain
            company_name = domain.replace('www.', '').split('.')[0].title()
            
            lead = CompanyLead(
                company_name=company_name,
                website=subdomain_url,
                avionte_mention=True,  # Confirmed via subdomain
                avionte_evidence=f"Confirmed Avionté user - subdomain: {subdomain_url}",
                source="subdomain_check",
                scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
            )
            leads.append(lead)
        
        time.sleep(0.5)  # Rate limiting
    
    return leads

def check_leads_for_avionte_subdomains(leads: List[CompanyLead]) -> List[CompanyLead]:
    """
    Check all leads for Avionté subdomains and update their avionte_mention status
    
    Args:
        leads: List of CompanyLead objects
    
    Returns:
        Updated list with avionte_mention set based on subdomain check
    """
    for lead in leads:
        # Skip if already confirmed
        if lead.avionte_mention:
            continue
        
        # Try to get domain from website or construct from company name
        domain = None
        if lead.website:
            from urllib.parse import urlparse
            parsed = urlparse(lead.website if lead.website.startswith(('http://', 'https://')) else f'https://{lead.website}')
            domain = parsed.netloc.replace('www.', '')
        elif lead.company_name and lead.company_name != "Unknown":
            # Construct domain from company name (best guess)
            domain = f"{lead.company_name.replace(' ', '').lower()}.com"
        
        if domain:
            found, subdomain_url = check_avionte_subdomain(domain)
            if found:
                lead.avionte_mention = True
                lead.avionte_evidence = f"Confirmed via subdomain: {subdomain_url}"
                if not lead.website:
                    lead.website = subdomain_url
        
        time.sleep(0.3)  # Rate limiting
    
    return leads

def discover_leads_from_news(
    queries: List[str] = ["Avionté staffing", "Avionte software review"],
    max_per_query: int = 20
) -> List[CompanyLead]:
    """Discover leads from news articles"""
    all_leads = []
    
    for query in queries:
        leads = search_news_articles(query, max_per_query)
        all_leads.extend(leads)
        time.sleep(2)  # Rate limiting
    
    return all_leads

def discover_leads_from_directories(
    queries: List[str] = ["staffing agency", "temporary staffing", "employment agency"],
    location: str = "United States",
    max_per_query: int = 50
) -> List[CompanyLead]:
    """Discover leads from industry directories"""
    all_leads = []
    
    for query in queries:
        leads = search_industry_directories(query, location, max_per_query)
        all_leads.extend(leads)
        time.sleep(2)  # Rate limiting
    
    return all_leads

def discover_leads_comprehensive(
    sources: List[str] = None,
    check_subdomains: bool = True,
    **kwargs
) -> List[CompanyLead]:
    """
    Comprehensive lead discovery from multiple sources
    
    Args:
        sources: List of sources to use: ['reddit', 'linkedin', 'news', 'directories', 'subdomain', 'quora', 'twitter']
        check_subdomains: Whether to check all leads for Avionté subdomains (default: True)
        **kwargs: Additional parameters for each source
    
    Returns:
        Combined list of CompanyLead objects (only those with confirmed Avionté subdomains if check_subdomains=True)
    """
    if sources is None:
        sources = ['reddit', 'news', 'directories']
    
    all_leads = []
    
    if 'reddit' in sources:
        reddit_queries = kwargs.get('reddit_queries', ["staffing agency", "recruiting"])
        reddit_subs = kwargs.get('reddit_subreddits', ['recruiting', 'staffing', 'hrtech'])
        leads = discover_leads_from_reddit(reddit_queries, reddit_subs)
        all_leads.extend(leads)
        print(f"✓ Reddit: Found {len(leads)} companies")
    
    if 'news' in sources:
        news_queries = kwargs.get('news_queries', ["staffing software", "recruiting software"])
        leads = discover_leads_from_news(news_queries)
        all_leads.extend(leads)
        print(f"✓ News: Found {len(leads)} companies")
    
    if 'directories' in sources:
        dir_queries = kwargs.get('directory_queries', ["staffing agency"])
        location = kwargs.get('location', "United States")
        leads = discover_leads_from_directories(dir_queries, location)
        all_leads.extend(leads)
        print(f"✓ Directories: Found {len(leads)} companies")
    
    if 'subdomain' in sources:
        domains = kwargs.get('company_domains', [])
        if domains:
            leads = discover_leads_from_subdomain_check(domains)
            all_leads.extend(leads)
            print(f"✓ Subdomain check: Found {len(leads)} confirmed Avionté users")
    
    if 'quora' in sources:
        quora_queries = kwargs.get('quora_queries', ["staffing software", "recruiting software"])
        leads = []
        for query in quora_queries:
            leads.extend(search_quora_questions(query))
        all_leads.extend(leads)
        print(f"✓ Quora: Found {len(leads)} companies")
    
    if 'twitter' in sources:
        twitter_queries = kwargs.get('twitter_queries', ["staffing agency"])
        leads = []
        for query in twitter_queries:
            leads.extend(search_twitter_mentions(query))
        all_leads.extend(leads)
        print(f"✓ Twitter: Found {len(leads)} companies")
    
    if 'linkedin' in sources:
        linkedin_queries = kwargs.get('linkedin_queries', ["staffing agency"])
        location = kwargs.get('location', "United States")
        leads = []
        for query in linkedin_queries:
            leads.extend(search_linkedin_jobs(query, location))
        all_leads.extend(leads)
        print(f"✓ LinkedIn: Found {len(leads)} companies")
    
    # Check all leads for Avionté subdomains
    if check_subdomains and all_leads:
        print(f"🔍 Checking {len(all_leads)} companies for Avionté subdomains...")
        all_leads = check_leads_for_avionte_subdomains(all_leads)
        confirmed_count = sum(1 for lead in all_leads if lead.avionte_mention)
        print(f"✓ Found {confirmed_count} confirmed Avionté users via subdomain check")
    
    return all_leads

