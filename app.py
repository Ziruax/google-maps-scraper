import streamlit as st
import requests
import csv
import time
import re
import pandas as pd
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import os
from datetime import datetime
from urllib.parse import urlparse
import concurrent.futures
import queue
import threading

# Configuration
MAX_RESULTS = 200
REQUEST_DELAY = 1.5  # seconds
USER_AGENT_ROTATION = True
TIMEOUT = 20
MAX_WORKERS = 3  # Safe concurrency level for free usage
MAX_RETRIES = 2
CAPTCHA_BYPASS_ATTEMPTS = 2

# Selectors (updated for recent Google Maps layout)
SELECTORS = {
    'business_card': 'div[role="article"]',
    'business_name': 'div.fontHeadlineLarge',
    'business_address': 'div > div > div.fontBodyMedium > div:nth-child(4)',
    'business_phone': 'div > div > div.fontBodyMedium > div:nth-child(5)',
    'business_website': 'a[href*="/url?"]',
    'business_rating': 'span[aria-label*="stars"]',
    'business_reviews': 'span[aria-label*="reviews"]',
    'business_category': 'div > div > div.fontBodyMedium > div:nth-child(2)',
    'business_hours': 'div[aria-label*="hours"]'
}

def get_random_user_agent():
    ua = UserAgent()
    return ua.random

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
            query = parsed.query
            # Extract actual URL from query parameters
            qs_params = dict(param.split('=') for param in query.split('&') if '=' in param)
            actual_url = qs_params.get('q', qs_params.get('url', url))
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
        time.sleep(0.5)
        
        response = requests.get(resolved_url, headers=headers, timeout=8)
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
            
            # Address - more robust extraction
            address_elem = card.select_one(SELECTORS['business_address'])
            address = clean_text(address_elem.text) if address_elem else "N/A"
            
            # Phone - improved fallback
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

def handle_captcha(soup, query):
    """Detect and handle CAPTCHA challenges"""
    if "captcha" in soup.text.lower() or "denied" in soup.text.lower():
        st.warning(f"CAPTCHA detected for: {query}")
        return True
    return False

def scrape_google_maps(query, max_results=MAX_RESULTS, progress_callback=None):
    """Scrape Google Maps for business listings with retries"""
    base_url = "https://www.google.com/maps/search/"
    
    headers = {
        'User-Agent': get_random_user_agent() if USER_AGENT_ROTATION else 'Mozilla/5.0',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    
    params = {'q': query}
    all_results = []
    start = 0
    retries = 0
    captcha_retries = 0
    
    try:
        while start < max_results and retries < MAX_RETRIES and captcha_retries < CAPTCHA_BYPASS_ATTEMPTS:
            # Simulate pagination
            if start > 0:
                params['start'] = start * 20  # Google's pagination multiplier
            
            try:
                response = requests.get(
                    base_url,
                    params=params,
                    headers=headers,
                    timeout=TIMEOUT
                )
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Check for CAPTCHA
                if handle_captcha(soup, query):
                    captcha_retries += 1
                    time.sleep(5)  # Longer delay for CAPTCHA
                    continue
                
                if response.status_code != 200:
                    st.warning(f"Retry {retries+1}/{MAX_RETRIES} for '{query}'")
                    retries += 1
                    time.sleep(REQUEST_DELAY * 2)
                    continue
                
                page_results = extract_business_data(soup)
                
                if not page_results:
                    break
                    
                all_results.extend(page_results)
                start += 1  # Page increment
                
                # Reset retries after successful request
                retries = 0
                
                # Update progress
                if progress_callback:
                    progress_callback(len(all_results))
                
                # Respectful delay
                time.sleep(REQUEST_DELAY)
                
                # Break if we've reached max results
                if len(all_results) >= max_results:
                    break
                    
            except requests.exceptions.RequestException as e:
                retries += 1
                time.sleep(REQUEST_DELAY * 3)
                
        return all_results[:max_results]
        
    except Exception as e:
        st.error(f"Scraping failed for '{query}': {str(e)}")
        return []

def scrape_worker(query_queue, result_queue, max_results, progress_dict):
    """Worker thread for concurrent scraping"""
    while not query_queue.empty():
        try:
            query = query_queue.get_nowait()
            results = scrape_google_maps(
                query, 
                max_results,
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
        page_title="Free Google Maps Lead Scraper",
        page_icon="🌍",
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
    </style>
    """, unsafe_allow_html=True)
    
    st.title("🌍 Free Google Maps Lead Scraper")
    st.markdown("""
    <div style="background-color: #e8f0fe; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
        <h3 style="color: #1a73e8; margin-top: 0;">Extract Valuable Business Leads for FREE</h3>
        <p>Generate targeted leads from Google Maps with contact information for your business outreach</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.expander("💡 How To Use This Tool", expanded=True):
        st.markdown("""
        1. **Enter search queries** - Location-based searches work best (e.g., "Dentists in Miami")
        2. **Configure settings** - Adjust results per query and scraping speed
        3. **Start scraping** - The tool will gather business information
        4. **Download CSV** - Get your leads in spreadsheet format
        """)
    
    # Lead generation tips
    with st.expander("🔍 Lead Generation Tips"):
        st.markdown("""
        - **Be specific**: "Plumbers in Austin TX" works better than "Plumbers"
        - **Use location modifiers**: Add zip codes or neighborhoods for targeted leads
        - **Try industry-specific terms**: "HVAC contractors", "SEO agencies", etc.
        - **Combine services + locations**: "Wedding photographers Boston"
        - **Use quotes for exact matches**: "Coffee shops" near "Times Square"
        """)
    
    # User input
    col1, col2 = st.columns([3, 1])
    with col1:
        queries = st.text_area(
            "**Enter search queries (one per line):**",
            height=150,
            placeholder="Restaurants in New York\nCoffee shops in London\nDentists in Chicago...",
            help="Enter multiple search terms for bulk scraping"
        ).splitlines()
    
    with col2:
        st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
        st.markdown("**Example searches:**")
        st.markdown("- `Marketing agencies LA`")
        st.markdown("- `Gym owners in Miami`")
        st.markdown("- `Real estate agents Texas`")

    # Settings
    with st.sidebar:
        st.markdown("## ⚙️ Settings")
        max_results = st.slider("Results per query", 10, 100, 30, 
                               help="Higher numbers may trigger CAPTCHAs")
        request_delay = st.slider("Delay between requests", 1, 5, 2, 
                                 help="Longer delays are safer")
        enable_concurrent = st.checkbox("Enable parallel scraping", value=True,
                                      help="Faster results for multiple queries")
        enable_email = st.checkbox("Extract emails from websites", value=True,
                                 help="Find contact emails (slower but valuable)")
        
        st.markdown("## 📊 Data Options")
        include_rating = st.checkbox("Include ratings", value=True)
        include_reviews = st.checkbox("Include review counts", value=True)
        
        st.markdown("## 💖 Support This Project")
        st.markdown("If this tool helps you, please:")
        st.markdown("- [Buy me a coffee](https://buymeacoffee.com)")
        st.markdown("- Star the [GitHub repo]()")
        st.markdown("- Share with others")
    
    # Process button
    if st.button("🚀 Start Lead Generation", use_container_width=True, type="primary"):
        if not queries or not any(q.strip() for q in queries):
            st.error("Please enter at least one search query")
            st.stop()
            
        all_data = []
        progress_text = st.empty()
        progress_bar = st.progress(0)
        status_area = st.empty()
        results_container = st.container()
        progress_dict = {}
        
        start_time = time.time()
        valid_queries = [q.strip() for q in queries if q.strip()]
        query_count = len(valid_queries)
        
        # Display lead estimate
        estimated_leads = min(max_results * query_count, 300)  # Conservative estimate
        status_area.info(f"⏳ Starting lead generation... Estimated potential leads: {estimated_leads}")
        
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
                        max_results,
                        progress_dict
                    )
                
                processed = 0
                while processed < query_count:
                    try:
                        query, results = result_queue.get(timeout=90)
                        all_data.extend(results)
                        processed += 1
                        progress_bar.progress(processed / query_count)
                        
                        # Update status
                        status_area.success(f"✅ {query}: Collected {len(results)} leads")
                        
                        # Show intermediate results
                        if results:
                            st.session_state.setdefault('leads', []).extend(results)
                            with results_container:
                                st.info(f"**Latest leads from {query}:**")
                                latest_df = pd.DataFrame(results[-3:])
                                st.dataframe(latest_df[['Business Name', 'Phone', 'Address']], hide_index=True)
                    except queue.Empty:
                        time.sleep(1)
            
        else:
            # Sequential scraping
            for i, query in enumerate(valid_queries):
                status_area.info(f"🔍 Searching: {query}...")
                results = scrape_google_maps(
                    query, 
                    max_results,
                    progress_callback=lambda count: progress_dict.update({query: count})
                )
                
                if results:
                    all_data.extend(results)
                    status_area.success(f"✅ Found {len(results)} leads for: {query}")
                    
                    # Show intermediate results
                    st.session_state.setdefault('leads', []).extend(results)
                    with results_container:
                        st.info(f"**Latest leads from {query}:**")
                        latest_df = pd.DataFrame(results[-3:])
                        st.dataframe(latest_df[['Business Name', 'Phone', 'Address']], hide_index=True)
                else:
                    status_area.warning(f"⚠️ No results found for: {query}")
                
                progress_bar.progress((i + 1) / query_count)
                time.sleep(1)
        
        # Email extraction if enabled
        if enable_email and all_data:
            with st.spinner("🔍 Extracting email addresses (most valuable leads)..."):
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
            results_container.success(f"✅ Success! Collected {len(all_data)} valuable leads in {elapsed:.1f} seconds")
            
            # Create final dataframe
            df = pd.DataFrame(all_data)
            
            # Show data preview
            with st.expander("📊 Full Leads Preview", expanded=True):
                # Filter columns based on settings
                display_cols = ['Business Name', 'Phone', 'Website', 'Address']
                if include_rating: display_cols.append('Rating')
                if include_reviews: display_cols.append('Reviews')
                if enable_email: display_cols.append('Emails')
                
                st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
                
                # Show stats
                st.subheader("📈 Lead Generation Report")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Leads", len(df))
                websites_found = df[df['Website'] != "don't have website"].shape[0]
                col2.metric("Websites Found", f"{websites_found} ({websites_found/len(df)*100:.1f}%)")
                
                if enable_email:
                    emails_found = df[df['Emails'] != "N/A"].shape[0]
                    col3.metric("Emails Extracted", f"{emails_found} ({emails_found/len(df)*100:.1f}%)")
                else:
                    col3.metric("Phone Numbers", df[df['Phone'] != "N/A"].shape[0])
                
                col4.metric("Avg. Rating", f"{df[df['Rating'] != 'N/A']['Rating'].mean():.1f}/5" if not df.empty else "N/A")
            
            # Export options
            csv_file = export_to_csv(all_data, "google_maps_leads")
            if csv_file:
                with open(csv_file, "rb") as f:
                    st.download_button(
                        label="💾 Download Full Leads CSV",
                        data=f,
                        file_name=os.path.basename(csv_file),
                        mime="text/csv",
                        use_container_width=True
                    )
                
                # Clean up file
                if os.path.exists(csv_file):
                    os.remove(csv_file)
        else:
            st.error("No leads collected. Try adjusting your search terms or reducing the number of results per query.")

if __name__ == "__main__":
    main()
