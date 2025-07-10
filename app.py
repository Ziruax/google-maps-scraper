# app.py

import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time
import random
import re
from urllib.parse import quote_plus

# --- Core Scraping and Parsing Functions ---

def get_headers():
    """Generates random User-Agent headers."""
    ua = UserAgent()
    return {'User-Agent': ua.random}

def parse_google_maps_html(soup):
    """
    Parses the HTML soup of a Google Maps search results page.
    This version is hardened against structural changes and NoneType errors.
    """
    results = []
    main_container = soup.find('div', {'role': 'feed'})
    
    if not main_container:
        if "Before you continue" in soup.get_text():
            st.error("Google is blocking the request (CAPTCHA/consent page).")
        else:
            st.warning("Could not find the main results container. The page structure may have changed, or there are no results.")
        return []

    # Find all potential result items
    all_links = main_container.find_all('a', href=re.compile(r'https://www.google.com/maps/place/'))
    
    processed_hrefs = set()

    for link in all_links:
        href = link.get('href')
        if not href or href in processed_hrefs:
            continue
        
        # --- THE CRITICAL FIX IS HERE ---
        # Find the parent container that represents a single search result "card".
        # This is more reliable than find_parent().find_parent().
        # We look for a div with a 'jsaction' attribute, which is common for result items.
        result_container = link.find_parent('div', {'jsaction': True})

        # If we can't find a proper container, it's likely a non-result link, so we skip it.
        if not result_container:
            continue
            
        # Add to processed to avoid duplicates from multiple links in the same card
        processed_hrefs.add(href)
        
        data = {
            'Query': 'Not Available',
            'Business Name': 'Not Available',
            'Business Category': 'Not Available',
            'Address': 'Not Available',
            'Website': 'No Website',
            'Phone Number': 'Not Available',
            'Rating': 'Not Available',
            'Number of Reviews': 'Not Available'
        }

        # --- Extract Business Name from the aria-label of the link ---
        business_name = link.get('aria-label')
        if not business_name:
            continue # If there's no aria-label, it's not a main business link.
        data['Business Name'] = business_name.strip()

        # --- Extract other details from the text within the container ---
        # Use a fallback to prevent error if get_text returns None (highly unlikely but safe)
        container_text = result_container.get_text(separator=' · ', strip=True) or ""
        text_parts = container_text.split(' · ')

        # --- Extract Rating and Reviews ---
        for part in text_parts:
            if '★' in part:
                try:
                    rating_match = re.search(r'(\d\.\d)\s?★', part)
                    if rating_match:
                        data['Rating'] = rating_match.group(1)
                    
                    reviews_match = re.search(r'\((\d{1,3}(?:,\d{3})*)\)', part)
                    if reviews_match:
                        data['Number of Reviews'] = reviews_match.group(1).replace(',', '')
                except (IndexError, ValueError):
                    pass # Ignore if parsing fails

        # --- Extract other info by iterating through the text parts ---
        # Heuristics are needed as the order and presence of elements vary.
        phone_found = False
        address_found = False
        
        for part in text_parts:
            # Skip parts that are clearly not category, address, or phone
            if part == data['Business Name'] or '★' in part or part.lower() in ['directions', 'website', 'call']:
                continue
            
            # Heuristic for Phone Number
            if not phone_found and (re.search(r'^\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$', part) or re.search(r'^\+\d{1,}', part)):
                data['Phone Number'] = part
                phone_found = True
                continue
            
            # Heuristic for Address (often contains numbers and is longer)
            if not address_found and any(char.isdigit() for char in part) and len(part) > 10:
                data['Address'] = part
                address_found = True
                continue

            # Heuristic for Category (usually short, no digits, and not found yet)
            if data['Business Category'] == 'Not Available' and not any(char.isdigit() for char in part) and 2 < len(part) < 30:
                 data['Business Category'] = part

        # --- Extract Website from a specific button ---
        website_tag = result_container.find('a', {'data-value': 'Website'})
        if website_tag and website_tag.get('href'):
            data['Website'] = website_tag['href']

        results.append(data)

    return results

def scrape_google_maps(queries):
    """Main function to orchestrate the scraping process for multiple queries."""
    all_results = []
    total_queries = len(queries)
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, query in enumerate(queries):
        query_cleaned = query.strip()
        if not query_cleaned:
            continue

        status_text.info(f"⚙️ Scraping query {i+1}/{total_queries}: '{query_cleaned}'...")
        url = f"https://www.google.com/maps/search/{quote_plus(query_cleaned)}"
        
        try:
            response = requests.get(url, headers=get_headers(), timeout=20)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'lxml')
            scraped_data = parse_google_maps_html(soup)

            if not scraped_data:
                status_text.warning(f"⚠️ No parseable results for '{query_cleaned}'. Query might be too broad/narrow, or the page was blocked.")
            else:
                for item in scraped_data:
                    item['Query'] = query_cleaned
                all_results.extend(scraped_data)

        except requests.exceptions.RequestException as e:
            status_text.error(f"❌ Network error for '{query_cleaned}': {e}")
        except Exception as e:
            status_text.error(f"❌ An unexpected error occurred for '{query_cleaned}': {e}")
        
        progress_bar.progress((i + 1) / total_queries)
        time.sleep(random.uniform(3, 6))

    if not all_results:
        status_text.error("Scraping finished, but no data was collected. This could be due to network issues, Google blocking all requests, or no results for your queries.")
    else:
        status_text.success("✅ Scraping complete!")
        
    return all_results

# --- Streamlit App UI ---
st.set_page_config(page_title="Google Maps Scraper", layout="wide", initial_sidebar_state="expanded")

st.title("🛰️ Robust Google Maps Scraper")
st.markdown("""
This app performs a **browserless** search on Google Maps. It's built to be resilient against common HTML changes.

**Instructions:**
1.  Enter search queries in the box below (one per line).
2.  Click "Start Scraping" and wait for the process to complete.
3.  Results appear in a table and can be downloaded as a CSV file.
""")

with st.form("search_form"):
    queries_input = st.text_area(
        "Enter Search Queries (one per line)",
        height=150,
        placeholder="golf clubs in new york\ncafes in paris\nhardware stores near me"
    )
    submitted = st.form_submit_button("🚀 Start Scraping", use_container_width=True)

if submitted:
    queries = [q.strip() for q in queries_input.split('\n') if q.strip()]
    
    if not queries:
        st.warning("Please enter at least one search query.")
    else:
        results = scrape_google_maps(queries)
        
        if results:
            st.success(f"Successfully scraped {len(results)} business listings.")
            df = pd.DataFrame(results)
            
            cols_order = ['Query', 'Business Name', 'Business Category', 'Rating', 'Number of Reviews', 'Address', 'Phone Number', 'Website']
            df = df[[col for col in cols_order if col in df.columns]]

            st.dataframe(df, use_container_width=True, height=500)

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv,
                file_name="google_maps_results.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("Process finished. Check messages above for details on why no data was returned.")

st.markdown("""
---
**⚠️ Disclaimer:** For educational purposes only. Automated scraping can be against a website's Terms of Service. The developer assumes no liability for misuse.
""")
