import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time
from urllib.parse import quote_plus

# Helper function to safely extract text from BeautifulSoup elements
def safe_get_text(element):
    return element.text.strip() if element else "Not Available"

# Headers with random User-Agent
def get_headers():
    ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    return {'User-Agent': ua.random}

# Core scraper function
def scrape_query(query):
    base_url = "https://www.google.com/maps/search/ "
    url = f"{base_url}{quote_plus(query)}"
    headers = get_headers()

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        if 'Our systems have detected unusual traffic' in response.text:
            return [{'error': 'CAPTCHA triggered. Try again later.'}]

        soup = BeautifulSoup(response.text, 'lxml')
        businesses = []

        # Extract results from known containers
        results = soup.find_all('div', class_='Nv2outer')
        
        for result in results:
            # Find all required elements
            name_tag = result.find('span', class_='OSrXXb')
            address_tag = result.find('div', class_='EI11Pd')
            rating_tag = result.find('span', class_='MW4etd')
            review_tag = result.find('span', class_='UYEzZb')
            category_tag = result.find('span', class_='DkEjCd')

            businesses.append({
                'Business Name': safe_get_text(name_tag),
                'Business Email': 'Not Available',
                'Phone Number': 'Not Available',
                'Website URL': 'No website',
                'Business Address': safe_get_text(address_tag),
                'Business Rating': safe_get_text(rating_tag),
                'Number of Reviews': safe_get_text(review_tag),
                'Business Category': safe_get_text(category_tag)
            })

        if not businesses:
            return [{'error': 'No results found for this query.'}]

        return businesses

    except requests.RequestException as e:
        return [{'error': f'Request failed: {str(e)}'}]
    except Exception as e:
        return [{'error': f'Error: {str(e)}'}]

# Streamlit UI
def main():
    st.set_page_config(page_title="gMaps Scraper", layout="wide")
    st.title("gMaps Bulk Scraper (Streamlit Cloud)")
    st.markdown("Enter multiple search queries (one per line) to extract business data from Google Maps.")

    queries = st.text_area("Search Queries", height=200, placeholder="e.g., coffee shops in Dubai\ngyms in New York...")
    start_scraping = st.button("Start Scraping")

    if start_scraping and queries:
        query_list = [q.strip() for q in queries.split('\n') if q.strip()]
        if not query_list:
            st.warning("Please enter at least one search query.")
            return

        progress_bar = st.progress(0)
        status_text = st.empty()
        scraped_data = []
        total_queries = len(query_list)

        for i, query in enumerate(query_list):
            status_text.text(f"Scraping: {query} ({i+1}/{total_queries})")
            businesses = scrape_query(query)
            if businesses and 'error' in businesses[0]:
                scraped_data.append({
                    'Business Name': 'Error',
                    'Business Email': businesses[0]['error'],
                    'Phone Number': '',
                    'Website URL': '',
                    'Business Address': '',
                    'Business Rating': '',
                    'Number of Reviews': '',
                    'Business Category': ''
                })
            else:
                scraped_data.extend(businesses)
            progress_bar.progress((i+1)/total_queries)
            time.sleep(3)  # Rate limiting

        if scraped_data:
            df = pd.DataFrame(scraped_data)
            st.dataframe(df)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name='google_maps_data.csv',
                mime='text/csv'
            )
        else:
            st.error("No data could be scraped from the queries provided.")
    elif start_scraping:
        st.warning("Please enter some search queries.")

if __name__ == "__main__":
    main()
