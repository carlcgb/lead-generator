#!/usr/bin/env python3
"""
Command-line interface for Primlogix Avionté Lead Generator
"""
import argparse
import sys
import csv
import io
from datetime import datetime
from dataclasses import asdict

# Import functions from streamlit_app (without Streamlit UI)
import sqlite3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import core functions (we'll need to extract them or import from streamlit_app)
# For now, let's create a CLI that uses the same logic

# Database setup
DATABASE = 'leads.db'

def get_db():
    """Get database connection"""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize the database"""
    # Import from streamlit_app
    import streamlit_app
    streamlit_app.init_db()

def scrape_urls_cli(urls, save_to_db=True, export_csv=None):
    """Scrape URLs from command line"""
    # Import scraping functions
    import streamlit_app
    
    print("🚀 Starting scraper in CLI mode...")
    print(f"📋 URLs to scrape: {len(urls)}\n")
    
    all_leads = []
    errors = []
    
    for idx, url in enumerate(urls, 1):
        print(f"🌐 Scraping {idx}/{len(urls)}: {url}")
        
        # Check for Capterra
        if 'capterra.com' in url or 'capterra.ca' in url:
            print(f"  ❌ Skipping Capterra (explicitly forbids automation)")
            errors.append(f"{url}: Capterra explicitly forbids automated scraping")
            continue
        
        try:
            html = streamlit_app.fetch_html(url)
            leads = streamlit_app.parse_reviews_generic(html, url)
            all_leads.extend(leads)
            print(f"  ✓ Found {len(leads)} negative reviews")
        except Exception as e:
            error_msg = str(e)
            print(f"  ✗ Error: {error_msg}")
            errors.append(f"{url}: {error_msg}")
    
    print(f"\n✅ Scraping complete! Found {len(all_leads)} total leads\n")
    
    # Save to database
    if save_to_db and all_leads:
        saved, duplicates = streamlit_app.save_leads_to_db(all_leads)
        print(f"💾 Database: Saved {saved} new leads, skipped {duplicates} duplicates")
    
    # Export to CSV
    if export_csv and all_leads:
        fieldnames = ['company_name', 'reviewer_name', 'review_title', 'review_text', 'rating', 
                      'pain_tags', 'source_url', 'scraped_at', 'lead_score', 'status']
        
        with open(export_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for lead in all_leads:
                writer.writerow(asdict(lead))
        print(f"📥 Exported {len(all_leads)} leads to {export_csv}")
    
    # Show errors
    if errors:
        print(f"\n⚠️  Errors encountered ({len(errors)}):")
        for error in errors:
            print(f"  • {error}")
    
    # Show summary
    if all_leads:
        print(f"\n📊 Summary:")
        print(f"  Total leads: {len(all_leads)}")
        print(f"  Average score: {sum(l.lead_score for l in all_leads) / len(all_leads):.1f}")
        
        # Show top leads
        sorted_leads = sorted(all_leads, key=lambda x: x.lead_score, reverse=True)
        print(f"\n🏆 Top 5 leads by score:")
        for i, lead in enumerate(sorted_leads[:5], 1):
            print(f"  {i}. {lead.company_name} (Score: {lead.lead_score:.1f}) - {lead.review_title[:60]}")
    else:
        print("\n⚠️  No leads found")
    
    return all_leads

def check_websites_cli(urls):
    """Check websites for Avionté mentions from command line"""
    try:
        from lead_discovery import check_website_for_avionte, scrape_company_website
    except ImportError:
        print("❌ Error: Lead discovery module not available")
        print("   Install: pip install googlemaps")
        return
    
    print("🔍 Checking websites for Avionté mentions...\n")
    
    results = []
    for idx, url in enumerate(urls, 1):
        print(f"Checking {idx}/{len(urls)}: {url}")
        
        # Normalize URL
        normalized_url = url.strip()
        if not normalized_url.startswith(('http://', 'https://')):
            normalized_url = 'https://' + normalized_url
        
        try:
            avionte_found, evidence = check_website_for_avionte(normalized_url)
            website_data = scrape_company_website(normalized_url)
            
            status = "✅ FOUND" if avionte_found else "❌ Not found"
            print(f"  {status}")
            
            if avionte_found:
                print(f"  Evidence: {evidence[:100] if evidence else 'N/A'}")
            
            if website_data:
                if website_data.get('email'):
                    print(f"  Email: {website_data['email']}")
                if website_data.get('phone'):
                    print(f"  Phone: {website_data['phone']}")
            
            results.append({
                'url': normalized_url,
                'avionte_found': avionte_found,
                'evidence': evidence,
                'email': website_data.get('email') if website_data else None,
                'phone': website_data.get('phone') if website_data else None
            })
        except Exception as e:
            print(f"  ✗ Error: {str(e)}")
            results.append({
                'url': normalized_url,
                'avionte_found': False,
                'evidence': f"Error: {str(e)}",
                'email': None,
                'phone': None
            })
    
    # Summary
    found_count = sum(1 for r in results if r['avionte_found'])
    print(f"\n📊 Summary: {found_count}/{len(results)} websites mention Avionté")
    
    return results

def main():
    parser = argparse.ArgumentParser(
        description='Primlogix Avionté Lead Generator - CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Scrape review pages
  python cli.py scrape --urls "https://g2.com/products/avionte-staffing-and-payroll/reviews"
  python cli.py scrape --urls "url1" "url2" "url3"
  python cli.py scrape --file urls.txt
  
  # Check websites for Avionté
  python cli.py check --urls "primlogix.com" "example-staffing.com"
  python cli.py check --file websites.txt
  
  # Export to CSV
  python cli.py scrape --urls "url1" --export leads.csv
        '''
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Scrape command
    scrape_parser = subparsers.add_parser('scrape', help='Scrape review pages')
    scrape_parser.add_argument('--urls', nargs='+', help='One or more review page URLs')
    scrape_parser.add_argument('--file', help='File containing URLs (one per line)')
    scrape_parser.add_argument('--save', action='store_true', default=True, help='Save to database (default: True)')
    scrape_parser.add_argument('--no-save', dest='save', action='store_false', help='Do not save to database')
    scrape_parser.add_argument('--export', help='Export to CSV file')
    
    # Check command
    check_parser = subparsers.add_parser('check', help='Check websites for Avionté mentions')
    check_parser.add_argument('--urls', nargs='+', help='One or more website URLs')
    check_parser.add_argument('--file', help='File containing URLs (one per line)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Collect URLs
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
    
    # Initialize database
    init_db()
    
    # Run command
    try:
        if args.command == 'scrape':
            scrape_urls_cli(urls, save_to_db=args.save, export_csv=args.export)
        elif args.command == 'check':
            check_websites_cli(urls)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()

