from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import csv
import io
import json
import time
import os
import re
import sqlite3
import hashlib
import threading
import argparse
import sys
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict
from typing import List, Optional
from dotenv import load_dotenv

# Playwright imports
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  Playwright not installed. Run: pip install playwright && playwright install chromium")

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'primlogix-dev-key')

# Database setup
DATABASE = 'leads.db'

def get_db():
    """Get database connection"""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize the database with leads table"""
    db = get_db()
    # Check if reviewer_name column exists, if not add it
    try:
        db.execute('SELECT reviewer_name FROM leads LIMIT 1')
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
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
    
    # Add new columns if they don't exist (for existing databases)
    try:
        db.execute('SELECT lead_score FROM leads LIMIT 1')
    except sqlite3.OperationalError:
        db.execute('ALTER TABLE leads ADD COLUMN lead_score REAL DEFAULT 0')
        db.execute('ALTER TABLE leads ADD COLUMN status TEXT DEFAULT "new"')
        db.execute('ALTER TABLE leads ADD COLUMN notes TEXT')
        db.execute('ALTER TABLE leads ADD COLUMN contacted_at TEXT')
        db.execute('ALTER TABLE leads ADD COLUMN converted_at TEXT')
        db.commit()
    db.execute('''
        CREATE INDEX IF NOT EXISTS idx_company_name ON leads(company_name)
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS idx_pain_tags ON leads(pain_tags)
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS idx_scraped_at ON leads(scraped_at)
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS idx_lead_score ON leads(lead_score)
    ''')
    db.execute('''
        CREATE INDEX IF NOT EXISTS idx_status ON leads(status)
    ''')
    db.commit()
    db.close()

def generate_lead_hash(lead) -> str:
    """Generate a unique hash for a lead to prevent duplicates"""
    # Use reviewer name + company name + review text (first 200 chars) + source URL as unique identifier
    content = f"{lead.reviewer_name}|{lead.company_name}|{lead.review_text[:200]}|{lead.source_url}"
    return hashlib.md5(content.encode()).hexdigest()

def save_leads_to_db(leads: List) -> tuple[int, int]:
    """
    Save leads to database, skipping duplicates.
    Returns: (saved_count, duplicate_count)
    """
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
            # Duplicate lead (same unique_hash)
            duplicates += 1
        except Exception as e:
            print(f"Error saving lead: {e}")
    
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
    
    # Sort options
    sort_options = {
        'lead_score': 'lead_score DESC',
        'rating': 'rating ASC',  # Lower rating = better
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

# Playwright browser management - use thread-local to avoid issues with Flask reloader
_playwright_lock = threading.Lock()
_playwright_instances = {}  # Thread-local storage

# ------------- Same scraper config from before -------------
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
    reviewer_name: str  # Name of the person who wrote the review
    review_title: str
    review_text: str
    rating: Optional[float]
    pain_tags: str
    source_url: str
    scraped_at: str = None
    lead_score: float = 0.0  # Calculated lead score
    status: str = 'new'  # new, contacted, converted, lost
    notes: str = ''

# ------------- Scraper functions (same as before) -------------
def get_playwright_context():
    """Get or create Playwright browser context for current thread"""
    thread_id = threading.get_ident()
    
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError("Playwright is not installed. Install it with: pip install playwright && playwright install chromium")
    
    # Check if we already have a context for this thread
    if thread_id in _playwright_instances:
        return _playwright_instances[thread_id]['context']
    
    # Create new browser instance for this thread
    with _playwright_lock:
        # Double-check after acquiring lock
        if thread_id in _playwright_instances:
            return _playwright_instances[thread_id]['context']
        
        print(f"  🚀 Initializing Playwright browser (thread {thread_id})...")
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']  # Reduce bot detection
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
            )
            # Add extra headers to look more like a real browser
            context.set_extra_http_headers({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            })
            
            # Store for this thread
            _playwright_instances[thread_id] = {
                'playwright': playwright,
                'browser': browser,
                'context': context
            }
            
            return context
        except Exception as e:
            print(f"  ✗ Error initializing Playwright: {e}")
            raise

def fetch_html_with_playwright(url: str) -> str:
    """Fetch HTML using Playwright (handles JavaScript rendering)"""
    page = None
    try:
        context = get_playwright_context()
        page = context.new_page()
        
        print(f"  🌐 Loading page with Playwright (JavaScript enabled)...")
        
        # Try to load the page - use 'domcontentloaded' instead of 'networkidle' 
        # as some sites have continuous network activity
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=60000)
        except Exception as e:
            # If it times out, try with 'load' which is less strict
            print(f"  ⚠️  Initial load timeout, trying with 'load' strategy...")
            try:
                page.goto(url, wait_until='load', timeout=60000)
            except:
                # Last resort - just wait for the page to be accessible
                page.goto(url, timeout=60000)
        
        # Wait for Cloudflare challenge to complete (if present)
        page_content = page.content()
        if 'cf-browser-verification' in page_content or 'challenge-platform' in page_content or 'Just a moment' in page_content or len(page_content) < 10000:
            print(f"  ⏳ Cloudflare challenge detected, waiting for it to complete...")
            # Wait for the challenge to complete - look for the page to actually load
            max_wait = 30  # seconds
            waited = 0
            while waited < max_wait:
                time.sleep(2)
                waited += 2
                current_content = page.content()
                # Check if we've moved past the challenge
                if len(current_content) > 50000 and 'cf-browser-verification' not in current_content:
                    print(f"  ✓ Challenge completed after {waited} seconds")
                    break
                if waited % 5 == 0:
                    print(f"  ⏳ Still waiting... ({waited}s/{max_wait}s)")
            
            # Final wait for any remaining JS to load
            time.sleep(3)
        
        # Wait for page to be fully interactive
        time.sleep(3)
        
        # Wait for review content to load (site-specific)
        if 'getapp.com' in url:
            print(f"  ⏳ Waiting for GetApp reviews to load...")
            try:
                # Wait for review elements to appear
                page.wait_for_selector('div[class*="review"], article[class*="review"]', timeout=10000)
            except:
                pass  # Continue even if selector not found
        
        # Enhanced scrolling to load more reviews
        print(f"  📜 Scrolling to load dynamic content...")
        
        # Site-specific scrolling strategies
        if 'getapp.com' in url:
            # GetApp uses infinite scroll - scroll multiple times
            for scroll in range(5):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
                # Try clicking "Load more" or "Show more reviews" buttons
                try:
                    load_more = page.query_selector('button:has-text("Load more"), button:has-text("Show more"), a:has-text("Load more")')
                    if load_more:
                        load_more.click()
                        time.sleep(2)
                except:
                    pass
        elif 'g2.com' in url:
            # G2 uses pagination and infinite scroll
            for scroll in range(4):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
        elif 'trustradius.com' in url:
            # TrustRadius uses pagination
            for scroll in range(4):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)
        else:
            # Generic scrolling for other sites
            for i in range(5):
                page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {i/4})")
                time.sleep(1.5)
        
        # Final scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(3)
        
        # Scroll back up to trigger any remaining lazy loads
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(1)
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        
        # Get the final HTML
        html = page.content()
        
        print(f"  ✓ Successfully fetched with Playwright ({len(html)} chars)")
        return html
    except Exception as e:
        print(f"  ✗ Playwright error: {str(e)}")
        raise
    finally:
        # Always close the page, but keep context/browser for thread reuse
        if page:
            try:
                page.close()
            except Exception as e:
                print(f"  ⚠️  Error closing page: {e}")

def fetch_html(url: str, use_playwright: bool = False) -> str:
    """
    Fetch HTML from URL. Tries requests first, falls back to Playwright if blocked.
    
    Args:
        url: URL to fetch
        use_playwright: If True, skip requests and use Playwright directly
    """
    # If explicitly requested or if we know the site needs JS, use Playwright
    if use_playwright or any(domain in url for domain in ['g2.com', 'getapp.com', 'capterra.com', 'trustradius.com', 'softwareadvice.com']):
        if PLAYWRIGHT_AVAILABLE:
            return fetch_html_with_playwright(url)
        else:
            print("  ⚠️  Playwright not available, trying requests anyway...")
    
    # Try requests first (faster)
    try:
        session = requests.Session()
        session.headers.update(HEADERS)
        
        # Add referer for more realistic browsing
        if 'g2.com' in url:
            session.headers['Referer'] = 'https://www.g2.com/'
        elif 'getapp.com' in url:
            session.headers['Referer'] = 'https://www.getapp.com/'
        
        resp = session.get(url, timeout=20, allow_redirects=True)
        
        # If we get blocked, try Playwright
        if resp.status_code == 403:
            print(f"  ⚠️  403 Forbidden - Switching to Playwright...")
            if PLAYWRIGHT_AVAILABLE:
                return fetch_html_with_playwright(url)
            else:
                raise requests.RequestException(f"403 Forbidden - Site blocking access and Playwright not available")
        
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        # If requests fails and we haven't tried Playwright yet, try it
        if PLAYWRIGHT_AVAILABLE and "403" not in str(e):
            print(f"  ⚠️  Requests failed ({str(e)}), trying Playwright...")
            return fetch_html_with_playwright(url)
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
    """
    Calculate lead score based on multiple factors.
    Higher score = better lead for Primlogix.
    Returns score from 0-100.
    """
    score = 0.0
    
    # Rating factor (lower rating = higher score, max 30 points)
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
    
    # Pain tags factor (more pain tags = higher score, max 40 points)
    pain_count = len(lead.pain_tags.split(',')) if lead.pain_tags else 0
    if pain_count >= 3:
        score += 40
    elif pain_count == 2:
        score += 30
    elif pain_count == 1:
        score += 20
    
    # Specific high-value pain tags (max 20 points)
    high_value_pains = ['complexity', 'bugs', 'performance']
    for pain in high_value_pains:
        if pain in lead.pain_tags.lower():
            score += 7
    
    # Review text length factor (detailed reviews = more serious, max 10 points)
    text_length = len(lead.review_text)
    if text_length > 300:
        score += 10
    elif text_length > 150:
        score += 5
    
    # Company name factor (if we have company name, it's more actionable, max 5 points)
    if lead.company_name and lead.company_name.lower() not in ['unknown', 'n/a', '']:
        score += 5
    
    # Reviewer name factor (if we have reviewer name, it's more actionable, max 5 points)
    if lead.reviewer_name and lead.reviewer_name.lower() not in ['unknown', 'n/a', '']:
        score += 5
    
    # Cap at 100
    return min(score, 100.0)

def parse_getapp_reviews(html: str, source_url: str) -> List[LeadReview]:
    """Parse GetApp reviews - site-specific parser"""
    soup = BeautifulSoup(html, "html.parser")
    leads: List[LeadReview] = []
    
    # GetApp uses specific classes - try multiple patterns
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
            print(f"  GetApp: Using selector '{selector}' - found {len(cards)} elements")
            break
    
    # If no cards found, try to find any divs with review-like content
    if not cards:
        # Look for divs containing rating stars or review text
        all_divs = soup.find_all('div', class_=lambda x: x and ('review' in x.lower() or 'rating' in x.lower() or 'comment' in x.lower()))
        if all_divs:
            cards = all_divs
            print(f"  GetApp: Found {len(cards)} potential review divs by class search")
    
    for card in cards[:200]:  # Increased limit to get more reviews
        # Try to extract review text - GetApp structure varies
        text = ""
        
        # Method 1: Look for specific review text classes
        text_el = card.find(['p', 'div', 'span'], class_=lambda x: x and ('text' in x.lower() or 'content' in x.lower() or 'body' in x.lower() or 'description' in x.lower() or 'review' in x.lower()))
        if text_el:
            text = text_el.get_text(" ", strip=True)
        
        # Method 2: Get all text from the card and find the longest paragraph
        # But exclude rating/metadata patterns
        if len(text) < 20:
            all_text = card.get_text(" ", strip=True)
            # Split by common separators
            paragraphs = [p.strip() for p in all_text.split('\n') if len(p.strip()) > 30]
            # Filter out rating patterns (e.g., "3.9 (168)", "Value for money 3.6")
            rating_pattern = re.compile(r'^\d+\.?\d*\s*\(?\d*\)?')
            meaningful_paragraphs = [p for p in paragraphs if not rating_pattern.match(p) and not re.match(r'^[A-Z][a-z]+\s+\d+\.?\d*', p)]
            if meaningful_paragraphs:
                text = max(meaningful_paragraphs, key=len)
        
        # Method 3: Find any paragraph with substantial content (not rating metadata)
        if len(text) < 20:
            # Look for text that contains actual sentences (has periods, common words)
            for p in card.find_all(['p', 'div', 'span']):
                p_text = p.get_text(" ", strip=True)
                # Skip if it looks like rating metadata
                if rating_pattern.match(p_text) or re.match(r'^[A-Z][a-z]+\s+\d+\.?\d*', p_text):
                    continue
                # Look for actual review text (has sentences, not just numbers/ratings)
                if len(p_text) > 50 and len(p_text) < 2000:
                    # Check if it has sentence-like structure (contains common words)
                    if any(word in p_text.lower() for word in ['the', 'and', 'is', 'was', 'are', 'have', 'has', 'this', 'that', 'with', 'for', 'from']):
                        text = p_text
                        break
        
        if len(text) < 20:
            continue
        
        # Try to find rating
        rating = None
        rating_el = card.find(['span', 'div'], class_=lambda x: x and ('rating' in x.lower() or 'star' in x.lower()))
        if rating_el:
            rating_text = rating_el.get_text(strip=True)
            # Try to extract number from text like "4.5" or "4 out of 5"
            rating_match = re.search(r'(\d+\.?\d*)', rating_text)
            if rating_match:
                try:
                    rating = float(rating_match.group(1))
                except:
                    pass
        
        # Enhanced extraction for reviewer name and company
        reviewer_name = ""
        company = ""
        
        # Strategy 1: Look for itemprop="author" or similar structured data
        author_el = card.find(['span', 'div', 'a', 'p'], attrs={'itemprop': 'author'}) or \
                   card.find(['span', 'div', 'a'], class_=lambda x: x and 'author' in x.lower())
        if author_el:
            reviewer_name = author_el.get_text(strip=True)
        
        # Strategy 2: Look for links that might contain reviewer names (often in profile links)
        if not reviewer_name:
            # Look for links with href containing "user", "profile", "reviewer", "author"
            profile_links = card.find_all('a', href=re.compile(r'(user|profile|reviewer|author)', re.I))
            for link in profile_links:
                link_text = link.get_text(strip=True)
                # If link text looks like a name (2-50 chars, contains letters, not just numbers)
                if 2 <= len(link_text) <= 50 and re.search(r'[a-zA-Z]', link_text) and not re.match(r'^\d+$', link_text):
                    # Skip common non-name words
                    if link_text.lower() not in ['view', 'more', 'read', 'see', 'profile', 'review', 'author']:
                        reviewer_name = link_text
                        break
        
        # Strategy 3: Look for reviewer/user name classes
        if not reviewer_name:
            name_selectors = [
                lambda x: x and ('reviewer' in x.lower() and 'name' in x.lower()),
                lambda x: x and ('user' in x.lower() and 'name' in x.lower()),
                lambda x: x and ('author' in x.lower() and 'name' in x.lower()),
                lambda x: x and ('profile' in x.lower() and 'name' in x.lower()),
                lambda x: x and ('writer' in x.lower()),
                lambda x: x and ('posted' in x.lower() and 'by' in x.lower()),
            ]
            for selector in name_selectors:
                name_el = card.find(['span', 'div', 'a', 'strong', 'b', 'p'], class_=selector)
                if name_el:
                    name_text = name_el.get_text(strip=True)
                    # Clean up common prefixes like "Reviewed by", "Written by"
                    name_text = re.sub(r'^(reviewed|written|posted)\s+by\s*:?\s*', '', name_text, flags=re.I)
                    if 2 <= len(name_text) <= 100 and name_text.lower() not in ['unknown', 'anonymous', 'n/a']:
                        reviewer_name = name_text
                        break
        
        # Strategy 4: Look for text patterns like "Reviewed by John Doe" or "By: John Doe"
        if not reviewer_name:
            card_text = card.get_text()
            # Pattern: "Reviewed by [Name]" or "By [Name]" or "[Name] reviewed"
            patterns = [
                r'(?:reviewed|written|posted)\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                r'by\s*:?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+reviewed',
            ]
            for pattern in patterns:
                match = re.search(pattern, card_text, re.IGNORECASE)
                if match:
                    potential_name = match.group(1).strip()
                    if 2 <= len(potential_name) <= 100:
                        reviewer_name = potential_name
                        break
        
        # Strategy 3: Look for company name (separate from reviewer)
        company_selectors = [
            lambda x: x and ('company' in x.lower() and 'name' in x.lower()),
            lambda x: x and ('organization' in x.lower()),
            lambda x: x and ('business' in x.lower() and 'name' in x.lower()),
            lambda x: x and ('firm' in x.lower()),
        ]
        for selector in company_selectors:
            company_el = card.find(['span', 'div', 'a'], class_=selector)
            if company_el:
                company = company_el.get_text(strip=True)
                if len(company) > 2 and len(company) < 200:
                    break
        
        # Strategy 4: If no company found, try generic name fields
        if not company:
            company_el = card.find(['span', 'div', 'a'], class_=lambda x: x and 'company' in x.lower())
            if company_el:
                company = company_el.get_text(strip=True)
        
        # Strategy 5: Look for structured data (data attributes, itemprop)
        if not reviewer_name:
            reviewer_el = card.find(attrs={'data-reviewer': True}) or \
                         card.find(attrs={'data-author': True}) or \
                         card.find(attrs={'data-user': True})
            if reviewer_el:
                reviewer_name = reviewer_el.get('data-reviewer') or \
                               reviewer_el.get('data-author') or \
                               reviewer_el.get('data-user') or \
                               reviewer_el.get_text(strip=True)
        
        # Get title if available
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
    
    # G2 uses specific data attributes and classes
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
            print(f"  G2: Using selector '{selector}' - found {len(cards)} elements")
            break
    
    # G2 might load reviews via JS, so we might not find them
    if not cards:
        print(f"  G2: No review cards found. Reviews may be loaded dynamically via JavaScript.")
        return leads
    
    for card in cards[:200]:  # Increased limit to get more reviews
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
        
        # Enhanced extraction for reviewer name and company (G2 specific)
        reviewer_name = ""
        company = ""
        
        # G2 often has reviewer info in specific structures
        reviewer_el = card.find(['span', 'div', 'a'], class_=lambda x: x and ('reviewer' in x.lower() or 'author' in x.lower()))
        if reviewer_el:
            reviewer_name = reviewer_el.get_text(strip=True)
        
        # Look for company name
        company_el = card.find(['span', 'div'], class_=lambda x: x and 'company' in x.lower())
        if company_el:
            company = company_el.get_text(strip=True)
        
        # Try structured data
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
    
    # TrustRadius uses specific classes
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
            print(f"  TrustRadius: Using selector '{selector}' - found {len(cards)} elements")
            break
    
    if not cards:
        # Try finding by data attributes
        cards = soup.find_all('div', attrs={'data-review-id': True})
        if cards:
            print(f"  TrustRadius: Found {len(cards)} reviews by data-review-id")
    
    for card in cards[:200]:
        # Extract review text
        text_el = card.find(['p', 'div'], class_=lambda x: x and ('text' in x.lower() or 'content' in x.lower() or 'body' in x.lower() or 'review' in x.lower()))
        text = text_el.get_text(" ", strip=True) if text_el else ""
        
        # If no text found, try itemprop
        if len(text) < 20:
            text_el = card.find(attrs={'itemprop': 'reviewBody'})
            if text_el:
                text = text_el.get_text(" ", strip=True)
        
        if len(text) < 20:
            continue
        
        # Extract rating
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
        
        # Extract reviewer name
        reviewer_name = ""
        reviewer_el = card.find(attrs={'itemprop': 'author'}) or \
                     card.find(['span', 'div', 'a'], class_=lambda x: x and ('reviewer' in x.lower() or 'author' in x.lower()))
        if reviewer_el:
            reviewer_name = reviewer_el.get_text(strip=True)
        
        # Extract company
        company = ""
        company_el = card.find(['span', 'div'], class_=lambda x: x and 'company' in x.lower())
        if company_el:
            company = company_el.get_text(strip=True)
        
        # Extract title
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
    
    # Software Advice uses specific classes
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
            print(f"  Software Advice: Using selector '{selector}' - found {len(cards)} elements")
            break
    
    if not cards:
        # Try finding reviews by common patterns
        cards = soup.find_all('div', class_=lambda x: x and ('review' in x.lower() or 'rating' in x.lower()))
        if cards:
            print(f"  Software Advice: Found {len(cards)} potential reviews by class search")
    
    for card in cards[:200]:
        # Extract review text
        text_el = card.find(['p', 'div'], class_=lambda x: x and ('text' in x.lower() or 'content' in x.lower() or 'body' in x.lower()))
        text = text_el.get_text(" ", strip=True) if text_el else ""
        
        if len(text) < 20:
            continue
        
        # Extract rating
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
        
        # Extract reviewer name
        reviewer_name = ""
        reviewer_el = card.find(['span', 'div', 'a'], class_=lambda x: x and ('reviewer' in x.lower() or 'author' in x.lower() or 'user' in x.lower()))
        if reviewer_el:
            reviewer_name = reviewer_el.get_text(strip=True)
        
        # Extract company
        company = ""
        company_el = card.find(['span', 'div'], class_=lambda x: x and 'company' in x.lower())
        if company_el:
            company = company_el.get_text(strip=True)
        
        # Extract title
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
    
    # Site-specific parsing
    if 'getapp.com' in source_url:
        return parse_getapp_reviews(html, source_url)
    elif 'g2.com' in source_url:
        return parse_g2_reviews(html, source_url)
    elif 'trustradius.com' in source_url:
        return parse_trustradius_reviews(html, source_url)
    elif 'softwareadvice.com' in source_url:
        return parse_softwareadvice_reviews(html, source_url)
    
    # Generic parsing for other sites
    # Try multiple selector strategies
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
            print(f"  Using selector '{selector}' - found {len(cards)} elements")
            break
    
    if not cards:
        print(f"  ⚠️  No review cards found with any selector. Page might be JavaScript-rendered.")
        print(f"  Sample HTML structure (first 500 chars): {html[:500]}")
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

        # Enhanced extraction for generic sites
        reviewer_name = ""
        company = ""
        
        # Try structured data first
        reviewer_el = card.find(attrs={'itemprop': 'author'}) or \
                     card.find(attrs={'data-reviewer': True}) or \
                     card.find(attrs={'data-author': True})
        if reviewer_el:
            reviewer_name = reviewer_el.get_text(strip=True) or \
                           reviewer_el.get('data-reviewer') or \
                           reviewer_el.get('data-author', '')
        
        # Try class-based selectors
        if not reviewer_name:
            reviewer_el = card.select_one(".reviewer-name, .author-name, .user-name, [class*='reviewer-name'], [class*='author-name']")
            if reviewer_el:
                reviewer_name = reviewer_el.get_text(strip=True)
        
        company_el = card.select_one(".reviewer-company, .company-name, [class*='company-name'], [class*='reviewer-company']")
        if company_el:
            company = company_el.get_text(strip=True)
        
        # If no company found, try generic company selector
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
    """
    Scrape review pages with pagination support.
    
    Args:
        urls: List of URLs to scrape
        max_pages: Maximum number of pages to scrape per URL (for pagination)
    """
    all_leads: List[LeadReview] = []
    debug_info = []
    errors = []
    
    for url in urls:
        try:
            print(f"Scraping {url}")
            pages_to_scrape = [url]
            
            # Check if URL supports pagination and add additional pages
            base_url = url.split('?')[0]  # Remove query params
            if 'g2.com' in url:
                # G2 uses page parameter
                for page in range(2, max_pages + 1):
                    pages_to_scrape.append(f"{base_url}?page={page}")
            elif 'trustradius.com' in url:
                # TrustRadius uses page parameter
                for page in range(2, max_pages + 1):
                    pages_to_scrape.append(f"{base_url}?page={page}")
            elif 'getapp.com' in url:
                # GetApp might have pagination
                for page in range(2, max_pages + 1):
                    pages_to_scrape.append(f"{base_url}?page={page}")
            
            for page_url in pages_to_scrape:
                try:
                    html = fetch_html(page_url)
                    debug_info.append(f"✓ Successfully fetched {page_url} ({len(html)} chars)")
                    
                    leads = parse_reviews_generic(html, page_url)
                    debug_info.append(f"  Parsed {len(leads)} negative reviews from this page")
                    all_leads.extend(leads)
                    
                    # If no leads found on this page, stop pagination
                    if len(leads) == 0 and page_url != url:
                        print(f"  ⚠️  No reviews found on page, stopping pagination")
                        break
                    
                    time.sleep(2)
                except Exception as e:
                    if page_url != url:  # Don't fail on pagination pages
                        print(f"  ⚠️  Error scraping page {page_url}: {e}")
                        break
                    else:
                        raise
        except requests.RequestException as e:
            error_msg = f"✗ Network error scraping {url}: {str(e)}"
            print(error_msg)
            debug_info.append(error_msg)
            # Check if it's a 403 error
            if "403" in str(e) or "Forbidden" in str(e):
                if PLAYWRIGHT_AVAILABLE:
                    errors.append(f"{url}: Still blocked after trying Playwright. The site may have advanced bot protection.")
                else:
                    errors.append(f"{url} is blocking automated requests (403 Forbidden). Install Playwright: pip install playwright && playwright install chromium")
            else:
                errors.append(f"{url}: {str(e)}")
        except Exception as e:
            error_msg = f"✗ Error scraping {url}: {str(e)}"
            print(error_msg)
            debug_info.append(error_msg)
            errors.append(f"{url}: {str(e)}")
    
    # Print debug info
    for info in debug_info:
        print(info)
    
    # Print leads to console
    if all_leads:
        print("\n" + "="*80)
        print(f"📊 FOUND {len(all_leads)} POTENTIAL LEADS")
        print("="*80)
        for i, lead in enumerate(all_leads, 1):
            print(f"\n[{i}] ⭐ Score: {lead.lead_score:.1f}/100")
            print(f"    Reviewer: {lead.reviewer_name or 'Unknown'}")
            print(f"    Company: {lead.company_name or 'Unknown'}")
            print(f"    Rating: {lead.rating if lead.rating else 'N/A'}")
            print(f"    Pain Tags: {lead.pain_tags or 'None'}")
            print(f"    Title: {lead.review_title[:80] if lead.review_title else 'N/A'}...")
            print(f"    Review: {lead.review_text[:150]}...")
            print(f"    Source: {lead.source_url}")
            print(f"    Scraped: {lead.scraped_at}")
            print("-"*80)
        print(f"\n✅ Total: {len(all_leads)} leads found\n")
    else:
        print("\n⚠️  No leads found\n")
    
    # Store errors for display to user
    scrape_review_pages.last_errors = errors
    
    return all_leads

# ------------- Flask routes -------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    urls = [url.strip() for url in request.form['urls'].split('\n') if url.strip()]
    
    if not urls:
        flash('Please enter at least one review URL', 'error')
        return redirect(url_for('index'))
    
    try:
        leads = scrape_review_pages(urls)
        
        # Save leads to database
        if leads:
            saved, duplicates = save_leads_to_db(leads)
            if saved > 0:
                flash(f'Saved {saved} new leads to database', 'success')
            if duplicates > 0:
                flash(f'Skipped {duplicates} duplicate leads', 'info')
        
        # Show errors if any
        if hasattr(scrape_review_pages, 'last_errors') and scrape_review_pages.last_errors:
            for error in scrape_review_pages.last_errors:
                flash(error, 'error')
        
        if not leads:
            if not (hasattr(scrape_review_pages, 'last_errors') and scrape_review_pages.last_errors):
                flash('No negative reviews found on these pages. This could mean: (1) The pages use JavaScript to load content (BeautifulSoup can\'t parse JS), (2) The CSS selectors don\'t match the page structure, or (3) There are no negative reviews matching the criteria. Check the console/terminal for detailed debug info.', 'warning')
        else:
            flash(f'Found {len(leads)} negative Avionté reviews!', 'success')
    except Exception as e:
        flash(f'Error during scraping: {str(e)}. Check the console for details.', 'error')
        leads = []
    
    return render_template('results.html', leads=leads)

@app.route('/leads')
def view_leads():
    """View all stored leads with advanced filtering"""
    pain_filter = request.args.get('pain', None)
    status_filter = request.args.get('status', None)
    min_score = request.args.get('min_score', None)
    sort_by = request.args.get('sort_by', 'lead_score')
    limit = int(request.args.get('limit', 1000))
    
    min_score_float = float(min_score) if min_score else None
    
    leads = get_all_leads_from_db(
        limit=limit, 
        pain_filter=pain_filter,
        status_filter=status_filter,
        min_score=min_score_float,
        sort_by=sort_by
    )
    stats = get_leads_count()
    analytics = get_lead_analytics()
    
    return render_template('leads.html', 
                         leads=leads, 
                         stats=stats, 
                         analytics=analytics,
                         pain_filter=pain_filter,
                         status_filter=status_filter,
                         min_score=min_score,
                         sort_by=sort_by)

@app.route('/analytics')
def analytics():
    """Analytics dashboard"""
    analytics_data = get_lead_analytics()
    return render_template('analytics.html', analytics=analytics_data)

@app.route('/lead/<int:lead_id>/update', methods=['POST'])
def update_lead(lead_id):
    """Update lead status and notes"""
    status = request.form.get('status', 'new')
    notes = request.form.get('notes', '')
    
    update_lead_status(lead_id, status, notes)
    flash(f'Lead #{lead_id} updated to status: {status}', 'success')
    return redirect(request.referrer or url_for('view_leads'))

@app.route('/download')
def download():
    """Download leads - either from request params or all from database"""
    leads_param = request.args.get('leads', None)
    
    if leads_param:
        # Download specific leads from results page
        leads_list = json.loads(leads_param)
        leads_data = [asdict(lead) for lead in leads_list]
    else:
        # Download all leads from database
        pain_filter = request.args.get('pain', None)
        leads_data = get_all_leads_from_db(limit=10000, pain_filter=pain_filter)
    
    output = io.StringIO()
    if leads_data:
        fieldnames = ['company_name', 'reviewer_name', 'review_title', 'review_text', 'rating', 
                      'pain_tags', 'source_url', 'scraped_at']
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for lead in leads_data:
            # Handle both dict and dataclass objects
            if isinstance(lead, dict):
                writer.writerow({k: lead.get(k, '') for k in fieldnames})
            else:
                writer.writerow(asdict(lead))
    
    output.seek(0)
    filename = f'avionte_leads_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

def cleanup_playwright_thread(thread_id=None):
    """Clean up Playwright browser resources for a specific thread"""
    if thread_id is None:
        thread_id = threading.get_ident()
    
    if thread_id not in _playwright_instances:
        return
    
    try:
        instance = _playwright_instances[thread_id]
        if instance.get('context'):
            instance['context'].close()
        if instance.get('browser'):
            instance['browser'].close()
        if instance.get('playwright'):
            instance['playwright'].stop()
        del _playwright_instances[thread_id]
        print(f"Playwright browser closed for thread {thread_id}")
    except Exception as e:
        # Silently handle thread switching errors (common with Flask reloader)
        if "cannot switch to a different thread" not in str(e):
            print(f"Error closing Playwright (thread {thread_id}): {e}")

def cleanup_all_playwright():
    """Clean up all Playwright instances (for shutdown)"""
    thread_ids = list(_playwright_instances.keys())
    for thread_id in thread_ids:
        try:
            cleanup_playwright_thread(thread_id)
        except:
            pass  # Ignore errors during cleanup


# Initialize database on startup
init_db()

def run_cli():
    """Run scraper from command line"""
    parser = argparse.ArgumentParser(
        description='Primlogix Avionté Lead Generator - CLI Mode',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python app.py --urls "https://g2.com/products/avionte-staffing-and-payroll/reviews"
  python app.py --urls "url1" "url2" "url3"
  python app.py --file urls.txt
  python app.py --web  (run web server)
        '''
    )
    parser.add_argument('--urls', nargs='+', help='One or more review page URLs to scrape')
    parser.add_argument('--file', help='File containing URLs (one per line)')
    parser.add_argument('--web', action='store_true', help='Run web server (default if no URLs provided)')
    parser.add_argument('--save', action='store_true', default=True, help='Save leads to database (default: True)')
    parser.add_argument('--no-save', dest='save', action='store_false', help='Do not save leads to database')
    parser.add_argument('--export', help='Export leads to CSV file')
    
    args = parser.parse_args()
    
    # If --web flag or no URLs provided, run web server
    if args.web or (not args.urls and not args.file):
        print("🌐 Starting web server on http://localhost:5000")
        print("Press Ctrl+C to stop\n")
        try:
            app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=True)
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            cleanup_all_playwright()
        return
    
    # CLI mode - collect URLs
    urls = []
    if args.urls:
        urls.extend(args.urls)
    if args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                file_urls = [line.strip() for line in f if line.strip()]
                urls.extend(file_urls)
        except FileNotFoundError:
            print(f"❌ Error: File '{args.file}' not found")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            sys.exit(1)
    
    if not urls:
        print("❌ Error: No URLs provided. Use --urls or --file")
        parser.print_help()
        sys.exit(1)
    
    # Run scraper
    print("🚀 Starting scraper in CLI mode...")
    print(f"📋 URLs to scrape: {len(urls)}\n")
    
    try:
        leads = scrape_review_pages(urls)
        
        # Save to database if requested
        if args.save and leads:
            saved, duplicates = save_leads_to_db(leads)
            print(f"\n💾 Database: Saved {saved} new leads, skipped {duplicates} duplicates")
        
        # Export to CSV if requested
        if args.export and leads:
            output = io.StringIO()
            fieldnames = ['company_name', 'reviewer_name', 'review_title', 'review_text', 'rating', 
                          'pain_tags', 'source_url', 'scraped_at', 'lead_score', 'status']
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for lead in leads:
                writer.writerow(asdict(lead))
            
            with open(args.export, 'w', encoding='utf-8', newline='') as f:
                f.write(output.getvalue())
            print(f"📥 Exported {len(leads)} leads to {args.export}")
        
        # Show summary
        if leads:
            print(f"\n✅ Successfully scraped {len(leads)} leads")
        else:
            print("\n⚠️  No leads found")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Scraping interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    finally:
        cleanup_all_playwright()

if __name__ == '__main__':
    run_cli()
