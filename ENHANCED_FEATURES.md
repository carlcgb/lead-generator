# Enhanced Lead Generation Features

## 🚀 New Lead Sources Added

### 1. 📱 Reddit Discovery
- **What it does**: Searches Reddit posts in staffing/recruiting subreddits for Avionté mentions
- **Subreddits**: r/recruiting, r/staffing, r/hrtech, r/humanresources, r/recruitinghell
- **Use case**: Find real discussions about Avionté problems and alternatives
- **Quality**: High - real user discussions

### 2. 📰 News & Articles
- **What it does**: Searches Google News for articles mentioning Avionté
- **Use case**: Find news articles, blog posts, case studies about Avionté
- **Quality**: Medium-High - often includes company names

### 3. 📞 Industry Directories
- **What it does**: Searches Yellow Pages and industry directories for staffing agencies
- **Use case**: Find all staffing agencies in a location, then check their websites
- **Quality**: Medium - need to verify Avionté usage

### 4. 🔗 Subdomain Checker
- **What it does**: Checks if companies use Avionté by verifying *.myavionte.com subdomains
- **Use case**: Confirm active Avionté users (highest quality leads!)
- **Quality**: Very High - confirms active usage
- **Example**: Checks if "primlogix.myavionte.com" exists

### 5. ❓ Quora Discovery
- **What it does**: Searches Quora for questions about Avionté alternatives
- **Use case**: Find people asking about Avionté alternatives
- **Quality**: Medium - may include company names

### 6. 🐦 Twitter/X Mentions
- **What it does**: Searches Twitter for Avionté mentions
- **Use case**: Find social media discussions about Avionté
- **Quality**: Medium - real-time discussions

### 7. 💼 LinkedIn Jobs (Enhanced)
- **What it does**: Searches LinkedIn job postings for Avionté mentions
- **Use case**: Find companies posting jobs requiring Avionté experience
- **Quality**: High - confirms active usage

## 📊 Comprehensive Discovery

The "All Sources" tab allows you to run discovery across multiple sources simultaneously:
- Select which sources to use
- Run all at once
- Get combined results with source breakdown

## 🎯 Lead Quality Scoring

Leads are automatically scored based on:
- **Subdomain confirmation**: +30 points (highest quality)
- **Job posting mentions**: +20 points
- **Review sites**: Based on rating and pain tags
- **Social media**: +10 points
- **News articles**: +15 points

## 💡 Best Practices

### High-Quality Lead Generation Strategy:

1. **Start with Subdomain Checker**
   - Use list of known staffing agencies
   - Confirms active Avionté users
   - Highest conversion potential

2. **Use Reddit for Real Discussions**
   - Find frustrated users discussing problems
   - Often includes company names
   - Real pain points mentioned

3. **Combine with Directory Search**
   - Find all staffing agencies in target area
   - Check their websites for Avionté mentions
   - Build comprehensive list

4. **News Articles for Case Studies**
   - Find "switching from Avionté" stories
   - Company names usually included
   - High-intent leads

5. **Job Boards for Active Users**
   - Companies posting Avionté-related jobs
   - Confirms current usage
   - Good for timing outreach

## 🔧 Technical Details

### Rate Limiting
- Reddit: 2 seconds between requests
- News: 2 seconds between queries
- Directories: 2 seconds between queries
- Subdomain checks: 0.5 seconds between checks

### Error Handling
- All sources have try-except blocks
- Errors are logged but don't stop the process
- Failed sources are skipped gracefully

### Data Quality
- Company names extracted from various sources
- Contact info extracted when available
- Avionté evidence preserved for verification

## 📈 Expected Results

### Typical Discovery Rates:
- **Reddit**: 5-20 leads per subreddit (depending on activity)
- **News**: 10-30 leads per query
- **Directories**: 50-200 companies (need verification)
- **Subdomain**: 1-5% of checked domains (high quality)
- **Quora**: 5-15 leads per query

### Combined Strategy:
Running all sources can yield **50-200+ leads per session** depending on:
- Number of queries
- Geographic scope
- Source selection

## 🚨 Important Notes

1. **Rate Limiting**: Always respect rate limits to avoid getting blocked
2. **Legal Compliance**: Only scrape public data, respect robots.txt
3. **Data Verification**: Always verify leads before contacting
4. **Subdomain Checks**: Only checks common patterns, not exhaustive
5. **Social Media**: May have limited results due to anti-scraping measures

## 🎯 Next Steps

1. Run comprehensive discovery across all sources
2. Review and filter leads by score
3. Verify high-scoring leads manually
4. Export to CSV for CRM import
5. Track conversion rates by source

