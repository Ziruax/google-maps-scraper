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
    This version is updated to handle recent changes in Google's HTML structure.
    """
    results = []
    # Find the main container for search results using a more stable attribute
    main_container = soup.find('div', {'role': 'feed'})
    
    if not main_container:
        # Check for a "Before you continue" page which indicates a block or CAPTCHA
        if "Before you continue" in soup.title.string:
            st.error("Google is blocking the request (CAPTCHA). Try again later or from a different network.")
        else:
            st.warning("Could not find the main results container on the page. The page structure may have changed.")
        return []

    # Find all individual result items. We look for links to places.
    place_links = main_container.find_all('a', href=re.compile(r'/maps/place/'))
    
    processed_links = set()

    for link in place_links:
        href = link.get('href')
        if href in processed_links:
            continue
        processed_links.add(href)
        
        # The parent div of the link usually contains all info for one result
        result_container = link.find_parent('div').find_parent('div')
        if not result_container:
            continue
            
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

        # --- Extract Business Name ---
        try:
            data['Business Name'] = link.get('aria-label', 'Not Available').strip()
        except AttributeError:
            continue # Skip if no name is found

        # --- Extract other details from the text within the container ---
        container_text_parts = result_container.get_text(separator=' · ', strip=True).split(' · ')
        
        # --- Extract Rating and Number of Reviews ---
        for part in container_text_parts:
            if '★' in part:
                try:
                    rating_reviews = part.split('★')
                    data['Rating'] = rating_reviews[0].strip()
                    review_match = re.search(r'\((\d{1,3}(?:,\d{3})*)\)', rating_reviews[1])
                    if review_match:
                        data['Number of Reviews'] = review_match.group(1).replace(',', '')
                    break
                except (IndexError, ValueError):
                    pass
        
        # --- Extract Phone Number ---
        for part in container_text_parts:
            # A common pattern for US phone numbers
            phone_match = re.search(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', part)
            if phone_match:
                data['Phone Number'] = phone_match.group(0)
                break
        
        # --- Extract Category and Address ---
        # This is heuristic, based on common patterns.
        # Address usually contains numbers (street number, zip code) and is longer.
        # Category is often one of the first few text parts and doesn't contain a rating star.
        address_parts = []
        for part in container_text_parts:
            if '★' in part or data['Phone Number'] in part or data['Business Name'] in part:
                continue
            
            # Simple check for an address-like string
            if any(char.isdigit() for char in part) and len(part) > 8:
                 address_parts.append(part)
            # A simple heuristic for category
            elif not any(char.isdigit() for char in part) and len(part) > 2 and len(part) < 30 and data['Business Category'] == 'Not Available':
                data['Business Category'] = part

        if address_parts:
            data['Address'] = " ".join(address_parts)
            
        # --- Extract Website ---
        # Website link is often found in a link with a 'data-value="Website"' attribute
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
                status_text.warning(f"⚠️ No results found for '{query_cleaned}'. The query might be too specific or the page was blocked.")
            else:
                for item in scraped_data:
                    item['Query'] = query_cleaned # Add the original query to each result
                all_results.extend(scraped_data)

        except requests.exceptions.RequestException as e:
            status_text.error(f"❌ Network error for '{query_cleaned}': {e}")
        except Exception as e:
            status_text.error(f"❌ An unexpected error occurred for '{query_cleaned}': {e}")
        
        progress_bar.progress((i + 1) / total_queries)
        # Use a longer, more random sleep time to be safer
        time.sleep(random.uniform(3, 6))

    if not all_results:
        status_text.error("Scraping finished, but no data was collected. This could be due to network issues, Google blocking requests, or no results for any of your queries.")
    else:
        status_text.success("✅ Scraping complete!")
        
    return all_results

# --- Streamlit App UI ---

st.set_page_config(page_title="Google Maps Scraper", layout="wide", initial_sidebar_state="expanded")

st.title("🛰️ Unlimited Google Maps Scraper")
st.markdown("""
This app performs a **browserless** search on Google Maps for your queries. It's lightweight, built for Streamlit Cloud, and does not use Selenium.

**How to Use:**
1.  Enter your search queries in the text box below (one per line).
2.  Click the "Start Scraping" button.
3.  Results will appear in a table, ready for download.

*Example queries: `golf clubs in new york`, `cafes in paris`, `hardware stores near me`*

---
""")

# --- User Input & Controls ---
with st.form("search_form"):
    queries_input = st.text_area(
        "Enter Search Queries (one per line)",
        height=150,
        placeholder="Coffee shops in Dubai\nGyms in New York\nBookstores in London"
    )
    submitted = st.form_submit_button("🚀 Start Scraping", use_container_width=True)

# --- Main App Logic & Results Display ---
if submitted:
    queries = [q.strip() for q in queries_input.split('\n') if q.strip()]
    
    if not queries:
        st.warning("Please enter at least one search query.")
    else:
        with st.spinner("Initializing scraper... Please wait. This can take a few minutes depending on the number of queries."):
            results = scrape_google_maps(queries)
        
        if results:
            st.success(f"Successfully scraped {len(results)} results.")
            
            df = pd.DataFrame(results)
            
            # Reorder columns for a clean presentation
            cols_order = ['Query', 'Business Name', 'Business Category', 'Rating', 'Number of Reviews', 'Address', 'Phone Number', 'Website']
            # Filter df to only include columns that exist, in the desired order
            df = df[[col for col in cols_order if col in df.columns]]

            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv,
                file_name="google_maps_results.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            # The specific error/warning messages are now handled inside the scrape function
            st.info("Process finished. Check messages above for details.")

st.markdown("""
---
**⚠️ Disclaimer:** This tool is for educational and experimental purposes only. Automated scraping may be against Google's Terms of Service. The developer assumes no liability for misuse. The HTML structure of Google Maps can change at any time, which may cause this tool to stop working.
""")
