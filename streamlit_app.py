import streamlit as st
import csv
import io
import json
import time
import os
import re
import sqlite3
import hashlib
import threading
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from typing import List, Optional
from dotenv import load_dotenv
import pandas as pd

# Lead discovery imports
try:
    from lead_discovery import (
        discover_leads_from_google_places,
        discover_leads_from_job_boards,
        convert_company_lead_to_review_lead,
        CompanyLead,
        check_website_for_avionte,  # Backward compatibility - now checks subdomain
        check_avionte_subdomain,
        scrape_company_website
    )
    LEAD_DISCOVERY_AVAILABLE = True
except ImportError as e:
    LEAD_DISCOVERY_AVAILABLE = False
    print(f"Lead discovery not available: {e}")

# Enhanced lead discovery imports
try:
    from enhanced_lead_discovery import (
        discover_leads_from_reddit,
        discover_leads_from_subdomain_check,
        discover_leads_from_news,
        discover_leads_from_directories,
        discover_leads_comprehensive,
        discover_leads_from_indeed_reviews,
        discover_leads_from_linkedin_reviews,
        search_reddit_posts,
        check_avionte_subdomain
    )
    ENHANCED_DISCOVERY_AVAILABLE = True
except ImportError as e:
    ENHANCED_DISCOVERY_AVAILABLE = False
    print(f"Enhanced discovery not available: {e}")

# Playwright imports
import sys
PLAYWRIGHT_AVAILABLE = False
PLAYWRIGHT_DISABLED_REASON = None
sync_playwright = None  # Will be None if not available

# Check Python version - Playwright has issues with Python 3.13+ on Windows
if sys.version_info >= (3, 13):
    PLAYWRIGHT_DISABLED_REASON = "Python 3.13+ has compatibility issues with Playwright on Windows"
    # Don't even try to import on Python 3.13+
else:
    try:
        from playwright.sync_api import sync_playwright
        PLAYWRIGHT_AVAILABLE = True
    except ImportError:
        PLAYWRIGHT_DISABLED_REASON = "Playwright not installed. Run: pip install playwright && playwright install chromium"
        sync_playwright = None

# Show info if Playwright is disabled (only in Streamlit context)
# Note: Playwright is optional - the app works fine without it
if not PLAYWRIGHT_AVAILABLE and PLAYWRIGHT_DISABLED_REASON:
    try:
        st.info(f"ℹ️  Playwright is optional. The app uses the `requests` library by default. Some JavaScript-heavy sites may not work without Playwright.")
    except:
        # Not in Streamlit context, just print
        pass

# Load .env only for local development (not needed for Streamlit Cloud)
# Streamlit Cloud uses st.secrets instead
try:
    load_dotenv()
except:
    pass  # .env file is optional

# Page config
st.set_page_config(
    page_title="Chevre - Lead Generator",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database setup - use relative path for Streamlit Cloud compatibility
DATABASE = os.path.join(os.path.dirname(__file__), 'leads.db')

def get_db():
    """Get database connection"""
    db = sqlite3.connect(DATABASE, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize the database with leads table"""
    db = get_db()
    # Check if reviewer_name column exists, if not add it
    try:
        db.execute('SELECT reviewer_name FROM leads LIMIT 1')
    except sqlite3.OperationalError:
        db.execute('ALTER TABLE leads ADD COLUMN reviewer_name TEXT')
        db.commit()
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT,
            reviewer_name TEXT,
            review_title TEXT,
            review_text TEXT,
            rating REAL,
            pain_tags TEXT,
            source_url TEXT,
            scraped_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            unique_hash TEXT UNIQUE,
            lead_score REAL DEFAULT 0,
            status TEXT DEFAULT 'new',
            notes TEXT,
            contacted_at TEXT,
            converted_at TEXT
        )
    ''')
    
    # Add new columns if they don't exist
    try:
        db.execute('SELECT lead_score FROM leads LIMIT 1')
    except sqlite3.OperationalError:
        db.execute('ALTER TABLE leads ADD COLUMN lead_score REAL DEFAULT 0')
        db.execute('ALTER TABLE leads ADD COLUMN status TEXT DEFAULT "new"')
        db.execute('ALTER TABLE leads ADD COLUMN notes TEXT')
        db.execute('ALTER TABLE leads ADD COLUMN contacted_at TEXT')
        db.execute('ALTER TABLE leads ADD COLUMN converted_at TEXT')
        db.commit()
    
    # Create indexes
    db.execute('CREATE INDEX IF NOT EXISTS idx_company_name ON leads(company_name)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_pain_tags ON leads(pain_tags)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_scraped_at ON leads(scraped_at)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_lead_score ON leads(lead_score)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_status ON leads(status)')
    db.commit()
    db.close()

def generate_lead_hash(lead) -> str:
    """Generate a unique hash for a lead to prevent duplicates"""
    content = f"{lead.reviewer_name}|{lead.company_name}|{lead.review_text[:200]}|{lead.source_url}"
    return hashlib.md5(content.encode()).hexdigest()

def save_leads_to_db(leads: List) -> tuple[int, int]:
    """Save leads to database, skipping duplicates. Returns: (saved_count, duplicate_count)"""
    if not leads:
        return (0, 0)
    
    db = get_db()
    saved = 0
    duplicates = 0
    
    for lead in leads:
        try:
            unique_hash = generate_lead_hash(lead)
            lead_score = calculate_lead_score(lead)
            db.execute('''
                INSERT INTO leads (company_name, reviewer_name, review_title, review_text, rating, 
                                 pain_tags, source_url, scraped_at, unique_hash, lead_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lead.company_name,
                lead.reviewer_name,
                lead.review_title,
                lead.review_text,
                lead.rating,
                lead.pain_tags,
                lead.source_url,
                lead.scraped_at,
                unique_hash,
                lead_score,
                lead.status
            ))
            saved += 1
        except sqlite3.IntegrityError:
            duplicates += 1
        except Exception as e:
            st.error(f"Error saving lead: {e}")
    
    db.commit()
    db.close()
    return (saved, duplicates)

def get_all_leads_from_db(limit: int = 1000, pain_filter: Optional[str] = None, 
                          status_filter: Optional[str] = None, min_score: Optional[float] = None,
                          sort_by: str = 'lead_score') -> List[dict]:
    """Retrieve all leads from database with advanced filtering"""
    db = get_db()
    
    conditions = []
    params = []
    
    if pain_filter:
        conditions.append("pain_tags LIKE ?")
        params.append(f'%{pain_filter}%')
    
    if status_filter:
        conditions.append("status = ?")
        params.append(status_filter)
    
    if min_score is not None:
        conditions.append("lead_score >= ?")
        params.append(min_score)
    
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    sort_options = {
        'lead_score': 'lead_score DESC',
        'rating': 'rating ASC',
        'recent': 'scraped_at DESC',
        'company': 'company_name ASC'
    }
    order_by = sort_options.get(sort_by, 'lead_score DESC')
    
    query = f'''
        SELECT * FROM leads 
        {where_clause}
        ORDER BY {order_by}
        LIMIT ?
    '''
    params.append(limit)
    
    leads = db.execute(query, tuple(params)).fetchall()
    db.close()
    return [dict(lead) for lead in leads]

def get_leads_count() -> dict:
    """Get statistics about stored leads"""
    db = get_db()
    total = db.execute('SELECT COUNT(*) as count FROM leads').fetchone()['count']
    by_pain = db.execute('''
        SELECT pain_tags, COUNT(*) as count 
        FROM leads 
        GROUP BY pain_tags 
        ORDER BY count DESC
    ''').fetchall()
    db.close()
    return {
        'total': total,
        'by_pain': {row['pain_tags']: row['count'] for row in by_pain}
    }

def update_lead_status(lead_id: int, status: str, notes: str = None):
    """Update lead status and notes"""
    db = get_db()
    if notes:
        db.execute('UPDATE leads SET status = ?, notes = ? WHERE id = ?', (status, notes, lead_id))
    else:
        db.execute('UPDATE leads SET status = ? WHERE id = ?', (status, lead_id))
    
    if status == 'contacted':
        db.execute('UPDATE leads SET contacted_at = ? WHERE id = ?', 
                  (datetime.now().strftime("%Y-%m-%d %H:%M"), lead_id))
    elif status == 'converted':
        db.execute('UPDATE leads SET converted_at = ? WHERE id = ?', 
                  (datetime.now().strftime("%Y-%m-%d %H:%M"), lead_id))
    
    db.commit()
    db.close()

def get_lead_analytics() -> dict:
    """Get comprehensive analytics about leads"""
    db = get_db()
    
    total = db.execute('SELECT COUNT(*) as count FROM leads').fetchone()['count']
    by_status = db.execute('''
        SELECT status, COUNT(*) as count 
        FROM leads 
        GROUP BY status
    ''').fetchall()
    
    avg_score = db.execute('SELECT AVG(lead_score) as avg FROM leads').fetchone()['avg'] or 0
    high_value = db.execute('SELECT COUNT(*) as count FROM leads WHERE lead_score >= 70').fetchone()['count']
    
    by_pain = db.execute('''
        SELECT pain_tags, COUNT(*) as count 
        FROM leads 
        GROUP BY pain_tags 
        ORDER BY count DESC
        LIMIT 10
    ''').fetchall()
    
    by_source = db.execute('''
        SELECT 
            CASE 
                WHEN source_url LIKE '%g2.com%' THEN 'G2'
                WHEN source_url LIKE '%getapp.com%' THEN 'GetApp'
                WHEN source_url LIKE '%trustradius.com%' THEN 'TrustRadius'
                WHEN source_url LIKE '%softwareadvice.com%' THEN 'Software Advice'
                ELSE 'Other'
            END as source,
            COUNT(*) as count
        FROM leads
        GROUP BY source
        ORDER BY count DESC
    ''').fetchall()
    
    db.close()
    
    return {
        'total': total,
        'by_status': {row['status']: row['count'] for row in by_status},
        'avg_score': round(avg_score, 1),
        'high_value_leads': high_value,
        'by_pain': {row['pain_tags']: row['count'] for row in by_pain},
        'by_source': {row['source']: row['count'] for row in by_source}
    }

# Playwright browser management
_playwright_lock = threading.Lock()
_playwright_instances = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

NEGATIVE_KEYWORDS = {
    "complexity": ["complex", "complicated", "confusing", "hard to use", "difficult"],
    "bugs": ["buggy", "crash", "error", "issue", "downtime", "glitch"],
    "support": ["support", "service", "helpdesk", "customer service", "response time"],
    "integration": ["integration", "integrate", "api", "sync", "doesn't connect"],
    "cost": ["expensive", "too costly", "price", "pricing", "overpriced"],
    "performance": ["slow", "laggy", "performance", "takes forever"],
}

MIN_BAD_RATING = 3.0

@dataclass
class LeadReview:
    company_name: str
    reviewer_name: str
    review_title: str
    review_text: str
    rating: Optional[float]
    pain_tags: str
    source_url: str
    scraped_at: str = None
    lead_score: float = 0.0
    status: str = 'new'
    notes: str = ''

def get_playwright_context():
    """Get or create Playwright browser context for current thread"""
    thread_id = threading.get_ident()
    
    # Early exit if Playwright is disabled
    if not PLAYWRIGHT_AVAILABLE:
        reason = PLAYWRIGHT_DISABLED_REASON or "Playwright not available"
        raise RuntimeError(f"Playwright not available: {reason}")
    
    if thread_id in _playwright_instances:
        return _playwright_instances[thread_id]['context']
    
    with _playwright_lock:
        if thread_id in _playwright_instances:
            return _playwright_instances[thread_id]['context']
        
        # Check if we've already failed to initialize Playwright in this session
        if hasattr(get_playwright_context, '_playwright_failed'):
            raise RuntimeError("Playwright not available in this environment (previous initialization failed)")
        
        try:
            # Double-check Playwright is available before trying to use it
            if not PLAYWRIGHT_AVAILABLE or sync_playwright is None:
                reason = PLAYWRIGHT_DISABLED_REASON or "Playwright not available"
                get_playwright_context._playwright_failed = True
                raise RuntimeError(f"Playwright not available: {reason}")
            
            # Try to start Playwright - wrap in try-except to catch all errors
            playwright = None
            playwright_manager = None
            
            # Double-check sync_playwright is available before calling
            if sync_playwright is None:
                get_playwright_context._playwright_failed = True
                raise RuntimeError("Playwright not available: sync_playwright is None")
            
            try:
                playwright_manager = sync_playwright()
                # This is where NotImplementedError can occur on Python 3.13+
                # Even if we're not on 3.13+, catch it just in case
                playwright = playwright_manager.start()
            except NotImplementedError:
                # Mark as failed immediately to prevent future attempts
                get_playwright_context._playwright_failed = True
                # Convert to RuntimeError to prevent unhandled future exceptions
                raise RuntimeError("Playwright not available: Python 3.13+ compatibility issue with asyncio subprocess") from None
            except Exception as e:
                # Mark as failed for any other error
                get_playwright_context._playwright_failed = True
                raise RuntimeError(f"Playwright initialization failed: {type(e).__name__}: {e}") from None
            
            try:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/New_York',
                )
                context.set_extra_http_headers({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                })
                
                _playwright_instances[thread_id] = {
                    'playwright': playwright,
                    'browser': browser,
                    'context': context
                }
                
                return context
            except Exception as e:
                # If browser launch fails, try to clean up
                if playwright:
                    try:
                        playwright.stop()
                    except:
                        pass
                get_playwright_context._playwright_failed = True
                raise RuntimeError(f"Playwright browser launch failed: {type(e).__name__}: {e}") from None
        except RuntimeError:
            # Re-raise RuntimeError (our converted errors)
            raise
        except Exception as e:
            # Catch any other exception and convert to RuntimeError
            get_playwright_context._playwright_failed = True
            raise RuntimeError(f"Playwright error: {type(e).__name__}: {e}") from None

def fetch_html_with_playwright(url: str) -> str:
    """Fetch HTML using Playwright (handles JavaScript rendering)"""
    page = None
    try:
        # Get context - this will raise RuntimeError if Playwright is not available
        context = get_playwright_context()
        page = context.new_page()
        
        with st.spinner("🌐 Loading page with Playwright (JavaScript enabled)..."):
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
            except Exception as e:
                try:
                    page.goto(url, wait_until='load', timeout=60000)
                except:
                    page.goto(url, timeout=60000)
            
            page_content = page.content()
            if 'cf-browser-verification' in page_content or 'challenge-platform' in page_content or 'Just a moment' in page_content or len(page_content) < 10000:
                max_wait = 30
                waited = 0
                progress_bar = st.progress(0)
                while waited < max_wait:
                    time.sleep(2)
                    waited += 2
                    current_content = page.content()
                    if len(current_content) > 50000 and 'cf-browser-verification' not in current_content:
                        break
                    progress_bar.progress(waited / max_wait)
                progress_bar.empty()
                time.sleep(3)
            
            time.sleep(3)
            
            if 'getapp.com' in url:
                try:
                    page.wait_for_selector('div[class*="review"], article[class*="review"]', timeout=10000)
                except:
                    pass
            
            # Scroll to load dynamic content
            if 'getapp.com' in url:
                for scroll in range(5):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
                    try:
                        load_more = page.query_selector('button:has-text("Load more"), button:has-text("Show more")')
                        if load_more:
                            load_more.click()
                            time.sleep(2)
                    except:
                        pass
            elif 'g2.com' in url or 'trustradius.com' in url:
                for scroll in range(4):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
            else:
                for i in range(5):
                    page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i/4})")
                    time.sleep(1.5)
            
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            
            html = page.content()
            return html
    except RuntimeError:
        # Re-raise RuntimeError (already converted)
        raise
    except Exception as e:
        # Convert any other exception to RuntimeError
        raise RuntimeError(f"Playwright error: {e}") from e
    finally:
        if page:
            try:
                page.close()
            except:
                pass

def fetch_html(url: str, use_playwright: bool = False) -> str:
    """Fetch HTML from URL. Tries requests first, falls back to Playwright if blocked."""
    # Check for Capterra - explicitly forbidden
    if 'capterra.com' in url or 'capterra.ca' in url:
        raise ValueError(
            "❌ Capterra explicitly forbids automated scraping in their terms of service.\n\n"
            "Please use other review sites like:\n"
            "• G2.com\n"
            "• GetApp.com\n"
            "• TrustRadius.com\n"
            "• SoftwareAdvice.com"
        )
    
    # Sites that typically need Playwright
    needs_playwright = any(domain in url for domain in ['g2.com', 'getapp.com', 'trustradius.com', 'softwareadvice.com'])
    
    # Try Playwright first for sites that need it
    if use_playwright or needs_playwright:
        if PLAYWRIGHT_AVAILABLE:
            try:
                return fetch_html_with_playwright(url)
            except RuntimeError as e:
                # Playwright not available or failed - silently fall through to requests
                # Don't show error here, it will be handled in scrape_review_pages
                pass
            except Exception:
                # Other Playwright errors, fall through to requests
                pass
    
    # Try requests
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        if 'g2.com' in url:
            session.headers['Referer'] = 'https://www.g2.com/'
        elif 'getapp.com' in url:
            session.headers['Referer'] = 'https://www.getapp.com/'
        
        resp = session.get(url, timeout=20, allow_redirects=True)
        
        if resp.status_code == 403:
            # If we get 403 and haven't tried Playwright yet, try it
            if needs_playwright and PLAYWRIGHT_AVAILABLE:
                try:
                    return fetch_html_with_playwright(url)
                except (RuntimeError, NotImplementedError):
                    raise requests.RequestException(
                        f"403 Forbidden - {url} is blocking automated access.\n"
                        "Playwright is not available in this environment.\n"
                        "Try using the 'Website Checker' tab in 'Discover Leads' instead."
                    )
            else:
                raise requests.RequestException(
                    f"403 Forbidden - {url} is blocking automated access.\n"
                    "This site may require JavaScript rendering (Playwright) or may block scrapers."
                )
        
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        # If requests fails and we haven't tried Playwright, try it
        if needs_playwright and PLAYWRIGHT_AVAILABLE and "403" not in str(e):
            try:
                return fetch_html_with_playwright(url)
            except (RuntimeError, NotImplementedError):
                # Re-raise original error
                pass
        raise

def classify_pains(text: str) -> List[str]:
    text_l = text.lower()
    tags = []
    for tag, keywords in NEGATIVE_KEYWORDS.items():
        if any(k in text_l for k in keywords):
            tags.append(tag)
    return tags

def is_negative_review(text: str, rating: Optional[float]) -> bool:
    if rating is not None and rating <= MIN_BAD_RATING:
        return True
    return len(classify_pains(text)) > 0

def calculate_lead_score(lead: LeadReview) -> float:
    """Calculate lead score based on multiple factors. Returns score from 0-100."""
    score = 0.0
    
    if lead.rating is not None:
        if lead.rating <= 1.0:
            score += 30
        elif lead.rating <= 2.0:
            score += 25
        elif lead.rating <= 2.5:
            score += 20
        elif lead.rating <= 3.0:
            score += 15
        else:
            score += 5
    
    pain_count = len(lead.pain_tags.split(',')) if lead.pain_tags else 0
    if pain_count >= 3:
        score += 40
    elif pain_count == 2:
        score += 30
    elif pain_count == 1:
        score += 20
    
    high_value_pains = ['complexity', 'bugs', 'performance']
    for pain in high_value_pains:
        if pain in lead.pain_tags.lower():
            score += 7
    
    text_length = len(lead.review_text)
    if text_length > 300:
        score += 10
    elif text_length > 150:
        score += 5
    
    if lead.company_name and lead.company_name.lower() not in ['unknown', 'n/a', '']:
        score += 5
    
    if lead.reviewer_name and lead.reviewer_name.lower() not in ['unknown', 'n/a', '']:
        score += 5
    
    return min(score, 100.0)

def parse_getapp_reviews(html: str, source_url: str) -> List[LeadReview]:
    """Parse GetApp reviews - site-specific parser"""
    soup = BeautifulSoup(html, "html.parser")
    leads: List[LeadReview] = []
    
    review_selectors = [
        "div[data-testid*='review']",
        ".review-item",
        ".review-card",
        "[class*='ReviewCard']",
        "[class*='review-card']",
        "div[class*='review']",
    ]
    
    cards = []
    for selector in review_selectors:
        found = soup.select(selector)
        if found:
            cards = found
            break
    
    if not cards:
        all_divs = soup.find_all('div', class_=lambda x: x and ('review' in x.lower() or 'rating' in x.lower() or 'comment' in x.lower()))
        if all_divs:
            cards = all_divs
    
    for card in cards[:200]:
        text = ""
        text_el = card.find(['p', 'div', 'span'], class_=lambda x: x and ('text' in x.lower() or 'content' in x.lower() or 'body' in x.lower() or 'description' in x.lower() or 'review' in x.lower()))
        if text_el:
            text = text_el.get_text(" ", strip=True)
        
        if len(text) < 20:
            all_text = card.get_text(" ", strip=True)
            paragraphs = [p.strip() for p in all_text.split('\n') if len(p.strip()) > 30]
            rating_pattern = re.compile(r'^\d+\.?\d*\s*\(?\d*\)?')
            meaningful_paragraphs = [p for p in paragraphs if not rating_pattern.match(p) and not re.match(r'^[A-Z][a-z]+\s+\d+\.?\d*', p)]
            if meaningful_paragraphs:
                text = max(meaningful_paragraphs, key=len)
        
        if len(text) < 20:
            for p in card.find_all(['p', 'div', 'span']):
                p_text = p.get_text(" ", strip=True)
                rating_pattern = re.compile(r'^\d+\.?\d*\s*\(?\d*\)?')
                if rating_pattern.match(p_text) or re.match(r'^[A-Z][a-z]+\s+\d+\.?\d*', p_text):
                    continue
                if len(p_text) > 50 and len(p_text) < 2000:
                    if any(word in p_text.lower() for word in ['the', 'and', 'is', 'was', 'are', 'have', 'has', 'this', 'that', 'with', 'for', 'from']):
                        text = p_text
                        break
        
        if len(text) < 20:
            continue
        
        rating = None
        rating_el = card.find(['span', 'div'], class_=lambda x: x and ('rating' in x.lower() or 'star' in x.lower()))
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            rating_match = re.search(r'(\d+\.?\d*)', rating_text)
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                except:
                    pass
        
        reviewer_name = ""
        company = ""
        
        author_el = card.find(['span', 'div', 'a', 'p'], attrs={'itemprop': 'author'}) or \
                   card.find(['span', 'div', 'a'], class_=lambda x: x and 'author' in x.lower())
        if author_el:
            reviewer_name = author_el.get_text(strip=True)
        
        if not reviewer_name:
            profile_links = card.find_all('a', href=re.compile(r'(user|profile|reviewer|author)', re.I))
            for link in profile_links:
                link_text = link.get_text(strip=True)
                if 2 <= len(link_text) <= 50 and re.search(r'[a-zA-Z]', link_text) and not re.match(r'^\d+$', link_text):
                    if link_text.lower() not in ['view', 'more', 'read', 'see', 'profile', 'review', 'author']:
                        reviewer_name = link_text
                        break
        
        if not reviewer_name:
            name_selectors = [
                lambda x: x and ('reviewer' in x.lower() and 'name' in x.lower()),
                lambda x: x and ('user' in x.lower() and 'name' in x.lower()),
                lambda x: x and ('author' in x.lower() and 'name' in x.lower()),
            ]
            for selector in name_selectors:
                name_el = card.find(['span', 'div', 'a', 'strong', 'b', 'p'], class_=selector)
                if name_el:
                    name_text = name_el.get_text(strip=True)
                    name_text = re.sub(r'^(reviewed|written|posted)\s+by\s*:?\s*', '', name_text, flags=re.I)
                    if 2 <= len(name_text) <= 100 and name_text.lower() not in ['unknown', 'anonymous', 'n/a']:
                        reviewer_name = name_text
                        break
        
        if not reviewer_name:
            card_text = card.get_text()
            patterns = [
                r'(?:reviewed|written|posted)\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                r'by\s*:?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            ]
            for pattern in patterns:
                match = re.search(pattern, card_text, re.IGNORECASE)
                if match:
                    potential_name = match.group(1).strip()
                    if 2 <= len(potential_name) <= 100:
                        reviewer_name = potential_name
                        break
        
        company_selectors = [
            lambda x: x and ('company' in x.lower() and 'name' in x.lower()),
            lambda x: x and ('organization' in x.lower()),
        ]
        for selector in company_selectors:
            company_el = card.find(['span', 'div', 'a'], class_=selector)
            if company_el:
                company = company_el.get_text(strip=True)
                if len(company) > 2 and len(company) < 200:
                    break
        
        if not company:
            company_el = card.find(['span', 'div', 'a'], class_=lambda x: x and 'company' in x.lower())
            if company_el:
                company = company_el.get_text(strip=True)
        
        title_el = card.find(['h3', 'h4', 'h5', 'div'], class_=lambda x: x and 'title' in x.lower())
        title = title_el.get_text(strip=True) if title_el else ""
        
        if not is_negative_review(text, rating):
            continue
        
        pains = classify_pains(text)
        lead = LeadReview(
            company_name=company or "Unknown",
            reviewer_name=reviewer_name or "Unknown",
            review_title=title[:100] or text[:50],
            review_text=text[:500],
            rating=rating,
            pain_tags=",".join(pains),
            source_url=source_url,
            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        lead.lead_score = calculate_lead_score(lead)
        leads.append(lead)
    
    return leads

def parse_g2_reviews(html: str, source_url: str) -> List[LeadReview]:
    """Parse G2 reviews - site-specific parser"""
    soup = BeautifulSoup(html, "html.parser")
    leads: List[LeadReview] = []
    
    review_selectors = [
        "div[data-testid*='review']",
        ".review-card",
        "[class*='ReviewCard']",
        "article[class*='review']",
    ]
    
    cards = []
    for selector in review_selectors:
        found = soup.select(selector)
        if found:
            cards = found
            break
    
    if not cards:
        return leads
    
    for card in cards[:200]:
        text_el = card.find(['p', 'div'], class_=lambda x: x and ('text' in x.lower() or 'content' in x.lower()))
        text = text_el.get_text(" ", strip=True) if text_el else ""
        if len(text) < 20:
            continue
        
        rating = None
        rating_el = card.find(['span', 'div'], class_=lambda x: x and ('rating' in x.lower() or 'star' in x.lower()))
        if rating_el:
            rating_match = re.search(r'(\d+\.?\d*)', rating_el.get_text())
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                except:
                    pass
        
        reviewer_name = ""
        company = ""
        
        reviewer_el = card.find(['span', 'div', 'a'], class_=lambda x: x and ('reviewer' in x.lower() or 'author' in x.lower()))
        if reviewer_el:
            reviewer_name = reviewer_el.get_text(strip=True)
        
        company_el = card.find(['span', 'div'], class_=lambda x: x and 'company' in x.lower())
        if company_el:
            company = company_el.get_text(strip=True)
        
        if not reviewer_name:
            reviewer_el = card.find(attrs={'itemprop': 'author'}) or \
                         card.find(attrs={'data-reviewer': True})
            if reviewer_el:
                reviewer_name = reviewer_el.get_text(strip=True) or \
                               reviewer_el.get('data-reviewer', '')
        
        title_el = card.find(['h3', 'h4'], class_=lambda x: x and 'title' in x.lower())
        title = title_el.get_text(strip=True) if title_el else ""
        
        if not is_negative_review(text, rating):
            continue
        
        pains = classify_pains(text)
        lead = LeadReview(
            company_name=company or "Unknown",
            reviewer_name=reviewer_name or "Unknown",
            review_title=title[:100] or text[:50],
            review_text=text[:500],
            rating=rating,
            pain_tags=",".join(pains),
            source_url=source_url,
            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        lead.lead_score = calculate_lead_score(lead)
        leads.append(lead)
    
    return leads

def parse_trustradius_reviews(html: str, source_url: str) -> List[LeadReview]:
    """Parse TrustRadius reviews - site-specific parser"""
    soup = BeautifulSoup(html, "html.parser")
    leads: List[LeadReview] = []
    
    review_selectors = [
        ".review-card",
        ".review-item",
        "article[class*='review']",
        "div[class*='ReviewCard']",
        "[data-review-id]",
    ]
    
    cards = []
    for selector in review_selectors:
        found = soup.select(selector)
        if found:
            cards = found
            break
    
    if not cards:
        cards = soup.find_all('div', attrs={'data-review-id': True})
    
    for card in cards[:200]:
        text_el = card.find(['p', 'div'], class_=lambda x: x and ('text' in x.lower() or 'content' in x.lower() or 'body' in x.lower() or 'review' in x.lower()))
        text = text_el.get_text(" ", strip=True) if text_el else ""
        
        if len(text) < 20:
            text_el = card.find(attrs={'itemprop': 'reviewBody'})
            if text_el:
                text = text_el.get_text(" ", strip=True)
        
        if len(text) < 20:
            continue
        
        rating = None
        rating_el = card.find(attrs={'itemprop': 'ratingValue'}) or \
                   card.find(['span', 'div'], class_=lambda x: x and ('rating' in x.lower() or 'star' in x.lower()))
        if rating_el:
            value = rating_el.get('content') or rating_el.get('data-rating') or rating_el.get_text(strip=True)
            rating_match = re.search(r'(\d+\.?\d*)', str(value))
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                except:
                    pass
        
        reviewer_name = ""
        reviewer_el = card.find(attrs={'itemprop': 'author'}) or \
                     card.find(['span', 'div', 'a'], class_=lambda x: x and ('reviewer' in x.lower() or 'author' in x.lower()))
        if reviewer_el:
            reviewer_name = reviewer_el.get_text(strip=True)
        
        company = ""
        company_el = card.find(['span', 'div'], class_=lambda x: x and 'company' in x.lower())
        if company_el:
            company = company_el.get_text(strip=True)
        
        title_el = card.find(['h3', 'h4', 'h5'], class_=lambda x: x and 'title' in x.lower())
        title = title_el.get_text(strip=True) if title_el else ""
        
        if not is_negative_review(text, rating):
            continue
        
        pains = classify_pains(text)
        lead = LeadReview(
            company_name=company or "Unknown",
            reviewer_name=reviewer_name or "Unknown",
            review_title=title[:100] or text[:50],
            review_text=text[:500],
            rating=rating,
            pain_tags=",".join(pains),
            source_url=source_url,
            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        lead.lead_score = calculate_lead_score(lead)
        leads.append(lead)
    
    return leads

def parse_softwareadvice_reviews(html: str, source_url: str) -> List[LeadReview]:
    """Parse Software Advice reviews - site-specific parser"""
    soup = BeautifulSoup(html, "html.parser")
    leads: List[LeadReview] = []
    
    review_selectors = [
        ".review-card",
        ".review-item",
        "article.review",
        "div[class*='review']",
        "[data-review]",
    ]
    
    cards = []
    for selector in review_selectors:
        found = soup.select(selector)
        if found:
            cards = found
            break
    
    if not cards:
        cards = soup.find_all('div', class_=lambda x: x and ('review' in x.lower() or 'rating' in x.lower()))
    
    for card in cards[:200]:
        text_el = card.find(['p', 'div'], class_=lambda x: x and ('text' in x.lower() or 'content' in x.lower() or 'body' in x.lower()))
        text = text_el.get_text(" ", strip=True) if text_el else ""
        
        if len(text) < 20:
            continue
        
        rating = None
        rating_el = card.find(['span', 'div'], class_=lambda x: x and ('rating' in x.lower() or 'star' in x.lower()))
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            rating_match = re.search(r'(\d+\.?\d*)', rating_text)
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                except:
                    pass
        
        reviewer_name = ""
        reviewer_el = card.find(['span', 'div', 'a'], class_=lambda x: x and ('reviewer' in x.lower() or 'author' in x.lower() or 'user' in x.lower()))
        if reviewer_el:
            reviewer_name = reviewer_el.get_text(strip=True)
        
        company = ""
        company_el = card.find(['span', 'div'], class_=lambda x: x and 'company' in x.lower())
        if company_el:
            company = company_el.get_text(strip=True)
        
        title_el = card.find(['h3', 'h4', 'h5'], class_=lambda x: x and 'title' in x.lower())
        title = title_el.get_text(strip=True) if title_el else ""
        
        if not is_negative_review(text, rating):
            continue
        
        pains = classify_pains(text)
        lead = LeadReview(
            company_name=company or "Unknown",
            reviewer_name=reviewer_name or "Unknown",
            review_title=title[:100] or text[:50],
            review_text=text[:500],
            rating=rating,
            pain_tags=",".join(pains),
            source_url=source_url,
            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        lead.lead_score = calculate_lead_score(lead)
        leads.append(lead)
    
    return leads

def parse_reviews_generic(html: str, source_url: str) -> List[LeadReview]:
    soup = BeautifulSoup(html, "html.parser")
    leads: List[LeadReview] = []
    
    if 'getapp.com' in source_url:
        return parse_getapp_reviews(html, source_url)
    elif 'g2.com' in source_url:
        return parse_g2_reviews(html, source_url)
    elif 'trustradius.com' in source_url:
        return parse_trustradius_reviews(html, source_url)
    elif 'softwareadvice.com' in source_url:
        return parse_softwareadvice_reviews(html, source_url)
    
    selectors = [
        ".review-card, .review-item, article.review, [data-review]",
        "[class*='review']",
        "[id*='review']",
        "article",
        ".review",
    ]
    
    cards = []
    for selector in selectors:
        found = soup.select(selector)
        if found and len(found) > 0:
            cards = found
            break
    
    if not cards:
        return leads
    
    for card in cards:
        title_el = card.select_one(".review-title, h3, h4, .title, [class*='title']")
        title = title_el.get_text(strip=True) if title_el else ""
        
        text_el = card.select_one(".review-body, .review-text, [itemprop='reviewBody'], p, [class*='text'], [class*='body']")
        text = text_el.get_text(" ", strip=True) if text_el else ""
        if len(text) < 20:
            continue
            
        rating = None
        rating_el = card.select_one("[itemprop='ratingValue'], .star-rating, .rating, [class*='rating'], [class*='star']")
        if rating_el:
            value = rating_el.get("content") or rating_el.get("data-rating") or rating_el.get_text(strip=True)
            try:
                rating = float(value)
            except (TypeError, ValueError):
                pass

        reviewer_name = ""
        company = ""
        
        reviewer_el = card.find(attrs={'itemprop': 'author'}) or \
                     card.find(attrs={'data-reviewer': True}) or \
                     card.find(attrs={'data-author': True})
        if reviewer_el:
            reviewer_name = reviewer_el.get_text(strip=True) or \
                           reviewer_el.get('data-reviewer') or \
                           reviewer_el.get('data-author', '')
        
        if not reviewer_name:
            reviewer_el = card.select_one(".reviewer-name, .author-name, .user-name, [class*='reviewer-name'], [class*='author-name']")
            if reviewer_el:
                reviewer_name = reviewer_el.get_text(strip=True)
        
        company_el = card.select_one(".reviewer-company, .company-name, [class*='company-name'], [class*='reviewer-company']")
        if company_el:
            company = company_el.get_text(strip=True)
        
        if not company:
            company_el = card.select_one("[class*='company'], [class*='organization']")
            if company_el:
                company = company_el.get_text(strip=True)

        if not is_negative_review(text, rating):
            continue

        pains = classify_pains(text)
        lead = LeadReview(
            company_name=company or "Unknown",
            reviewer_name=reviewer_name or "Unknown",
            review_title=title[:100],
            review_text=text[:500],
            rating=rating,
            pain_tags=",".join(pains),
            source_url=source_url,
            scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        lead.lead_score = calculate_lead_score(lead)
        leads.append(lead)
    
    return leads

def scrape_review_pages(urls: List[str], max_pages: int = 3) -> List[LeadReview]:
    """Scrape review pages with pagination support."""
    all_leads: List[LeadReview] = []
    errors = []
    playwright_warning_shown = False
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, url in enumerate(urls):
        try:
            status_text.text(f"🌐 Scraping {idx+1}/{len(urls)}: {url}")
            progress_bar.progress((idx) / len(urls))
            
            # Check for Capterra first
            if 'capterra.com' in url or 'capterra.ca' in url:
                errors.append(f"{url}: ❌ Capterra explicitly forbids automated scraping. Please use other review sites (G2, GetApp, TrustRadius, SoftwareAdvice).")
                continue
            
            pages_to_scrape = [url]
            base_url = url.split('?')[0]
            if 'g2.com' in url or 'trustradius.com' in url or 'getapp.com' in url:
                for page in range(2, max_pages + 1):
                    pages_to_scrape.append(f"{base_url}?page={page}")
            
            for page_url in pages_to_scrape:
                try:
                    html = fetch_html(page_url)
                    leads = parse_reviews_generic(html, page_url)
                    all_leads.extend(leads)
                    
                    if len(leads) == 0 and page_url != url:
                        break
                    
                    time.sleep(2)
                except ValueError as e:
                    # Capterra or other validation errors
                    if 'capterra' in str(e).lower():
                        errors.append(f"{url}: {str(e)}")
                        break
                    raise
                except Exception as e:
                    if page_url != url:
                        break
                    else:
                        raise
        except ValueError as e:
            # Validation errors (like Capterra)
            errors.append(f"{url}: {str(e)}")
        except requests.RequestException as e:
            error_msg = str(e)
            if "403" in error_msg or "Forbidden" in error_msg:
                # Provide helpful guidance for 403 errors
                site_name = url.split('/')[2] if '/' in url else url
                if "Playwright not available" in error_msg:
                    if not playwright_warning_shown:
                        st.info(
                            "ℹ️ **Playwright is optional** - The app works without it using the `requests` library.\n\n"
                            "**If you need JavaScript rendering:**\n"
                            "1. Install: `pip install playwright && playwright install chromium`\n"
                            "2. Use Python 3.11/3.12 (3.13+ has compatibility issues)\n\n"
                            "**Alternative:** Try different review sites or use the 'Website Checker' tab for manual checking."
                        )
                        playwright_warning_shown = True
                    errors.append(f"{url}: Blocked (403) - Site requires JavaScript rendering. Try a different site or install Playwright (optional).")
                else:
                    errors.append(
                        f"{url}: Blocked (403 Forbidden) - {site_name} is blocking automated access.\n"
                        f"💡 **Tip:** This site may require JavaScript rendering or may block scrapers.\n"
                        f"   Try: (1) Different review sites that allow scraping, (2) Manual checking via 'Website Checker' tab, or (3) Install Playwright for JavaScript rendering (optional)"
                    )
            else:
                errors.append(f"{url}: {error_msg}")
        except RuntimeError as e:
            # Playwright errors
            if "Playwright not available" in str(e) and not playwright_warning_shown:
                st.warning(
                    "⚠️ **Playwright not available** - This is a known issue on Windows with Python 3.13+.\n\n"
                    "**Solutions:**\n"
                    "1. The app will try using requests library (may not work for JavaScript-heavy sites)\n"
                    "2. Try: `playwright install chromium`\n"
                    "3. Use Python 3.11/3.12 instead of 3.13+\n"
                    "4. Use the 'Website Checker' tab in 'Discover Leads' for manual checking"
                )
                playwright_warning_shown = True
            errors.append(f"{url}: {str(e)}")
        except Exception as e:
            errors.append(f"{url}: {str(e)}")
    
    progress_bar.progress(1.0)
    status_text.text("✅ Scraping complete!")
    
    scrape_review_pages.last_errors = errors
    return all_leads

# Streamlit UI
def main():
    # Initialize database (only once)
    if 'db_initialized' not in st.session_state:
        init_db()
        st.session_state.db_initialized = True
    st.title("🚀 Chevre - Lead Generator")
    
    # Load target indicators configuration
    try:
        from lead_config import (
            TargetIndicator, DEFAULT_INDICATORS, load_indicators_from_file,
            save_indicators_to_file, get_indicator_by_name
        )
        CONFIG_AVAILABLE = True
        current_indicators = load_indicators_from_file()
        if not current_indicators:
            current_indicators = DEFAULT_INDICATORS
    except ImportError:
        CONFIG_AVAILABLE = False
        current_indicators = []
        st.sidebar.error("⚠️ Configuration module not available")
    
    # Sidebar navigation
    page = st.sidebar.selectbox("Navigation", [
        "⚙️ Configure Targets",
        "🔍 Scrape Reviews", 
        "🌐 Discover Leads", 
        "🚀 Advanced Discovery",
        "📊 View Leads", 
        "📈 Analytics"
    ])
    
    if page == "⚙️ Configure Targets":
        st.header("⚙️ Configure Target Software/Indicators")
        st.markdown("Configure which software or indicators to search for when generating leads.")
        
        if not CONFIG_AVAILABLE:
            st.error("Configuration module not available. Please ensure lead_config.py exists.")
        else:
            st.subheader("Current Target Indicators")
            
            if current_indicators:
                for idx, indicator in enumerate(current_indicators):
                    with st.expander(f"📌 {indicator.name}", expanded=False):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_name = st.text_input("Name", value=indicator.name, key=f"name_{idx}")
                            subdomain = st.text_input("Subdomain Pattern", value=indicator.subdomain_pattern or "", 
                                                     placeholder="*.myavionte.com", key=f"subdomain_{idx}")
                            keywords = st.text_area("Keywords (one per line)", 
                                                   value="\n".join(indicator.keywords), 
                                                   key=f"keywords_{idx}")
                        with col2:
                            link_patterns = st.text_area("Link Patterns (one per line)", 
                                                        value="\n".join(indicator.link_patterns), 
                                                        key=f"links_{idx}")
                        
                        if st.button(f"💾 Update {indicator.name}", key=f"update_{idx}"):
                            indicator.name = new_name
                            indicator.subdomain_pattern = subdomain if subdomain else None
                            indicator.keywords = [k.strip() for k in keywords.split('\n') if k.strip()]
                            indicator.link_patterns = [l.strip() for l in link_patterns.split('\n') if l.strip()]
                            save_indicators_to_file(current_indicators)
                            st.success(f"✅ Updated {indicator.name}")
                            st.rerun()
                        
                        if st.button(f"🗑️ Delete {indicator.name}", key=f"delete_{idx}"):
                            current_indicators.pop(idx)
                            save_indicators_to_file(current_indicators)
                            st.success(f"✅ Deleted {indicator.name}")
                            st.rerun()
            else:
                st.info("No indicators configured. Add one below.")
            
            st.subheader("Add New Indicator")
            with st.form("add_indicator"):
                new_name = st.text_input("Name", placeholder="e.g., Avionté, Mindscope")
                new_subdomain = st.text_input("Subdomain Pattern", placeholder="*.myavionte.com")
                new_keywords = st.text_area("Keywords (one per line)", placeholder="avionte\navionté")
                new_links = st.text_area("Link Patterns (one per line)", placeholder="avionte.com\nmyavionte.com")
                
                if st.form_submit_button("➕ Add Indicator"):
                    if new_name:
                        new_indicator = TargetIndicator(
                            name=new_name,
                            subdomain_pattern=new_subdomain if new_subdomain else None,
                            keywords=[k.strip() for k in new_keywords.split('\n') if k.strip()],
                            link_patterns=[l.strip() for l in new_links.split('\n') if l.strip()]
                        )
                        current_indicators.append(new_indicator)
                        save_indicators_to_file(current_indicators)
                        st.success(f"✅ Added {new_name}")
                        st.rerun()
    
    elif page == "🔍 Scrape Reviews":
        st.header("🔍 Scrape Reviews")
        st.markdown("Find negative reviews about target software (Bullhorn, Mindscope, Avionté, etc.) from multiple sources.")
        
        # Tabs for different review sources
        tab1, tab2, tab3 = st.tabs(["📄 Review Sites", "💼 Indeed Reviews", "💼 LinkedIn Reviews"])
        
        with tab1:
            st.subheader("Review Sites (G2, GetApp, TrustRadius, etc.)")
            st.markdown("Enter review page URLs (one per line) containing reviews. Only use sites where scraping is allowed by their terms.")
            st.info("✅ **Recommended sites:** G2.com, GetApp.com, TrustRadius.com, SoftwareAdvice.com\n\n❌ **Do NOT use:** Capterra.com (explicitly forbids automation)")
            
            urls_text = st.text_area(
                "Review Page URLs:",
                height=150,
                placeholder="https://www.getapp.com/hr-employee-management-software/a/avionte/\nhttps://g2.com/products/avionte-staffing-and-payroll/reviews",
                key="review_urls"
            )
            
            if st.button("🔍 Find Target Software Users", type="primary", key="scrape_reviews"):
                urls = [url.strip() for url in urls_text.split('\n') if url.strip()]
                
                if not urls:
                    st.error("Please enter at least one review URL")
                else:
                    try:
                        leads = scrape_review_pages(urls)
                        
                        if leads:
                            saved, duplicates = save_leads_to_db(leads)
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.success(f"✅ Found {len(leads)} negative reviews!")
                                st.info(f"💾 Saved {saved} new leads to database")
                            with col2:
                                if duplicates > 0:
                                    st.warning(f"⚠️ Skipped {duplicates} duplicate leads")
                            
                            if hasattr(scrape_review_pages, 'last_errors') and scrape_review_pages.last_errors:
                                st.error("Errors encountered:")
                                for error in scrape_review_pages.last_errors:
                                    st.error(f"  • {error}")
                            
                            st.subheader("📋 Scraped Leads")
                            df = pd.DataFrame([{
                                'Score': f"{lead.lead_score:.1f}",
                                'Reviewer': lead.reviewer_name,
                                'Company': lead.company_name,
                                'Rating': lead.rating or 'N/A',
                                'Pain Tags': lead.pain_tags,
                                'Title': lead.review_title[:60] + '...' if len(lead.review_title) > 60 else lead.review_title,
                                'Source': lead.source_url
                            } for lead in leads])
                            st.dataframe(df, width='stretch', hide_index=True)
                        else:
                            st.warning("No negative reviews found. This could mean: (1) The pages use JavaScript to load content, (2) The CSS selectors don't match the page structure, or (3) There are no negative reviews matching the criteria.")
                            
                            if hasattr(scrape_review_pages, 'last_errors') and scrape_review_pages.last_errors:
                                st.error("Errors encountered:")
                                for error in scrape_review_pages.last_errors:
                                    st.error(f"  • {error}")
                    except Exception as e:
                        st.error(f"Error during scraping: {str(e)}")
        
        with tab2:
            st.subheader("💼 Indeed Company Reviews")
            st.markdown("Search Indeed company reviews for negative mentions of target software (Bullhorn, Mindscope, Avionté, etc.)")
            
            if not ENHANCED_DISCOVERY_AVAILABLE:
                st.error("Enhanced discovery module not available")
            else:
                max_indeed = st.number_input("Max Results per Indicator:", min_value=1, max_value=100, value=50, key="max_indeed")
                
                if st.button("🔍 Search Indeed Reviews", type="primary", key="indeed_reviews"):
                    with st.spinner("🔍 Searching Indeed for bad reviews..."):
                        try:
                            company_leads = discover_leads_from_indeed_reviews(current_indicators, max_indeed)
                            
                            if company_leads:
                                # Convert to LeadReview format
                                review_leads = []
                                for company_lead in company_leads:
                                    if company_lead.has_any_indicator():
                                        review_lead = convert_company_lead_to_review_lead(
                                            company_lead, LeadReview, calculate_lead_score
                                        )
                                        if review_lead:
                                            review_leads.append(review_lead)
                                
                                if review_leads:
                                    saved, duplicates = save_leads_to_db(review_leads)
                                    
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.success(f"✅ Found {len(review_leads)} negative reviews on Indeed!")
                                        st.info(f"💾 Saved {saved} new leads")
                                    with col2:
                                        if duplicates > 0:
                                            st.warning(f"⚠️ Skipped {duplicates} duplicates")
                                    
                                    st.subheader("📋 Discovered Leads from Indeed")
                                    df = pd.DataFrame([{
                                        'Score': f"{lead.lead_score:.1f}",
                                        'Company': lead.company_name,
                                        'Review Title': lead.review_title[:60] + '...' if len(lead.review_title) > 60 else lead.review_title,
                                        'Source': lead.source_url
                                    } for lead in review_leads])
                                    st.dataframe(df, width='stretch', hide_index=True)
                                else:
                                    st.warning(f"Found {len(company_leads)} companies, but none had negative reviews mentioning target software.")
                            else:
                                st.info("No negative reviews found on Indeed. Try adjusting your target indicators or search criteria.")
                        except Exception as e:
                            st.error(f"Error searching Indeed reviews: {str(e)}")
        
        with tab3:
            st.subheader("💼 LinkedIn Reviews & Posts")
            st.markdown("Search LinkedIn posts/comments for negative mentions of target software")
            st.info("⚠️ Note: LinkedIn has strict anti-scraping measures. Results may be limited without API access.")
            
            if not ENHANCED_DISCOVERY_AVAILABLE:
                st.error("Enhanced discovery module not available")
            else:
                max_linkedin = st.number_input("Max Results per Indicator:", min_value=1, max_value=50, value=25, key="max_linkedin")
                
                if st.button("🔍 Search LinkedIn", type="primary", key="linkedin_reviews"):
                    with st.spinner("🔍 Searching LinkedIn for negative mentions..."):
                        try:
                            company_leads = discover_leads_from_linkedin_reviews(current_indicators, max_linkedin)
                            
                            if company_leads:
                                # Convert to LeadReview format
                                review_leads = []
                                for company_lead in company_leads:
                                    if company_lead.has_any_indicator():
                                        review_lead = convert_company_lead_to_review_lead(
                                            company_lead, LeadReview, calculate_lead_score
                                        )
                                        if review_lead:
                                            review_leads.append(review_lead)
                                
                                if review_leads:
                                    saved, duplicates = save_leads_to_db(review_leads)
                                    
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.success(f"✅ Found {len(review_leads)} negative mentions on LinkedIn!")
                                        st.info(f"💾 Saved {saved} new leads")
                                    with col2:
                                        if duplicates > 0:
                                            st.warning(f"⚠️ Skipped {duplicates} duplicates")
                                    
                                    st.subheader("📋 Discovered Leads from LinkedIn")
                                    df = pd.DataFrame([{
                                        'Score': f"{lead.lead_score:.1f}",
                                        'Company': lead.company_name,
                                        'Review Title': lead.review_title[:60] + '...' if len(lead.review_title) > 60 else lead.review_title,
                                        'Source': lead.source_url
                                    } for lead in review_leads])
                                    st.dataframe(df, width='stretch', hide_index=True)
                                else:
                                    st.warning(f"Found {len(company_leads)} companies, but none had negative mentions.")
                            else:
                                st.info("No negative mentions found on LinkedIn. LinkedIn requires authentication for most content.")
                        except Exception as e:
                            st.error(f"Error searching LinkedIn: {str(e)}")
    
    elif page == "🌐 Discover Leads":
        st.header("🌐 Multi-Source Lead Discovery")
        st.markdown("Discover potential target software users from Google Places, job boards, and company websites.")
        
        if not LEAD_DISCOVERY_AVAILABLE:
            st.error("⚠️ Lead discovery module not available. Please ensure all dependencies are installed.")
            st.code("pip install googlemaps")
        else:
            tab1, tab2, tab3 = st.tabs(["📍 Google Places", "💼 Job Boards", "🔍 Website Checker"])
            
            with tab1:
                st.subheader("📍 Discover from Google Places")
                st.markdown("Search Google Places for businesses and check for target software indicators (subdomains, links, keywords).")
                
                col1, col2 = st.columns(2)
                with col1:
                    search_queries = st.text_area(
                        "Search Queries (one per line):",
                        height=100,
                        value="staffing agency\ntemporary staffing\nemployment agency\nrecruiting firm",
                        help="Enter search queries to find staffing agencies"
                    )
                    location = st.text_input("Location:", value="United States")
                
                with col2:
                    # Try Streamlit secrets first (for Streamlit Cloud), then env var (for local dev)
                    default_key = ''
                    try:
                        default_key = st.secrets.get('GOOGLE_PLACES_API_KEY', '')
                    except:
                        # Not in Streamlit Cloud, try environment variable for local dev
                        default_key = os.getenv('GOOGLE_PLACES_API_KEY', '')
                    
                    google_api_key = st.text_input(
                        "Google Places API Key:",
                        type="password",
                        value=default_key,
                        help="Get your API key from Google Cloud Console. For Streamlit Cloud, add it in Secrets."
                    )
                    max_results = st.number_input("Max Results per Query:", min_value=1, max_value=50, value=20)
                    check_websites = st.checkbox("Check for target software indicators (subdomains, links)", value=True)
                
                if st.button("🔍 Discover from Google Places", type="primary"):
                    if not google_api_key:
                        st.error("Please enter a Google Places API key")
                    else:
                        queries = [q.strip() for q in search_queries.split('\n') if q.strip()]
                        if not queries:
                            st.error("Please enter at least one search query")
                        else:
                            with st.spinner("🔍 Discovering leads from Google Places..."):
                                try:
                                    company_leads = discover_leads_from_google_places(
                                        queries,
                                        location,
                                        check_websites,
                                        google_api_key
                                    )
                                except ValueError as e:
                                    # Billing or API configuration error
                                    st.error(str(e))
                                    st.stop()
                                except Exception as e:
                                    st.error(f"Error during discovery: {str(e)}")
                                    st.stop()
                                
                                if company_leads:
                                    # Convert to LeadReview format
                                    review_leads = []
                                    for company_lead in company_leads:
                                        if company_lead.has_any_indicator():
                                            review_lead = convert_company_lead_to_review_lead(
                                                company_lead, LeadReview, calculate_lead_score
                                            )
                                            if review_lead:
                                                review_leads.append(review_lead)
                                    
                                    if review_leads:
                                        saved, duplicates = save_leads_to_db(review_leads)
                                        
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.success(f"✅ Found {len(review_leads)} companies using target software!")
                                            st.info(f"💾 Saved {saved} new leads")
                                        with col2:
                                            if duplicates > 0:
                                                st.warning(f"⚠️ Skipped {duplicates} duplicates")
                                        
                                        # Show results
                                        st.subheader("📋 Discovered Leads")
                                        
                                        # Get indicator evidence for display
                                        indicator_evidence = {}
                                        for i, lead in enumerate(review_leads):
                                            company_lead = company_leads[i]
                                            # Find first indicator with evidence
                                            evidence_text = 'N/A'
                                            for indicator_name, has_indicator in company_lead.target_indicators.items():
                                                if has_indicator and indicator_name in company_lead.indicator_evidence:
                                                    evidence = company_lead.indicator_evidence[indicator_name]
                                                    if evidence:
                                                        evidence_text = evidence[:100] + '...' if len(evidence) > 100 else evidence
                                                        break
                                            indicator_evidence[i] = evidence_text
                                        
                                        df = pd.DataFrame([{
                                            'Company': lead.company_name,
                                            'Website': company_leads[i].website or 'N/A',
                                            'Phone': company_leads[i].phone or 'N/A',
                                            'Target Found': '✅' if company_leads[i].has_any_indicator() else '❌',
                                            'Indicator Evidence': indicator_evidence.get(i, 'N/A'),
                                            'Score': f"{lead.lead_score:.1f}"
                                        } for i, lead in enumerate(review_leads)])
                                        st.dataframe(df, width='stretch', hide_index=True)
                                    else:
                                        st.warning(f"Found {len(company_leads)} companies, but none matched your target indicators.")
                                        
                                        # Show all companies found
                                        st.subheader("📋 All Companies Found")
                                        df = pd.DataFrame([{
                                            'Company': lead.company_name,
                                            'Website': lead.website or 'N/A',
                                            'Address': lead.address or 'N/A',
                                            'Phone': lead.phone or 'N/A'
                                        } for lead in company_leads])
                                        st.dataframe(df, width='stretch', hide_index=True)
                                else:
                                    st.warning("No companies found. Try different search queries or check your API key.")
            
            with tab2:
                st.subheader("💼 Discover from Job Boards")
                st.markdown("Search job postings for companies using target software.")
                
                col1, col2 = st.columns(2)
                with col1:
                    job_queries = st.text_area(
                        "Search Queries (one per line):",
                        height=100,
                        value="staffing software\nrecruiting software\nATS software",
                        help="Search for job postings mentioning target software"
                    )
                    job_location = st.text_input("Location:", value="United States", key="job_location")
                
                with col2:
                    max_job_results = st.number_input("Max Results per Query:", min_value=1, max_value=100, value=50, key="max_job")
                
                if st.button("🔍 Discover from Job Boards", type="primary"):
                    queries = [q.strip() for q in job_queries.split('\n') if q.strip()]
                    if not queries:
                        st.error("Please enter at least one search query")
                    else:
                        with st.spinner("🔍 Searching job boards..."):
                            try:
                                company_leads = discover_leads_from_job_boards(queries, job_location)
                                
                                if company_leads:
                                    # Convert to LeadReview format
                                    review_leads = []
                                    for company_lead in company_leads:
                                        review_lead = convert_company_lead_to_review_lead(
                                            company_lead, LeadReview, calculate_lead_score
                                        )
                                        if review_lead:
                                            review_leads.append(review_lead)
                                    
                                    if review_leads:
                                        saved, duplicates = save_leads_to_db(review_leads)
                                        
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.success(f"✅ Found {len(review_leads)} companies using target software!")
                                            st.info(f"💾 Saved {saved} new leads")
                                        with col2:
                                            if duplicates > 0:
                                                st.warning(f"⚠️ Skipped {duplicates} duplicates")
                                        
                                        st.subheader("📋 Discovered Leads")
                                        df = pd.DataFrame([{
                                            'Company': lead.company_name,
                                            'Job Posting': company_leads[i].description or 'N/A',
                                            'Evidence': (company_leads[i].indicator_evidence.get(list(company_leads[i].target_indicators.keys())[0], 'N/A') if company_leads[i].has_any_indicator() and company_leads[i].indicator_evidence else 'N/A'),
                                            'Score': f"{lead.lead_score:.1f}"
                                        } for i, lead in enumerate(review_leads)])
                                        st.dataframe(df, width='stretch', hide_index=True)
                                    else:
                                        st.warning("No companies found using target software in job postings.")
                                else:
                                    st.info("No results found. Try different search queries.")
                            except Exception as e:
                                st.error(f"Error during job board search: {str(e)}")
            
            with tab3:
                st.subheader("🔍 Check Websites for Target Indicators")
                st.markdown("Enter company domains to check for target software indicators (subdomains, links, keywords).")
                st.info("💡 **Tip:** Enter company domains (e.g., 'company.com') - the app will check configured indicators")
                
                website_urls = st.text_area(
                    "Website URLs (one per line):",
                    height=150,
                    placeholder="primlogix.com\nexample-staffing.com\nhttps://another-agency.com"
                )
                
                if st.button("🔍 Check Websites", type="primary"):
                    urls = [url.strip() for url in website_urls.split('\n') if url.strip()]
                    if not urls:
                        st.error("Please enter at least one website URL")
                    else:
                        results = []
                        progress_bar = st.progress(0)
                        
                        status_text = st.empty()
                        for idx, url in enumerate(urls):
                            progress_bar.progress((idx + 1) / len(urls))
                            status_text.text(f"Checking {idx+1}/{len(urls)}: {url}")
                            
                            try:
                                # Normalize URL (add https:// if missing)
                                normalized_url = url.strip()
                                if not normalized_url.startswith(('http://', 'https://')):
                                    normalized_url = 'https://' + normalized_url
                                
                                # Check for Avionté subdomain
                                from urllib.parse import urlparse
                                parsed = urlparse(normalized_url)
                                domain = parsed.netloc.replace('www.', '')
                                # Check for all configured indicators
                                from lead_config import load_indicators_from_file, check_subdomain_for_indicator
                                indicators = load_indicators_from_file()
                                if not indicators:
                                    from lead_config import DEFAULT_INDICATORS
                                    indicators = DEFAULT_INDICATORS
                                
                                indicator_found = False
                                found_indicator_name = None
                                found_subdomain_url = None
                                
                                for indicator in indicators:
                                    found, subdomain_url = check_subdomain_for_indicator(domain, indicator)
                                    if found:
                                        indicator_found = True
                                        found_indicator_name = indicator.name
                                        found_subdomain_url = subdomain_url
                                        break
                                
                                avionte_found = indicator_found
                                subdomain_url = found_subdomain_url
                                
                                website_data = scrape_company_website(normalized_url)
                                
                                results.append({
                                    'URL': normalized_url,
                                    'Target Found': '✅' if avionte_found else '❌',
                                    'Subdomain URL': subdomain_url[:200] + '...' if subdomain_url and len(subdomain_url) > 200 else (subdomain_url or 'N/A'),
                                    'Email': website_data.get('email') if website_data and website_data.get('email') else 'N/A',
                                    'Phone': website_data.get('phone') if website_data and website_data.get('phone') else 'N/A'
                                })
                            except Exception as e:
                                # If there's an error, still add the result with error info
                                results.append({
                                    'URL': url,
                                    'Target Found': '❌',
                                    'Subdomain URL': f"Error: {str(e)[:100]}",
                                    'Email': 'N/A',
                                    'Phone': 'N/A'
                                })
                            
                            time.sleep(1)  # Rate limiting
                        
                        status_text.empty()
                        
                        progress_bar.empty()
                        
                        # Show results
                        df = pd.DataFrame(results)
                        st.dataframe(df, width='stretch', hide_index=True)
                        
                        # Create leads for companies with confirmed target indicators
                        avionte_leads = [r for r in results if r['Target Found'] == '✅']
                        if avionte_leads:
                            if st.button("💾 Save Target Software Users as Leads"):
                                review_leads = []
                                for result in avionte_leads:
                                    # Extract company name from URL
                                    from urllib.parse import urlparse
                                    domain = urlparse(result['URL']).netloc.replace('www.', '')
                                    company_name = domain.split('.')[0].title()
                                    
                                    lead = LeadReview(
                                        company_name=company_name,
                                        reviewer_name="Website Check",
                                        review_title=f"Target Software User: {company_name}",
                                        review_text=f"Confirmed target software user via indicator check. Evidence: {result['Subdomain URL']}",
                                        rating=None,
                                        pain_tags="discovery",
                                        source_url=result['URL'],
                                        scraped_at=datetime.now().strftime("%Y-%m-%d %H:%M")
                                    )
                                    lead.lead_score = calculate_lead_score(lead)
                                    review_leads.append(lead)
                                
                                saved, duplicates = save_leads_to_db(review_leads)
                                st.success(f"💾 Saved {saved} new leads!")
                                if duplicates > 0:
                                    st.warning(f"⚠️ Skipped {duplicates} duplicates")
    
    elif page == "🚀 Advanced Discovery":
        st.header("🚀 Advanced Multi-Source Lead Discovery")
        st.markdown("Discover leads from Reddit, news articles, industry directories, subdomain checking, and more.")
        
        if not ENHANCED_DISCOVERY_AVAILABLE:
            st.error("⚠️ Enhanced discovery module not available. Please ensure all dependencies are installed.")
        else:
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📱 Reddit", 
                "📰 News & Articles", 
                "📞 Directories", 
                "🔗 Subdomain Checker",
                "🌐 All Sources"
            ])
            
            with tab1:
                st.subheader("📱 Discover from Reddit")
                st.markdown("Search Reddit for discussions about target software in relevant communities.")
                
                col1, col2 = st.columns(2)
                with col1:
                    reddit_queries = st.text_area(
                        "Search Queries (one per line):",
                        height=100,
                        value="staffing software\nrecruiting software\nsoftware alternatives",
                        help="Search terms to find in Reddit posts"
                    )
                    reddit_subreddits = st.text_area(
                        "Subreddits (one per line):",
                        height=80,
                        value="recruiting\nstaffing\nhrtech\nhumanresources",
                        help="Subreddits to search"
                    )
                
                with col2:
                    max_reddit = st.number_input("Max Results per Subreddit:", min_value=1, max_value=100, value=25)
                
                if st.button("🔍 Discover from Reddit", type="primary"):
                    queries = [q.strip() for q in reddit_queries.split('\n') if q.strip()]
                    subs = [s.strip() for s in reddit_subreddits.split('\n') if s.strip()]
                    
                    if not queries or not subs:
                        st.error("Please enter at least one query and one subreddit")
                    else:
                        with st.spinner("🔍 Searching Reddit..."):
                            try:
                                company_leads = discover_leads_from_reddit(queries, subs, max_reddit)
                                
                                if company_leads:
                                    review_leads = []
                                    for company_lead in company_leads:
                                        review_lead = convert_company_lead_to_review_lead(
                                            company_lead, LeadReview, calculate_lead_score
                                        )
                                        if review_lead:
                                            review_leads.append(review_lead)
                                    
                                    if review_leads:
                                        saved, duplicates = save_leads_to_db(review_leads)
                                        
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.success(f"✅ Found {len(review_leads)} leads from Reddit!")
                                            st.info(f"💾 Saved {saved} new leads")
                                        with col2:
                                            if duplicates > 0:
                                                st.warning(f"⚠️ Skipped {duplicates} duplicates")
                                        
                                        st.subheader("📋 Discovered Leads")
                                        df = pd.DataFrame([{
                                            'Company': lead.company_name,
                                            'Source': company_leads[i].source,
                                            'Evidence': ((list(company_leads[i].indicator_evidence.values())[0][:100] + '...' if len(list(company_leads[i].indicator_evidence.values())[0]) > 100 else list(company_leads[i].indicator_evidence.values())[0]) if company_leads[i].has_any_indicator() and company_leads[i].indicator_evidence else 'N/A'),
                                            'Score': f"{lead.lead_score:.1f}"
                                        } for i, lead in enumerate(review_leads)])
                                        st.dataframe(df, width='stretch', hide_index=True)
                                    else:
                                        st.info("No leads found mentioning target software in Reddit posts.")
                                else:
                                    st.info("No results found. Try different queries or subreddits.")
                            except Exception as e:
                                st.error(f"Error during Reddit search: {str(e)}")
            
            with tab2:
                st.subheader("📰 Discover from News & Articles")
                st.markdown("Search news articles and blog posts for companies, then check for target software indicators.")
                
                news_queries = st.text_area(
                    "Search Queries (one per line):",
                    height=100,
                    value="staffing software\nrecruiting software\nsoftware review",
                    help="Search terms for news articles"
                )
                max_news = st.number_input("Max Results per Query:", min_value=1, max_value=50, value=20, key="max_news")
                
                if st.button("🔍 Discover from News", type="primary"):
                    queries = [q.strip() for q in news_queries.split('\n') if q.strip()]
                    if not queries:
                        st.error("Please enter at least one search query")
                    else:
                        with st.spinner("🔍 Searching news articles..."):
                            try:
                                company_leads = discover_leads_from_news(queries, max_news)
                                
                                if company_leads:
                                    review_leads = []
                                    for company_lead in company_leads:
                                        review_lead = convert_company_lead_to_review_lead(
                                            company_lead, LeadReview, calculate_lead_score
                                        )
                                        if review_lead:
                                            review_leads.append(review_lead)
                                    
                                    if review_leads:
                                        saved, duplicates = save_leads_to_db(review_leads)
                                        st.success(f"✅ Found {len(review_leads)} leads from news articles!")
                                        st.info(f"💾 Saved {saved} new leads")
                                        
                                        df = pd.DataFrame([{
                                            'Company': lead.company_name,
                                            'Source': company_leads[i].source,
                                            'Description': company_leads[i].description[:80] + '...' if company_leads[i].description and len(company_leads[i].description) > 80 else (company_leads[i].description or 'N/A'),
                                            'Score': f"{lead.lead_score:.1f}"
                                        } for i, lead in enumerate(review_leads)])
                                        st.dataframe(df, width='stretch', hide_index=True)
                                    else:
                                        st.info("No leads found.")
                                else:
                                    st.info("No results found.")
                            except Exception as e:
                                st.error(f"Error during news search: {str(e)}")
            
            with tab3:
                st.subheader("📞 Discover from Industry Directories")
                st.markdown("Search Yellow Pages and industry directories for staffing agencies.")
                
                col1, col2 = st.columns(2)
                with col1:
                    dir_queries = st.text_area(
                        "Search Queries (one per line):",
                        height=100,
                        value="staffing agency\ntemporary staffing\nemployment agency",
                        help="Search terms for directories"
                    )
                with col2:
                    dir_location = st.text_input("Location:", value="United States", key="dir_location")
                    max_dir = st.number_input("Max Results per Query:", min_value=1, max_value=100, value=50, key="max_dir")
                
                if st.button("🔍 Discover from Directories", type="primary"):
                    queries = [q.strip() for q in dir_queries.split('\n') if q.strip()]
                    if not queries:
                        st.error("Please enter at least one search query")
                    else:
                        with st.spinner("🔍 Searching directories..."):
                            try:
                                company_leads = discover_leads_from_directories(queries, dir_location, max_dir)
                                
                                if company_leads:
                                    st.success(f"✅ Found {len(company_leads)} companies!")
                                    st.info("💡 Tip: Use the 'Website Checker' tab to verify which ones use target software")
                                    
                                    df = pd.DataFrame([{
                                        'Company': lead.company_name,
                                        'Website': lead.website or 'N/A',
                                        'Phone': lead.phone or 'N/A',
                                        'Address': lead.address or 'N/A'
                                    } for lead in company_leads])
                                    st.dataframe(df, width='stretch', hide_index=True)
                                    
                                    # Option to check all websites
                                    if st.button("🔍 Check All Websites for Target Indicators"):
                                        checked_leads = []
                                        progress_bar = st.progress(0)
                                        for idx, lead in enumerate(company_leads):
                                            if lead.website:
                                                progress_bar.progress((idx + 1) / len(company_leads))
                                                # Check for all configured indicators
                                                from lead_config import load_indicators_from_file, check_company_for_indicators
                                                indicators = load_indicators_from_file()
                                                if not indicators:
                                                    from lead_config import DEFAULT_INDICATORS
                                                    indicators = DEFAULT_INDICATORS
                                                
                                                company_lead = check_company_for_indicators(lead.company_name, lead.website, indicators)
                                                avionte_found = company_lead.has_any_indicator() if company_lead else False
                                                # Get evidence from first found indicator
                                                evidence = None
                                                if company_lead and avionte_found:
                                                    for indicator_name, has_indicator in company_lead.target_indicators.items():
                                                        if has_indicator and indicator_name in company_lead.indicator_evidence:
                                                            evidence = company_lead.indicator_evidence[indicator_name]
                                                            break
                                                if avionte_found:
                                                    # Update the lead with indicator information
                                                    lead.target_indicators = company_lead.target_indicators
                                                    lead.indicator_evidence = company_lead.indicator_evidence
                                                    checked_leads.append(lead)
                                                time.sleep(1)
                                        progress_bar.empty()
                                        
                                        if checked_leads:
                                            review_leads = []
                                            for company_lead in checked_leads:
                                                review_lead = convert_company_lead_to_review_lead(
                                                    company_lead, LeadReview, calculate_lead_score
                                                )
                                                if review_lead:
                                                    review_leads.append(review_lead)
                                            
                                            if review_leads:
                                                saved, duplicates = save_leads_to_db(review_leads)
                                                st.success(f"💾 Saved {saved} new leads with confirmed target indicators!")
                                else:
                                    st.info("No results found.")
                            except Exception as e:
                                st.error(f"Error during directory search: {str(e)}")
            
            with tab4:
                st.subheader("🔗 Target Software Subdomain Checker")
                st.markdown("Check if companies use target software by verifying configured subdomain patterns.")
                st.info("💡 This confirms active software usage - very high-quality leads!")
                
                company_domains = st.text_area(
                    "Company Domains (one per line):",
                    height=150,
                    placeholder="primlogix.com\nexample-staffing.com\nanother-agency.com",
                    help="Enter company domains to check for target software subdomains"
                )
                
                if st.button("🔍 Check Subdomains", type="primary"):
                    domains = [d.strip() for d in company_domains.split('\n') if d.strip()]
                    if not domains:
                        st.error("Please enter at least one company domain")
                    else:
                        with st.spinner("🔍 Checking for target software subdomains..."):
                            try:
                                company_leads = discover_leads_from_subdomain_check(domains)
                                
                                if company_leads:
                                    st.success(f"✅ Found {len(company_leads)} confirmed target software users!")
                                    
                                    review_leads = []
                                    for company_lead in company_leads:
                                        review_lead = convert_company_lead_to_review_lead(
                                            company_lead, LeadReview, calculate_lead_score
                                        )
                                        if review_lead:
                                            # Subdomain confirmation = very high score
                                            review_lead.lead_score = min(review_lead.lead_score + 30, 100)
                                            review_leads.append(review_lead)
                                    
                                    if review_leads:
                                        saved, duplicates = save_leads_to_db(review_leads)
                                        st.info(f"💾 Saved {saved} new confirmed leads!")
                                        
                                        df = pd.DataFrame([{
                                            'Company': lead.company_name,
                                            'Subdomain URL': company_leads[i].website or 'N/A',
                                            'Evidence': (company_leads[i].indicator_evidence.get(list(company_leads[i].target_indicators.keys())[0], 'N/A') if company_leads[i].has_any_indicator() and company_leads[i].indicator_evidence else 'N/A'),
                                            'Score': f"{lead.lead_score:.1f}"
                                        } for i, lead in enumerate(review_leads)])
                                        st.dataframe(df, width='stretch', hide_index=True)
                                else:
                                    st.info("No target software subdomains found. These companies may not be using the target software.")
                            except Exception as e:
                                st.error(f"Error during subdomain check: {str(e)}")
            
            with tab5:
                st.subheader("🌐 Comprehensive Discovery")
                st.markdown("Run discovery across multiple sources at once.")
                
                st.checkbox("📱 Reddit", value=True, key="comp_reddit")
                st.checkbox("📰 News Articles", value=True, key="comp_news")
                st.checkbox("📞 Industry Directories", value=True, key="comp_dirs")
                st.checkbox("🔗 Subdomain Checker", value=False, key="comp_subdomain")
                st.checkbox("❓ Quora", value=True, key="comp_quora")
                
                if st.button("🚀 Run Comprehensive Discovery", type="primary"):
                    sources = []
                    if st.session_state.comp_reddit:
                        sources.append('reddit')
                    if st.session_state.comp_news:
                        sources.append('news')
                    if st.session_state.comp_dirs:
                        sources.append('directories')
                    if st.session_state.comp_subdomain:
                        sources.append('subdomain')
                    if st.session_state.comp_quora:
                        sources.append('quora')
                    
                    if not sources:
                        st.error("Please select at least one source")
                    else:
                        with st.spinner("🚀 Running comprehensive discovery..."):
                            try:
                                company_leads = discover_leads_comprehensive(sources=sources)
                                
                                if company_leads:
                                    # Filter to only confirmed target indicators
                                    avionte_leads = [l for l in company_leads if l.has_any_indicator()]
                                    
                                    if avionte_leads:
                                        review_leads = []
                                        for company_lead in avionte_leads:
                                            review_lead = convert_company_lead_to_review_lead(
                                                company_lead, LeadReview, calculate_lead_score
                                            )
                                            if review_lead:
                                                review_leads.append(review_lead)
                                        
                                        if review_leads:
                                            saved, duplicates = save_leads_to_db(review_leads)
                                            
                                            st.success(f"✅ Found {len(review_leads)} leads across {len(sources)} sources!")
                                            st.info(f"💾 Saved {saved} new leads")
                                            
                                            # Show breakdown by source
                                            source_counts = {}
                                            for lead in avionte_leads:
                                                source = lead.source
                                                source_counts[source] = source_counts.get(source, 0) + 1
                                            
                                            st.subheader("📊 Results by Source")
                                            for source, count in source_counts.items():
                                                st.write(f"  • {source}: {count} leads")
                                            
                                            df = pd.DataFrame([{
                                                'Company': lead.company_name,
                                                'Source': company_leads[i].source,
                                                'Evidence': ((list(company_leads[i].indicator_evidence.values())[0][:80] + '...' if len(list(company_leads[i].indicator_evidence.values())[0]) > 80 else list(company_leads[i].indicator_evidence.values())[0]) if company_leads[i].has_any_indicator() and company_leads[i].indicator_evidence else 'N/A'),
                                                'Score': f"{lead.lead_score:.1f}"
                                            } for i, lead in enumerate(review_leads)])
                                            st.dataframe(df, width='stretch', hide_index=True)
                                        else:
                                            st.warning(f"Found {len(company_leads)} companies, but none matched your target indicators.")
                                else:
                                    st.info("No results found. Try different sources or queries.")
                            except Exception as e:
                                st.error(f"Error during comprehensive discovery: {str(e)}")
    
    elif page == "📊 View Leads":
        st.header("📊 Stored Leads Database")
        
        # Filters
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            pain_filter = st.selectbox(
                "Pain Tag:",
                ["All"] + list(NEGATIVE_KEYWORDS.keys()),
                key="pain_filter"
            )
            pain_filter = None if pain_filter == "All" else pain_filter
        
        with col2:
            status_filter = st.selectbox(
                "Status:",
                ["All", "new", "contacted", "converted", "lost"],
                key="status_filter"
            )
            status_filter = None if status_filter == "All" else status_filter
        
        with col3:
            min_score = st.number_input("Min Score:", min_value=0, max_value=100, value=0, key="min_score")
            min_score = None if min_score == 0 else float(min_score)
        
        with col4:
            sort_by = st.selectbox(
                "Sort By:",
                ["lead_score", "rating", "recent", "company"],
                format_func=lambda x: {
                    "lead_score": "Score (High→Low)",
                    "rating": "Rating (Low→High)",
                    "recent": "Most Recent",
                    "company": "Company Name"
                }[x],
                key="sort_by"
            )
        
        leads = get_all_leads_from_db(
            limit=1000,
            pain_filter=pain_filter,
            status_filter=status_filter,
            min_score=min_score,
            sort_by=sort_by
        )
        
        stats = get_leads_count()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Leads", stats['total'])
        with col2:
            st.metric("Filtered Results", len(leads))
        with col3:
            if leads:
                avg_score = sum(l.get('lead_score', 0) for l in leads) / len(leads)
                st.metric("Avg Score", f"{avg_score:.1f}")
        
        if leads:
            st.subheader(f"📋 Leads ({len(leads)} results)")
            
            for lead in leads:
                with st.expander(f"Score: {lead.get('lead_score', 0):.1f} | {lead.get('company_name', 'Unknown')} | {lead.get('reviewer_name', 'Unknown')}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Company:** {lead.get('company_name', 'Unknown')}")
                        st.write(f"**Reviewer:** {lead.get('reviewer_name', 'Unknown')}")
                        st.write(f"**Rating:** {lead.get('rating', 'N/A')}")
                        st.write(f"**Pain Tags:** {lead.get('pain_tags', 'None')}")
                    with col2:
                        st.write(f"**Status:** {lead.get('status', 'new')}")
                        st.write(f"**Score:** {lead.get('lead_score', 0):.1f}/100")
                        st.write(f"**Source:** {lead.get('source_url', 'N/A')}")
                        st.write(f"**Scraped:** {lead.get('scraped_at', 'N/A')}")
                    
                    st.write(f"**Title:** {lead.get('review_title', 'N/A')}")
                    st.write(f"**Review:** {lead.get('review_text', 'N/A')}")
                    
                    # Update status form
                    with st.form(f"update_{lead['id']}"):
                        new_status = st.selectbox(
                            "Update Status:",
                            ["new", "contacted", "converted", "lost"],
                            index=["new", "contacted", "converted", "lost"].index(lead.get('status', 'new')),
                            key=f"status_{lead['id']}"
                        )
                        notes = st.text_area("Notes:", value=lead.get('notes', ''), key=f"notes_{lead['id']}")
                        if st.form_submit_button("Update"):
                            update_lead_status(lead['id'], new_status, notes)
                            st.success(f"Lead #{lead['id']} updated!")
                            st.rerun()
        else:
            st.info("No leads found with current filters.")
        
        # Download CSV
        if leads:
            csv_data = io.StringIO()
            writer = csv.writer(csv_data)
            writer.writerow(['Company', 'Reviewer', 'Title', 'Review', 'Rating', 'Pain Tags', 'Score', 'Status', 'Source URL', 'Scraped At'])
            for lead in leads:
                writer.writerow([
                    lead.get('company_name', ''),
                    lead.get('reviewer_name', ''),
                    lead.get('review_title', ''),
                    lead.get('review_text', ''),
                    lead.get('rating', ''),
                    lead.get('pain_tags', ''),
                    lead.get('lead_score', 0),
                    lead.get('status', 'new'),
                    lead.get('source_url', ''),
                    lead.get('scraped_at', '')
                ])
            st.download_button(
                "📥 Download CSV",
                csv_data.getvalue(),
                "leads.csv",
                "text/csv"
            )
    
    elif page == "📈 Analytics":
        st.header("📈 Lead Analytics Dashboard")
        
        analytics = get_lead_analytics()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Leads", analytics['total'])
        with col2:
            st.metric("Avg Score", f"{analytics['avg_score']:.1f}")
        with col3:
            st.metric("High Value Leads", analytics['high_value_leads'])
        with col4:
            new_leads = analytics['by_status'].get('new', 0)
            st.metric("New Leads", new_leads)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Leads by Status")
            if analytics['by_status']:
                status_df = pd.DataFrame(list(analytics['by_status'].items()), columns=['Status', 'Count'])
                st.bar_chart(status_df.set_index('Status'))
            else:
                st.info("No status data available")
        
        with col2:
            st.subheader("Leads by Source")
            if analytics['by_source']:
                source_df = pd.DataFrame(list(analytics['by_source'].items()), columns=['Source', 'Count'])
                st.bar_chart(source_df.set_index('Source'))
            else:
                st.info("No source data available")
        
        st.subheader("Top Pain Tags")
        if analytics['by_pain']:
            pain_df = pd.DataFrame(list(analytics['by_pain'].items()), columns=['Pain Tag', 'Count'])
            st.bar_chart(pain_df.set_index('Pain Tag'))
        else:
            st.info("No pain tag data available")

if __name__ == "__main__":
    main()

