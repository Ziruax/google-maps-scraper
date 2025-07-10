import streamlit as st
import requests
import csv
import time
import re
import os
import random
import json
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
USER_AGENT_ROTATION = True
TIMEOUT = 30
MAX_RETRIES = 5
REQUEST_DELAY = 2.0
CAPTCHA_BYPASS_ATTEMPTS = 3

# UPDATED SELECTORS - fixed to match current Google Maps structure
SELECTORS = {
    'business_card': ['div[role="article"]', 'div.Nv2PK', 'div.section-result', 'div.lI9IFe', 'div.THOPZb'],
    'business_name': ['div.fontHeadlineLarge', 'div.qBF1Pd', 'h2.section-result-title', 'h2.drO22b'],
    'business_address': [
        'div.W4Efsd:not(:has(span.W4Efsd))',
        'div > div > div.fontBodyMedium > div:nth-child(4)',
        'span.section-result-location',
        'div.UaQhfb'
    ],
    'business_phone': [
        'span[aria-label*="Phone"]',
        'span[data-tooltip*="Phone"]',
        'div.W4Efsd > span:nth-child(3)',
        'span.section-result-phone'
    ],
    'business_website': [
        'a[href*="/url?"]',
        'a[aria-label*="Website"]',
        'a.section-result-action-icon',
        'a[data-tooltip*="Website"]'
    ],
    'business_rating': [
        'span[aria-label*="stars"]', 
        'span[role="img"]', 
        'div.section-result-rating'
    ],
    'business_reviews': [
        'span[aria-label*="reviews"]', 
        'span.julYat', 
        'span.section-result-num-ratings'
    ],
    'business_category': [
        'div.W4Efsd > span:nth-child(1)',
        'div > div > div.fontBodyMedium > div:nth-child(2)',
        'div.section-result-details-container'
    ],
    'result_count': [
        'div.m6QErb.DxyBCb.kA9KIf.dS8AEf',
        'div.fontBodyMedium > div > div > div:nth-child(2)'
    ]
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

def find_element_with_fallback(soup, selectors):
    """Try multiple selectors until one works"""
    for selector in selectors:
        try:
            elements = soup.select(selector)
            if elements:
                return elements
        except Exception as e:
            logger.warning(f"Selector error: {selector} - {str(e)}")
    return None

def extract_business_data(soup):
    """Extract business data from Google Maps HTML with fallbacks"""
    results = []
    
    # Try all possible card selectors
    business_cards = []
    for card_selector in SELECTORS['business_card']:
        cards = soup.select(card_selector)
        if cards:
            business_cards = cards
            break
    
    if not business_cards:
        logger.warning("No business cards found with any selector")
        return results
    
    logger.info(f"Found {len(business_cards)} business cards")
    
    for card in business_cards:
        try:
            # Business Name
            name_elem = find_element_with_fallback(card, SELECTORS['business_name'])
            name = clean_text(name_elem[0].text) if name_elem and len(name_elem) > 0 else "N/A"
            
            # Address - improved handling
            address_elem = find_element_with_fallback(card, SELECTORS['business_address'])
            address = ""
            if address_elem:
                for elem in address_elem:
                    text = clean_text(elem.text)
                    if text and not any(word in text.lower() for word in ["hours", "open", "closed", "phone"]):
                        address = text
                        break
                if not address:
                    address = clean_text(address_elem[0].text) if address_elem else "N/A"
            else:
                address = "N/A"
            
            # Phone
            phone_elem = find_element_with_fallback(card, SELECTORS['business_phone'])
            phone = clean_text(phone_elem[0].text) if phone_elem and len(phone_elem) > 0 else "N/A"
            
            # Website
            website = "don't have website"
            website_elems = find_element_with_fallback(card, SELECTORS['business_website'])
            if website_elems:
                for elem in website_elems:
                    if 'href' in elem.attrs:
                        website = elem['href']
                        break
            website = resolve_google_redirect(website)
            
            # Rating
            rating_elem = find_element_with_fallback(card, SELECTORS['business_rating'])
            rating = "N/A"
            if rating_elem:
                for elem in rating_elem:
                    if 'aria-label' in elem.attrs:
                        rating_text = elem['aria-label']
                        match = re.search(r'(\d+\.?\d*)', rating_text)
                        if match:
                            rating = match.group(1)
                            break
                    else:
                        match = re.search(r'(\d+\.?\d*)', elem.text)
                        if match:
                            rating = match.group(1)
                            break
            
            # Reviews
            reviews_elem = find_element_with_fallback(card, SELECTORS['business_reviews'])
            reviews = "N/A"
            if reviews_elem:
                reviews_text = clean_text(reviews_elem[0].text)
                match = re.search(r'(\d[\d,]*)', reviews_text.replace(',', ''))
                if match:
                    reviews = match.group(1)
            
            # Category
            category_elem = find_element_with_fallback(card, SELECTORS['business_category'])
            category = clean_text(category_elem[0].text) if category_elem and len(category_elem) > 0 else "N/A"
            
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
            logger.error(f"Error processing card: {str(e)}")
            continue
            
    return results

def get_result_count(soup):
    """Get total result count from page"""
    try:
        for selector in SELECTORS['result_count']:
            count_elem = soup.select(selector)
            if count_elem:
                count_text = clean_text(count_elem[0].text)
                match = re.search(r'(\d+(,\d+)*)', count_text.replace(',', ''))
                if match:
                    return int(match.group(1))
        return 0
    except:
        return 0

def handle_captcha(response, query):
    """Detect and handle CAPTCHA challenges"""
    captcha_indicators = ["captcha", "denied", "sorry", "automated", "robot"]
    if any(indicator in response.text.lower() for indicator in captcha_indicators):
        logger.warning(f"CAPTCHA detected for: {query}")
        return True
    return False

def scrape_google_maps(query):
    """Scrape Google Maps for business listings with multiple fallbacks"""
    base_url = "https://www.google.com/maps/search/"
    
    headers = {
        'User-Agent': get_random_user_agent(),
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://www.google.com/'
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
                
                if handle_captcha(response, query):
                    captcha_retries += 1
                    time.sleep(10)  # Longer delay for CAPTCHA
                    continue
                
                if response.status_code != 200:
                    logger.warning(f"Request failed with status {response.status_code}, retrying...")
                    retries += 1
                    time.sleep(REQUEST_DELAY * 2)
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Get initial results
                page_results = extract_business_data(soup)
                all_results.extend(page_results)
                
                # Get total result count
                result_count = get_result_count(soup)
                
                logger.info(f"Initial results: {len(page_results)} | Total results: {result_count}")
                
                # Reset retries after successful request
                retries = 0
                break
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Request exception: {str(e)}")
                retries += 1
                time.sleep(REQUEST_DELAY * 3)
        
        # Only attempt pagination if we have results
        if page_results:
            # Scroll to get more results (simulated by changing viewport)
            scroll_params = {'q': query, 'start': len(all_results)}
            
            try:
                response = session.get(
                    base_url,
                    params=scroll_params,
                    headers=headers,
                    timeout=TIMEOUT
                )
                
                if not handle_captcha(response, query) and response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    additional_results = extract_business_data(soup)
                    if additional_results:
                        all_results.extend(additional_results)
                        logger.info(f"Additional results: {len(additional_results)} | Total: {len(all_results)}")
            except Exception as e:
                logger.warning(f"Pagination failed: {str(e)}")
        
        return all_results
        
    except Exception as e:
        logger.error(f"Scraping failed for '{query}': {str(e)}")
        return []

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
        page_title="Robust Google Maps Scraper",
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
        .scraping-info {
            background-color: #e8f0fe;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .debug-section {
            background-color: #fff8e1;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
        }
        .result-card {
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            background-color: #f8f9fa;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.title("🌐 Robust Google Maps Scraper")
    st.markdown("""
    <div class="scraping-info">
        <h3 style="color: #1a73e8; margin-top: 0;">Advanced Scraping with Multiple Fallback Methods</h3>
        <p><strong>Fixed selector issues</strong> and improved data extraction reliability</p>
    </div>
    """, unsafe_allow_html=True)
    
    # User input
    col1, col2 = st.columns([3, 1])
    with col1:
        queries = st.text_area(
            "**Enter search queries (one per line):**",
            height=200,
            placeholder="Restaurants in New York\nCoffee shops in London\nDentists in Chicago...",
            help="Enter multiple search terms for bulk scraping",
            value="Real estate agents Texas"
        ).splitlines()
    
    with col2:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        st.markdown("**Effective Query Examples:**")
        st.markdown("- `Marketing agencies near me`")
        st.markdown("- `Gym owners in Miami`")
        st.markdown("- `Real estate agents Texas`")
        st.markdown("- `IT companies with more than 50 employees`")

    # Settings
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        request_delay = st.slider("Request Delay (seconds)", 1, 10, 2, 
                                 help="Longer delays prevent blocking")
        enable_email = st.checkbox("Extract emails from websites", value=True,
                                 help="Find contact emails (slower but valuable)")
        max_results = st.slider("Max Results per Query", 10, 100, 30,
                               help="Limit results per search query")
        
        st.markdown("## 🛡 Anti-Blocking Features")
        st.markdown("- Multiple selector fallbacks")
        st.markdown("- Rotating User Agents")
        st.markdown("- CAPTCHA detection")
        st.markdown("- Request throttling")
        
        st.markdown("## 🐞 Debugging Tools")
        debug_mode = st.checkbox("Enable debug mode", value=False,
                               help="Show detailed scraping information")

    # Process button
    if st.button("🚀 Start Advanced Scraping", use_container_width=True, type="primary"):
        if not queries or not any(q.strip() for q in queries):
            st.error("Please enter at least one search query")
            st.stop()
            
        # Initialize session state
        if 'all_data' not in st.session_state:
            st.session_state.all_data = []
        if 'scraping_complete' not in st.session_state:
            st.session_state.scraping_complete = False
            
        all_data = st.session_state.all_data
        status_area = st.empty()
        results_container = st.container()
        debug_container = st.container()
        
        start_time = time.time()
        valid_queries = [q.strip() for q in queries if q.strip()]
        
        # Display scraping info
        status_area.info("🔍 Starting advanced scraping with multiple fallback methods...")
        
        # Sequential scraping with detailed logging
        for i, query in enumerate(valid_queries):
            status_area.info(f"🌐 Processing: {query}...")
            
            # Create a progress bar for each query
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Scrape with retries
            results = []
            for attempt in range(MAX_RETRIES):
                try:
                    status_text.info(f"Attempt {attempt+1}/{MAX_RETRIES} for: {query}")
                    results = scrape_google_maps(query)
                    if results:
                        # Apply max results limit
                        results = results[:max_results]
                        break
                except Exception as e:
                    status_text.error(f"Error during attempt {attempt+1}: {str(e)}")
                    time.sleep(request_delay * 2)
            
            if results:
                all_data.extend(results)
                status_area.success(f"✅ Found {len(results)} results for: {query}")
                
                # Show intermediate results
                with results_container:
                    st.info(f"**Results from {query}:**")
                    with st.expander("View Results", expanded=False):
                        for i, biz in enumerate(results[:5]):
                            st.markdown(f"""
                            <div class="result-card">
                                <h4>{i+1}. {biz['Business Name']}</h4>
                                <p><strong>Category:</strong> {biz['Category']}</p>
                                <p><strong>Address:</strong> {biz['Address']}</p>
                                <p><strong>Phone:</strong> {biz['Phone']}</p>
                                <p><strong>Website:</strong> {biz['Website']}</p>
                            </div>
                            """, unsafe_allow_html=True)
            else:
                status_area.warning(f"⚠️ No results found for: {query}")
            
            progress_bar.progress(100)
            time.sleep(request_delay)
        
        # Update session state
        st.session_state.all_data = all_data
        st.session_state.scraping_complete = True
        
        # Email extraction if enabled
        if enable_email and all_data:
            with st.spinner("🔍 Extracting email addresses from websites..."):
                email_bar = st.progress(0)
                total_businesses = len(all_data)
                extracted_count = 0
                
                for i, business in enumerate(all_data):
                    if business['Website'] and business['Website'] != "don't have website":
                        emails = extract_emails_from_website(business['Website'])
                        if emails:
                            business['Emails'] = ", ".join(emails)
                            extracted_count += 1
                        else:
                            business['Emails'] = "N/A"
                    else:
                        business['Emails'] = "N/A"
                    
                    # Update progress
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
            csv_file = export_to_csv(all_data, "google_maps_results")
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
            
        # Debug info
        if debug_mode:
            with debug_container:
                st.markdown("## 🐞 Debug Information")
                st.info("""
                **Scraping Process Details:**
                - Used multiple selector fallbacks for each element
                - Rotated user agents between requests
                - Implemented CAPTCHA detection and handling
                - Used session persistence for better reliability
                """)
                
                if valid_queries:
                    st.write(f"**Processed Queries:** {', '.join(valid_queries)}")
                    st.write(f"**Total Results Collected:** {len(all_data)}")
                    st.write(f"**Time Taken:** {elapsed:.1f} seconds")
                    
                    if all_data:
                        st.write("**Sample Data Structure:**")
                        st.json(all_data[0])

    # Show session data if scraping completed
    if st.session_state.get('scraping_complete', False) and st.session_state.get('all_data'):
        st.markdown("## 📦 Saved Scraping Results")
        st.info(f"Total businesses collected: {len(st.session_state.all_data)}")
        
        if st.button("🔄 Export Results Again", use_container_width=True):
            csv_file = export_to_csv(st.session_state.all_data, "google_maps_results")
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
