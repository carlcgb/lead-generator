<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Project Context (Legacy)

> **Tags:** `#legacy` `#context` `#business-context` `#historical`

**Note:** This file contains legacy context. The project has been refactored to be generic.

# Primlogix Avionté Lead Generation Scraper - COMPLETE CONTEXT

## Business Context

**Company**: Primlogix (staffing agency software competing directly with Avionté)
**Objective**: Find frustrated Avionté customers (staffing agencies) and turn them into Primlogix leads
**Lead Definition**: Staffing agencies posting negative reviews (<3/5 stars OR specific pain keywords) about Avionté
**Target Pains** (Primlogix wins here):

```
Complexity: "complex", "complicated", "hard to use", "difficult", "confusing"
Bugs: "buggy", "crash", "error", "downtime", "glitch"
Support: "support", "service", "helpdesk", "response time"
Integration: "integration", "sync", "api", "doesn't connect"
Cost: "expensive", "costly", "overpriced", "pricing"
Performance: "slow", "laggy", "takes forever"
```


## Technical Context

**Current Stack**: Flask web app with BeautifulSoup scraper → CSV export
**Input**: List of review page URLs (one per line)
**Output**: CSV with columns: `company_name`, `review_title`, `review_text`, `rating`, `pain_tags`, `source_url`, `scraped_at`
**Key Constraint**: Only scrape sites where terms/robots.txt explicitly allow automated access

## Target Review Site Categories

### 1. Major B2B Software Platforms (check terms first)

```
G2.com: https://g2.com/products/avionte-staffing-and-payroll/reviews
GetApp: https://www.getapp.com/hr-employee-management-software/a/avionte/
Software Advice: https://www.softwareadvice.com/ats/avionte-profile/
TrustRadius: https://www.trustradius.com/products/avionte/reviews
```


### 2. Staffing/HR Niche Blogs \& Comparisons

```
- "Top staffing software 2025" articles
- "Avionté review" from HR tech blogs
- ATS comparison sites for temp agencies
- "Why we switched from Avionté" case studies
```


### 3. Indirect Sources

```
- Reddit: r/recruiting, r/staffing, r/hrtech
- Forums: staffing agency owner communities
- Quora: "Avionté alternatives?" questions
```


## Scraper Requirements

### Legal/Ethical Rules (MANDATORY)

```
✅ Check robots.txt before adding any domain
✅ Respect rate limits (2-3 sec between requests)
✅ User-Agent: "PrimlogixLeadGenBot/1.0; +https://primlogix.com"
✅ Never access login-protected content
✅ No brute-force subdomain scanning (*.myavionte.com)
❌ Never scrape Capterra (explicitly forbids automation)
```


### Parser Selectors (flexible, site-adaptive)

```
Review containers: ".review-card", ".review-item", "article.review", "[data-review]"
Title: ".review-title", "h3", "h4", ".title"
Body: ".review-body", ".review-text", "[itemprop='reviewBody']"
Rating: "[itemprop='ratingValue']", ".star-rating", ".rating" (data-rating/content/text)
Company: ".reviewer-company", ".company-name", ".reviewer-name"
```


### Lead Qualification Logic

```
is_negative_review(text, rating):
    return rating <= 3.0 OR len(classify_pains(text)) > 0

classify_pains(text):  # returns ["complexity", "support", ...]
    Match against NEGATIVE_KEYWORDS dict
```


## Avionté Customer Signals (optional enrichment)

```
✅ *.myavionte.com subdomains confirm usage (single HEAD request only)
✅ Job postings mentioning Avionté = confirmed users
✅ Review company names → enrich with LinkedIn/Apollo
```


## Ideal Lead Output Format

```csv
company_name,review_title,review_text,rating,pain_tags,source_url,scraped_at,primlogix_fit_score
"ABC Staffing","Too Complex","The interface is way too complicated...",2.5,"complexity,support",https://g2.com/...,2025-12-05 10:00,9/10
```


## Web App Usage Flow

```
1. http://localhost:5000 → Paste review URLs
2. Click "Find Frustrated Avionté Users"
3. Results table → Filter by pain_tags
4. Download CSV → Import to CRM → Outbound calls
```


## Next Development Priorities

```
1. Add site-specific parsers (G2, GetApp selectors)
2. CRM integration (HubSpot/Salesforce CSV mapping)
3. Avionté subdomain checker (lightweight)
4. Lead scoring based on pain + company size
5. Scheduled scraping (cron + email alerts)
6. Deployment: Railway/Heroku for team access
```


## Example URLs to Test (SAFE starting points)

```
https://g2.com/products/avionte-staffing-and-payroll/reviews
https://www.getapp.com/hr-employee-management-software/a/avionte/reviews/
https://www.trustradius.com/products/avionte/reviews
https://www.softwareadvice.com/ats/avionte-profile/reviews/
```


***

**COPY THIS ENTIRE MARKDOWN → Cursor Settings → Custom Context**

This gives your Cursor agent full business context, legal boundaries, technical specs, and prioritization logic to refine the scraper intelligently.

