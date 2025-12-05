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

# Import configuration
try:
    from lead_config import (
        TargetIndicator, DEFAULT_INDICATORS, load_indicators_from_file
    )
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

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
            
            for post in posts:
                post_data = post.get('data', {})
                title = post_data.get('title', '')
                selftext = post_data.get('selftext', '')
                url = post_data.get('url', '')
                author = post_data.get('author', 'Unknown')
                
                # Try to extract company name from title or text
                company_name = "Unknown"
                # Look for company patterns in text
                company_patterns = [
                    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:staffing|recruiting|agency|company)',
                    r'company:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                    r'at\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                ]
                full_text = f"{title} {selftext}"
                for pattern in company_patterns:
                    match = re.search(pattern, full_text, re.IGNORECASE)
                    if match:
                        company_name = match.group(1)
                        break
                
                lead = CompanyLead(
                    company_name=company_name,
                    description=f"Reddit post: {title}",
                    website=None,
                    source="reddit",
                    scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                )
                leads.append(lead)
    except Exception as e:
        print(f"Error searching Reddit: {e}")
    
    return leads

def search_indeed_reviews(indicators: List[TargetIndicator] = None, max_results: int = 50) -> List[CompanyLead]:
    """
    Search Indeed company reviews for negative mentions of target software
    
    Args:
        indicators: List of TargetIndicator to search for (defaults to DEFAULT_INDICATORS)
        max_results: Maximum number of results per indicator
    
    Returns:
        List of CompanyLead objects with negative reviews
    """
    if not CONFIG_AVAILABLE:
        return []
    
    if indicators is None:
        indicators = load_indicators_from_file()
        if not indicators:
            indicators = DEFAULT_INDICATORS
    
    leads = []
    
    # Negative keywords to identify bad reviews
    negative_keywords = [
        "terrible", "awful", "horrible", "worst", "bad", "hate", "disappointed",
        "frustrated", "slow", "buggy", "broken", "doesn't work", "issues",
        "problems", "complaint", "poor", "unreliable", "difficult", "confusing"
    ]
    
    for indicator in indicators:
        # Search for reviews mentioning the software with negative sentiment
        search_queries = []
        for keyword in indicator.keywords:
            # Search for company reviews mentioning the software
            search_queries.append(f'"{keyword}" review')
            search_queries.append(f'"{keyword}" company review')
        
        for query in search_queries[:3]:  # Limit to 3 queries per indicator
            try:
                # Indeed company reviews search
                base_url = "https://www.indeed.com/companies/search"
                params = {
                    'q': query,
                    'from': 'discovery-cmp-search'
                }
                
                response = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Find company review links
                    company_links = soup.find_all('a', href=re.compile(r'/cmp/'))
                    
                    for link in company_links[:max_results]:
                        try:
                            company_name = link.get_text(strip=True)
                            if not company_name:
                                continue
                            
                            # Get company review page URL
                            href = link.get('href', '')
                            if not href.startswith('http'):
                                href = f"https://www.indeed.com{href}"
                            
                            # Try to get reviews page
                            reviews_url = href.replace('/cmp/', '/cmp/') + '/reviews'
                            
                            # Search for negative reviews mentioning the software
                            review_response = requests.get(reviews_url, headers=HEADERS, timeout=15)
                            
                            if review_response.status_code == 200:
                                review_soup = BeautifulSoup(review_response.text, 'html.parser')
                                
                                # Find review cards
                                review_cards = review_soup.find_all('div', class_=lambda x: x and 'review' in str(x).lower())
                                
                                for card in review_cards[:10]:  # Check first 10 reviews
                                    review_text = card.get_text(' ', strip=True).lower()
                                    
                                    # Check if review mentions the software and is negative
                                    mentions_software = any(kw.lower() in review_text for kw in indicator.keywords)
                                    is_negative = any(nkw in review_text for nkw in negative_keywords)
                                    
                                    if mentions_software and is_negative:
                                        # Extract rating if available
                                        rating_el = card.find(['span', 'div'], class_=lambda x: x and 'rating' in str(x).lower())
                                        rating = None
                                        if rating_el:
                                            rating_match = re.search(r'(\d+)', rating_el.get_text())
                                            if rating_match:
                                                try:
                                                    rating = float(rating_match.group(1))
                                                    if rating > 3:  # Skip positive ratings
                                                        continue
                                                except:
                                                    pass
                                        
                                        # Extract reviewer name
                                        reviewer_el = card.find(['span', 'div'], class_=lambda x: x and ('author' in str(x).lower() or 'reviewer' in str(x).lower()))
                                        reviewer_name = reviewer_el.get_text(strip=True) if reviewer_el else "Unknown"
                                        
                                        # Create lead
                                        lead = CompanyLead(
                                            company_name=company_name,
                                            description=f"Indeed review mentioning {indicator.name}: {review_text[:200]}",
                                            website=None,
                                            source=f"indeed_reviews_{indicator.name.lower()}",
                                            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                                        )
                                        
                                        # Mark that this indicator was found
                                        lead.target_indicators = {indicator.name: True}
                                        lead.indicator_evidence = {indicator.name: reviews_url}
                                        
                                        leads.append(lead)
                                        break  # One lead per company is enough
                            
                            time.sleep(1)  # Rate limiting
                        except Exception as e:
                            continue
                
                time.sleep(2)  # Rate limiting between queries
            except Exception as e:
                print(f"Error searching Indeed reviews for {indicator.name}: {e}")
                continue
    
    return leads

def search_linkedin_reviews(indicators: List[TargetIndicator] = None, max_results: int = 50) -> List[CompanyLead]:
    """
    Search LinkedIn posts/comments for negative mentions of target software
    
    Note: LinkedIn has strict anti-scraping measures. This function uses public search
    but may have limited results.
    
    Args:
        indicators: List of TargetIndicator to search for (defaults to DEFAULT_INDICATORS)
        max_results: Maximum number of results per indicator
    
    Returns:
        List of CompanyLead objects with negative mentions
    """
    if not CONFIG_AVAILABLE:
        return []
    
    if indicators is None:
        indicators = load_indicators_from_file()
        if not indicators:
            indicators = DEFAULT_INDICATORS
    
    leads = []
    
    # Negative keywords
    negative_keywords = [
        "terrible", "awful", "horrible", "worst", "bad", "hate", "disappointed",
        "frustrated", "slow", "buggy", "broken", "doesn't work", "issues",
        "problems", "complaint", "poor", "unreliable", "difficult", "confusing"
    ]
    
    for indicator in indicators:
        for keyword in indicator.keywords[:2]:  # Limit keywords
            try:
                # LinkedIn public search (limited without authentication)
                # Note: LinkedIn requires authentication for most content
                # This is a basic implementation that may have limited results
                
                search_url = "https://www.linkedin.com/search/results/content/"
                params = {
                    'keywords': f'"{keyword}" (terrible OR awful OR worst OR bad OR hate OR frustrated OR slow OR buggy)',
                    'origin': 'GLOBAL_SEARCH_HEADER'
                }
                
                # LinkedIn often blocks scraping, so we'll use a simpler approach
                # Search for posts mentioning the software
                # Note: This may not work without proper authentication
                
                # For now, return empty list with a note that LinkedIn requires authentication
                # In a production environment, you would need LinkedIn API access
                print(f"Note: LinkedIn search requires authentication. Skipping LinkedIn reviews for {indicator.name}.")
                
            except Exception as e:
                print(f"Error searching LinkedIn for {indicator.name}: {e}")
                continue
    
    return leads

def discover_leads_from_indeed_reviews(indicators: List[TargetIndicator] = None, max_results: int = 50) -> List[CompanyLead]:
    """
    Discover leads from Indeed reviews mentioning target software negatively
    
    Args:
        indicators: List of TargetIndicator to search for
        max_results: Maximum results per indicator
    
    Returns:
        List of CompanyLead objects
    """
    return search_indeed_reviews(indicators, max_results)

def discover_leads_from_linkedin_reviews(indicators: List[TargetIndicator] = None, max_results: int = 50) -> List[CompanyLead]:
    """
    Discover leads from LinkedIn posts/comments mentioning target software negatively
    
    Args:
        indicators: List of TargetIndicator to search for
        max_results: Maximum results per indicator
    
    Returns:
        List of CompanyLead objects
    """
    return search_linkedin_reviews(indicators, max_results)

def discover_leads_from_reddit(subreddits: List[str], queries: List[str], max_results: int = 25) -> List[CompanyLead]:
    """
    Discover leads from Reddit posts
    
    Args:
        subreddits: List of subreddit names to search
        queries: List of search queries
        max_results: Maximum results per subreddit/query combination
    
    Returns:
        List of CompanyLead objects
    """
    leads = []
    
    for subreddit in subreddits:
        for query in queries:
            try:
                subreddit_leads = search_reddit_posts(subreddit, query, max_results)
                leads.extend(subreddit_leads)
                time.sleep(1)  # Rate limiting
            except Exception as e:
                print(f"Error searching Reddit r/{subreddit} for '{query}': {e}")
                continue
    
    return leads

def discover_leads_from_subdomain_check(company_domains: List[str], indicators: List[TargetIndicator] = None) -> List[CompanyLead]:
    """
    Discover leads by checking subdomains for target software
    
    Args:
        company_domains: List of company domain names (e.g., ["primlogix.com"])
        indicators: List of TargetIndicator to check (defaults to DEFAULT_INDICATORS)
    
    Returns:
        List of CompanyLead objects with confirmed subdomain matches
    """
    if not CONFIG_AVAILABLE:
        return []
    
    if indicators is None:
        indicators = load_indicators_from_file()
        if not indicators:
            indicators = DEFAULT_INDICATORS
    
    leads = []
    
    from lead_config import check_subdomain_for_indicator
    
    for domain in company_domains:
        domain = domain.strip().replace('www.', '').replace('https://', '').replace('http://', '').split('/')[0]
        
        for indicator in indicators:
            try:
                found, subdomain_url = check_subdomain_for_indicator(domain, indicator)
                if found:
                    lead = CompanyLead(
                        company_name=domain.split('.')[0].title(),
                        website=f"https://{domain}",
                        source="subdomain_check",
                        scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                    )
                    lead.target_indicators = {indicator.name: True}
                    lead.indicator_evidence = {indicator.name: subdomain_url}
                    leads.append(lead)
                    break  # Found one indicator, move to next company
            except Exception as e:
                continue
    
    return leads

def discover_leads_from_news(queries: List[str], max_results: int = 20) -> List[CompanyLead]:
    """
    Discover leads from news articles mentioning companies
    
    Args:
        queries: List of search queries
        max_results: Maximum results per query
    
    Returns:
        List of CompanyLead objects
    """
    leads = []
    
    # Use Google News search
    for query in queries:
        try:
            search_url = "https://news.google.com/search"
            params = {
                'q': query,
                'hl': 'en',
                'gl': 'US',
                'ceid': 'US:en'
            }
            
            response = requests.get(search_url, headers=HEADERS, params=params, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find article links
                articles = soup.find_all('article')[:max_results]
                
                for article in articles:
                    try:
                        link = article.find('a', href=True)
                        if not link:
                            continue
                        
                        title = link.get_text(strip=True)
                        href = link.get('href', '')
                        
                        # Try to extract company name from title
                        company_name = "Unknown"
                        company_patterns = [
                            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:announces|reports|launches)',
                            r'(?:at|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                        ]
                        for pattern in company_patterns:
                            match = re.search(pattern, title)
                            if match:
                                company_name = match.group(1)
                                break
                        
                        lead = CompanyLead(
                            company_name=company_name,
                            description=f"News: {title}",
                            website=None,
                            source="news",
                            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                        )
                        leads.append(lead)
                    except:
                        continue
                
                time.sleep(1)  # Rate limiting
        except Exception as e:
            print(f"Error searching news for '{query}': {e}")
            continue
    
    return leads

def discover_leads_from_directories(queries: List[str], location: str = "United States", max_results: int = 50) -> List[CompanyLead]:
    """
    Discover leads from business directories (Yellow Pages, etc.)
    
    Args:
        queries: List of search queries
        location: Location to search
        max_results: Maximum results per query
    
    Returns:
        List of CompanyLead objects
    """
    leads = []
    
    for query in queries:
        try:
            # Yellow Pages search
            search_url = "https://www.yellowpages.com/search"
            params = {
                'search_terms': query,
                'geo_location_terms': location
            }
            
            response = requests.get(search_url, headers=HEADERS, params=params, timeout=15)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find business listings
                listings = soup.find_all('div', class_=lambda x: x and 'result' in str(x).lower())[:max_results]
                
                for listing in listings:
                    try:
                        name_el = listing.find(['h2', 'h3', 'a'], class_=lambda x: x and ('name' in str(x).lower() or 'title' in str(x).lower()))
                        company_name = name_el.get_text(strip=True) if name_el else "Unknown"
                        
                        website_el = listing.find('a', href=re.compile(r'http'))
                        website = website_el.get('href') if website_el else None
                        
                        phone_el = listing.find(['span', 'div'], class_=lambda x: x and 'phone' in str(x).lower())
                        phone = phone_el.get_text(strip=True) if phone_el else None
                        
                        lead = CompanyLead(
                            company_name=company_name,
                            website=website,
                            phone=phone,
                            source="directory",
                            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                        )
                        leads.append(lead)
                    except:
                        continue
                
                time.sleep(1)  # Rate limiting
        except Exception as e:
            print(f"Error searching directories for '{query}': {e}")
            continue
    
    return leads

def discover_leads_comprehensive(
    sources: List[str] = None,
    indicators: List[TargetIndicator] = None,
    max_results: int = 50
) -> List[CompanyLead]:
    """
    Comprehensive lead discovery from multiple sources
    
    Args:
        sources: List of sources to search ('reddit', 'news', 'directories', 'subdomain', 'indeed_reviews', 'linkedin_reviews')
        indicators: List of TargetIndicator to search for
        max_results: Maximum results per source
    
    Returns:
        List of CompanyLead objects
    """
    if sources is None:
        sources = ['reddit', 'news', 'directories']
    
    all_leads = []
    
    if 'indeed_reviews' in sources:
        indeed_leads = discover_leads_from_indeed_reviews(indicators, max_results)
        all_leads.extend(indeed_leads)
    
    if 'linkedin_reviews' in sources:
        linkedin_leads = discover_leads_from_linkedin_reviews(indicators, max_results)
        all_leads.extend(linkedin_leads)
    
    if 'reddit' in sources:
        # Default Reddit search
        reddit_leads = discover_leads_from_reddit(
            ['recruiting', 'staffing', 'hr'],
            ['staffing software', 'recruiting software'],
            max_results
        )
        all_leads.extend(reddit_leads)
    
    if 'news' in sources:
        news_leads = discover_leads_from_news(
            ['staffing agency', 'recruiting firm'],
            max_results
        )
        all_leads.extend(news_leads)
    
    if 'directories' in sources:
        dir_leads = discover_leads_from_directories(
            ['staffing agency', 'recruiting firm'],
            max_results=max_results
        )
        all_leads.extend(dir_leads)
    
    return all_leads
