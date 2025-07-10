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

def parse_business_data(soup):
    """Parses the HTML soup to extract business data."""
    results = []
    
    # Find all result containers. Google's class names are obfuscated and change.
    # We target a div that consistently appears as a container for each search result.
    # The 'jslog' attribute seems to be a stable identifier for result items.
    for result in soup.find_all('div', {'jslog': re.compile(r'.*')}):
        
        # Initialize dictionary with default values
        data = {
            'Business Name': 'Not Available',
            'Business Category': 'Not Available',
            'Address': 'Not Available',
            'Website': 'No Website',
            'Phone Number': 'Not Available',
            'Rating': 'Not Available',
            'Number of Reviews': 'Not Available',
            'Business Email': 'Not Available' # Email is almost never public on the search page
        }

        # --- Extract Business Name ---
        name_tag = result.find('a', {'aria-label': True})
        if name_tag:
            data['Business Name'] = name_tag['aria-label']
        else:
            # Skip divs that are not actual business listings
            continue 

        # --- Extract Other Information from the result block ---
        # The info is usually in a sibling or child div. We'll get all text and parse.
        info_block = result.find_all('div')
        
        # Combine all text from divs within the result for easier searching
        # This is a robust way to handle variations in Google's HTML structure
        full_text_content = " ".join([div.text for div in info_block])

        # --- Extract Rating and Number of Reviews ---
        rating_match = re.search(r'(\d\.\d)\s?★', full_text_content)
        if rating_match:
            data['Rating'] = rating_match.group(1)
        
        reviews_match = re.search(r'\((\d+,?\d*)\)', full_text_content)
        if reviews_match:
            data['Number of Reviews'] = reviews_match.group(1).replace(',', '')

        # --- Extract Category, Address, etc. using regex on combined text ---
        # This part is tricky because the order is not guaranteed.
        # We look for common patterns.
        
        # Phone Number (matches various formats)
        phone_match = re.search(r'(\+?\d{1,3}[-\.\s]?)?\(?\d{3}\)?[-\.\s]?\d{3}[-\.\s]?\d{4}', full_text_content)
        if phone_match:
            data['Phone Number'] = phone_match.group(0)

        # Category and Address are often together
        # We find the rating span and look at its neighbors, but regex on the block is more stable.
        lines = [line.strip() for line in full_text_content.split('·') if line.strip()]
        if len(lines) > 1:
            # Often, the category is the first item after the review count
            # Heuristic: The category is usually a short phrase without numbers.
            potential_category = lines[0]
            if not any(char.isdigit() for char in potential_category) and len(potential_category) < 50:
                 data['Business Category'] = potential_category.replace(data['Rating'], '').replace(data['Number of Reviews'], '').strip('() ')
            
            # Heuristic: Address is usually one of the longer strings containing numbers.
            for line in lines:
                if any(char.isdigit() for char in line) and len(line) > 10 and not phone_match:
                    data['Address'] = line
                    break

        # --- Extract Website ---
        # Website is usually in a link with a specific 'data-value'
        website_tag = result.find('a', {'data-value': 'Website'})
        if website_tag and website_tag.get('href'):
            data['Website'] = website_tag['href']
        
        # Avoid duplicate entries if the same div is processed multiple times
        if data not in results:
            results.append(data)

    return results

def scrape_google_maps(queries):
    """Main function to orchestrate the scraping process."""
    all_results = []
    total_queries = len(queries)
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, query in enumerate(queries):
        status_text.info(f"⚙️ Scraping query {i+1}/{total_queries}: '{query}'...")
        
        url = f"https://www.google.com/maps/search/{quote_plus(query)}"
        
        try:
            response = requests.get(url, headers=get_headers(), timeout=15)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # The actual useful data is often embedded in a script tag as a giant string.
            # We need to find the right script tag and parse its content.
            scripts = soup.find_all('script')
            data_script = None
            for script in scripts:
                if script.string and 'window.APP_INITIALIZATION_STATE' in script.string:
                    data_script = script.string
                    break
            
            if not data_script:
                # Fallback to parsing the visible HTML if the main data script isn't found
                st.warning(f"Could not find detailed data for '{query}'. Parsing basic HTML. Results may be limited.")
                scraped_data = parse_business_data(soup)
            else:
                 # This is the complex part. The data is in a JS object.
                 # We use regex to extract the main data list.
                 # This regex is designed to find the list of search results.
                match = re.search(r'window\.APP_INITIALIZATION_STATE=\s*(\[.+?\]);', data_script)
                if match:
                    # This part is highly experimental and brittle due to Google's structure
                    # For this lightweight app, we will rely on the direct HTML parsing which is more stable
                    # A more advanced version would need to parse the complex JS object.
                    # For now, we stick with the `parse_business_data` on the whole soup.
                    scraped_data = parse_business_data(soup)
                else:
                    scraped_data = parse_business_data(soup)

            if not scraped_data:
                status_text.warning(f"⚠️ No results found for '{query}'. It might be a protected query or have no listings.")
            else:
                for item in scraped_data:
                    item['Query'] = query # Add the original query to each result
                all_results.extend(scraped_data)

        except requests.exceptions.RequestException as e:
            status_text.error(f"❌ Failed to fetch data for '{query}'. Error: {e}")
        
        # Update progress and sleep to be respectful to the server
        progress_bar.progress((i + 1) / total_queries)
        time.sleep(random.uniform(2.5, 5.5))

    status_text.success("✅ Scraping complete!")
    return all_results

# --- Streamlit App UI ---

st.set_page_config(page_title="Lightweight Google Maps Scraper", layout="wide")

st.title("🛰️ Lightweight Google Maps Scraper")
st.markdown("""
This app performs a **browserless** search on Google Maps for your queries. 
It's lightweight and designed for Streamlit Cloud.

**Instructions:**
1.  Enter one search query per line (e.g., `Coffee shops in Dubai`).
2.  Click "Start Scraping".
3.  Results will appear below, and you can download them as a CSV file.

⚠️ **Disclaimer:** This is for educational purposes. Scraping can be against Google's ToS. 
The structure of Google's HTML can change, which may break the scraper.
""")

# --- User Input & Controls ---
with st.form("search_form"):
    queries_input = st.text_area(
        "Enter Search Queries (one per line)", 
        height=150,
        placeholder="Coffee shops in Dubai\nGyms in New York\nBookstores in London"
    )
    submitted = st.form_submit_button("🚀 Start Scraping")

# --- Main App Logic ---
if submitted:
    queries = [q.strip() for q in queries_input.split('\n') if q.strip()]
    
    if not queries:
        st.warning("Please enter at least one search query.")
    else:
        with st.spinner("Initializing scraper... This may take a moment."):
            results = scrape_google_maps(queries)
        
        if results:
            st.success(f"Found {len(results)} results.")
            
            # Convert results to DataFrame
            df = pd.DataFrame(results)
            
            # Reorder columns for better readability
            cols_order = ['Query', 'Business Name', 'Business Category', 'Address', 'Website', 'Phone Number', 'Rating', 'Number of Reviews', 'Business Email']
            df = df[cols_order]

            # Display results in an interactive table
            st.dataframe(df)

            # Provide a download button for the CSV
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv,
                file_name="google_maps_results.csv",
                mime="text/csv",
            )
        else:
            st.error("No data could be scraped. Please check your queries or try again later.")
