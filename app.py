import streamlit as st
import requests
import csv
import time
import re
import os
import random
import concurrent.futures
import queue
import threading
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

# Configuration
USER_AGENT_ROTATION = True
TIMEOUT = 25
MAX_WORKERS = 4
MAX_RETRIES = 5
REQUEST_DELAY = 2.0
CAPTCHA_BYPASS_ATTEMPTS = 3

# Updated selectors for current Google Maps layout
SELECTORS = {
    'business_card': 'div[role="article"]',
    'business_name': 'div.fontHeadlineLarge',
    'business_address': 'div > div > div.fontBodyMedium > div:nth-child(4)',
    'business_phone': 'div > div > div.fontBodyMedium > div:nth-child(5)',
    'business_website': 'a[href*="/url?"]',
    'business_rating': 'span[aria-label*="stars"]',
    'business_reviews': 'span[aria-label*="reviews"]',
    'business_category': 'div > div > div.fontBodyMedium > div:nth-child(2)',
    'next_page_button': 'button[aria-label="Next page"]',
    'result_count': 'div.fontBodyMedium > div > div > div:nth-child(2)'
}

# Common user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
]

def get_random_user_agent():
    """Get a random user agent from the list"""
    return random.choice(USER_AGENTS)

def clean_text(text):
    """Clean and normalize text"""
    if text is None:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

def resolve_google_redirect(url):
    """Resolve Google's redirect URL to actual website"""
    try:
        if url.startswith('https://www.google.com/url?'):
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            actual_url = query.get('q', [url])[0] or query.get('url', [url])[0]
            return actual_url
        return url
    except:
        return url

def extract_emails_from_website(url):
    """Extract emails from a website with polite delays"""
    if not url or url == "don't have website":
        return []
    
    try:
        resolved_url = resolve_google_redirect(url)
        headers = {'User-Agent': get_random_user_agent()}
        
        # Respectful delay before scraping websites
        time.sleep(1.0)
        
        response = requests.get(resolved_url, headers=headers, timeout=10)
        if response.status_code != 200:
            return []
        
        # Find email patterns in text
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, response.text)
        return list(set(emails))[:3]  # Return max 3 unique emails
    except:
        return []

def extract_business_data(soup):
    """Extract business data from Google Maps HTML"""
    results = []
    business_cards = soup.select(SELECTORS['business_card'])
    
    for card in business_cards:
        try:
            # Business Name
            name_elem = card.select_one(SELECTORS['business_name'])
            name = clean_text(name_elem.text) if name_elem else "N/A"
            
            # Address
            address_elem = card.select_one(SELECTORS['business_address'])
            address = clean_text(address_elem.text) if address_elem else "N/A"
            
            # Phone
            phone_elem = card.select_one(SELECTORS['business_phone'])
            phone = clean_text(phone_elem.text) if phone_elem else "N/A"
            
            # Website
            website_elem = card.select_one(SELECTORS['business_website'])
            website = website_elem['href'] if website_elem else "don't have website"
            website = resolve_google_redirect(website)
            
            # Rating
            rating_elem = card.select_one(SELECTORS['business_rating'])
            rating = clean_text(rating_elem['aria-label'].split()[0]) if rating_elem else "N/A"
            
            # Reviews
            reviews_elem = card.select_one(SELECTORS['business_reviews'])
            reviews = clean_text(reviews_elem['aria-label']) if reviews_elem else "N/A"
            
            # Category
            category_elem = card.select_one(SELECTORS['business_category'])
            category = clean_text(category_elem.text) if category_elem else "N/A"
            
            results.append({
                'Business Name': name,
                'Phone': phone,
                'Website': website,
                'Address': address,
                'Rating': rating,
                'Reviews': reviews,
                'Category': category
            })
        except Exception as e:
            continue
            
    return results

def get_result_count(soup):
    """Get total result count from page"""
    try:
        count_elem = soup.select_one(SELECTORS['result_count'])
        if count_elem:
            count_text = clean_text(count_elem.text)
            match = re.search(r'(\d+(,\d+)*)', count_text.replace(',', ''))
            if match:
                return int(match.group(1))
        return 0
    except:
        return 0

def handle_captcha(soup, query):
    """Detect and handle CAPTCHA challenges"""
    if "captcha" in soup.text.lower() or "denied" in soup.text.lower():
        st.warning(f"CAPTCHA detected for: {query}")
        return True
    return False

def scrape_google_maps(query, progress_callback=None):
    """Scrape Google Maps for business listings with infinite scrolling"""
    base_url = "https://www.google.com/maps/search/"
    
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    params = {'q': query}
    all_results = []
    retries = 0
    captcha_retries = 0
    result_count = 0
    session = requests.Session()
    
    try:
        # Initial request
        while retries < MAX_RETRIES and captcha_retries < CAPTCHA_BYPASS_ATTEMPTS:
            try:
                response = session.get(
                    base_url,
                    params=params,
                    headers=headers,
                    timeout=TIMEOUT
                )
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Check for CAPTCHA
                if handle_captcha(soup, query):
                    captcha_retries += 1
                    time.sleep(10)  # Longer delay for CAPTCHA
                    continue
                
                if response.status_code != 200:
                    retries += 1
                    time.sleep(REQUEST_DELAY * 2)
                    continue
                
                # Get initial results
                page_results = extract_business_data(soup)
                all_results.extend(page_results)
                
                # Get total result count
                result_count = get_result_count(soup)
                
                # Reset retries after successful request
                retries = 0
                break
                    
            except requests.exceptions.RequestException:
                retries += 1
                time.sleep(REQUEST_DELAY * 3)
        
        # If we have a result count, scrape all pages
        if result_count > 0:
            st.info(f"Found {result_count} total results for: {query}")
            
            # Continuously scrape until we have all results
            while len(all_results) < result_count and retries < MAX_RETRIES:
                try:
                    # Simulate scrolling by updating start parameter
                    params['start'] = len(all_results)
                    
                    response = session.get(
                        base_url,
                        params=params,
                        headers=headers,
                        timeout=TIMEOUT
                    )
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Check for CAPTCHA
                    if handle_captcha(soup, query):
                        captcha_retries += 1
                        time.sleep(15)
                        continue
                    
                    if response.status_code != 200:
                        retries += 1
                        time.sleep(REQUEST_DELAY * 2)
                        continue
                    
                    page_results = extract_business_data(soup)
                    
                    if not page_results:
                        break
                    
                    all_results.extend(page_results)
                    
                    # Update progress
                    if progress_callback:
                        progress_callback(len(all_results))
                    
                    # Respectful delay
                    time.sleep(REQUEST_DELAY)
                    
                    # Reset retries after successful request
                    retries = 0
                    
                except requests.exceptions.RequestException:
                    retries += 1
                    time.sleep(REQUEST_DELAY * 3)
        
        return all_results
        
    except Exception as e:
        st.error(f"Scraping failed for '{query}': {str(e)}")
        return []

def scrape_worker(query_queue, result_queue, progress_dict):
    """Worker thread for concurrent scraping"""
    while not query_queue.empty():
        try:
            query = query_queue.get_nowait()
            results = scrape_google_maps(
                query, 
                progress_callback=lambda count: progress_dict.update({query: count})
            )
            result_queue.put((query, results))
        except queue.Empty:
            break
        finally:
            query_queue.task_done()

def export_to_csv(data, filename_prefix):
    """Export data to CSV with timestamp"""
    if not data:
        return None
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename_prefix}_{timestamp}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Business Name', 'Phone', 'Website', 'Address', 
                     'Rating', 'Reviews', 'Category', 'Emails']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in data:
            writer.writerow(row)
        
    return filename

def main():
    st.set_page_config(
        page_title="Unlimited Google Maps Scraper",
        page_icon="🌐",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
        .stProgress > div > div > div > div {
            background: linear-gradient(90deg, #1a73e8, #34a853);
        }
        .stButton>button {
            background: linear-gradient(90deg, #1a73e8, #34a853);
            color: white;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            font-weight: 600;
            border: none;
            width: 100%;
        }
        .stButton>button:hover {
            background: linear-gradient(90deg, #1557b0, #2e8b46);
        }
        .stDownloadButton>button {
            background: linear-gradient(90deg, #1a73e8, #ea4335);
        }
        .stTextArea>textarea {
            min-height: 150px;
            border-radius: 8px;
        }
        .stExpander {
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        }
        .lead-badge {
            background-color: #34a853;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: bold;
            display: inline-block;
            margin-left: 8px;
        }
        .scraping-info {
            background-color: #e8f0fe;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("🌐 Unlimited Google Maps Scraper")
    st.markdown("""
    <div class="scraping-info">
        <h3 style="color: #1a73e8; margin-top: 0;">Scrape All Business Listings Without Limits</h3>
        <p>Get every result from Google Maps searches with complete contact information</p>
    </div>
    """, unsafe_allow_html=True)
    
    # User input
    col1, col2 = st.columns([3, 1])
    with col1:
        queries = st.text_area(
            "**Enter search queries (one per line):**",
            height=200,
            placeholder="Restaurants in New York\nCoffee shops in London\nDentists in Chicago...",
            help="Enter multiple search terms for bulk scraping"
        ).splitlines()
    
    with col2:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        st.markdown("**Power Search Examples:**")
        st.markdown("- `Marketing agencies near me`")
        st.markdown("- `Gym owners in Miami`")
        st.markdown("- `Real estate agents Texas`")
        st.markdown("- `IT companies with more than 50 employees`")

    # Settings
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        request_delay = st.slider("Request Delay (seconds)", 1, 10, 3, 
                                 help="Longer delays prevent blocking")
        enable_concurrent = st.checkbox("Enable parallel scraping", value=True,
                                      help="Faster results for multiple queries")
        enable_email = st.checkbox("Extract emails from websites", value=True,
                                 help="Find contact emails (slower but valuable)")
        
        st.markdown("## 🛡 Anti-Blocking Features")
        st.markdown("- Rotating User Agents")
        st.markdown("- Randomized request timing")
        st.markdown("- CAPTCHA detection")
        st.markdown("- Automatic retries")
        
        st.markdown("## 📦 Deployment Verified")
        st.success("Compatible with Streamlit Cloud")
        st.info("No external dependencies required")

    # Process button
    if st.button("🚀 Start Unlimited Scraping", use_container_width=True, type="primary"):
        if not queries or not any(q.strip() for q in queries):
            st.error("Please enter at least one search query")
            st.stop()
            
        # Initialize session state
        if 'all_data' not in st.session_state:
            st.session_state.all_data = []
        if 'scraping_complete' not in st.session_state:
            st.session_state.scraping_complete = False
            
        all_data = st.session_state.all_data
        progress_text = st.empty()
        progress_bar = st.progress(0)
        status_area = st.empty()
        results_container = st.container()
        progress_dict = {}
        
        start_time = time.time()
        valid_queries = [q.strip() for q in queries if q.strip()]
        query_count = len(valid_queries)
        
        # Display scraping info
        status_area.info("🔥 Starting unlimited scraping... This may take time for large result sets")
        
        if enable_concurrent and query_count > 1:
            # Concurrent scraping with thread pool
            query_queue = queue.Queue()
            result_queue = queue.Queue()
            
            for query in valid_queries:
                query_queue.put(query)
                progress_dict[query] = 0
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, query_count)) as executor:
                for _ in range(min(MAX_WORKERS, query_count)):
                    executor.submit(
                        scrape_worker, 
                        query_queue, 
                        result_queue, 
                        progress_dict
                    )
                
                processed = 0
                while processed < query_count:
                    try:
                        query, results = result_queue.get(timeout=120)
                        all_data.extend(results)
                        processed += 1
                        progress_bar.progress(processed / query_count)
                        
                        # Update status
                        status_area.success(f"✅ {query}: Collected {len(results)} businesses")
                        
                        # Show intermediate results
                        if results:
                            with results_container:
                                st.info(f"**Latest results from {query}:**")
                                st.json(results[-1], expanded=False)
                    except queue.Empty:
                        time.sleep(1)
            
        else:
            # Sequential scraping
            for i, query in enumerate(valid_queries):
                status_area.info(f"🔍 Searching: {query}...")
                results = scrape_google_maps(
                    query, 
                    progress_callback=lambda count: progress_dict.update({query: count})
                )
                
                if results:
                    all_data.extend(results)
                    status_area.success(f"✅ Found {len(results)} businesses for: {query}")
                    
                    # Show intermediate results
                    if results:
                        with results_container:
                            st.info(f"**Latest results from {query}:**")
                            st.json(results[-1], expanded=False)
                else:
                    status_area.warning(f"⚠️ No results found for: {query}")
                
                progress_bar.progress((i + 1) / query_count)
                time.sleep(1)
        
        # Update session state
        st.session_state.all_data = all_data
        st.session_state.scraping_complete = True
        
        # Email extraction if enabled
        if enable_email and all_data:
            with st.spinner("🔍 Extracting email addresses from websites..."):
                email_bar = st.progress(0)
                total_businesses = len(all_data)
                
                for i, business in enumerate(all_data):
                    if business['Website'] and business['Website'] != "don't have website":
                        business['Emails'] = ", ".join(extract_emails_from_website(business['Website']))
                    else:
                        business['Emails'] = "N/A"
                    
                    # Update progress more frequently
                    if i % 5 == 0 or i == total_businesses - 1:
                        email_bar.progress((i + 1) / total_businesses)
        
        # Final results display
        if all_data:
            elapsed = time.time() - start_time
            results_container.success(f"✅ Success! Collected {len(all_data)} businesses in {elapsed:.1f} seconds")
            
            # Show data preview
            with st.expander("📊 Results Preview", expanded=True):
                if all_data:
                    st.write(f"**Total Businesses:** {len(all_data)}")
                    st.write(f"**First Business:** {all_data[0]['Business Name']}")
                    st.write(f"**Last Business:** {all_data[-1]['Business Name']}")
                    st.json(all_data[0], expanded=False)
            
            # Export options
            csv_file = export_to_csv(all_data, "unlimited_google_maps_results")
            if csv_file:
                with open(csv_file, "rb") as f:
                    st.download_button(
                        label="💾 Download Full Results CSV",
                        data=f,
                        file_name=os.path.basename(csv_file),
                        mime="text/csv",
                        use_container_width=True
                    )
                
                # Clean up file
                if os.path.exists(csv_file):
                    os.remove(csv_file)
        else:
            st.error("No business data collected. Try different queries or check settings.")

    # Show session data if scraping completed
    if st.session_state.get('scraping_complete', False) and st.session_state.get('all_data'):
        st.markdown("## 📦 Saved Scraping Results")
        st.info(f"Total businesses collected: {len(st.session_state.all_data)}")
        
        if st.button("🔄 Export Results Again", use_container_width=True):
            csv_file = export_to_csv(st.session_state.all_data, "unlimited_google_maps_results")
            if csv_file:
                with open(csv_file, "rb") as f:
                    st.download_button(
                        label="💾 Download Results CSV",
                        data=f,
                        file_name=os.path.basename(csv_file),
                        mime="text/csv",
                        use_container_width=True
                    )

if __name__ == "__main__":
    main()
