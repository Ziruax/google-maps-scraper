import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time
from urllib.parse import quote_plus

# Headers with random User-Agent
def get_headers():
    ua = UserAgent(fallback="Mozilla/5.0")
    return {'User-Agent': ua.random}

# Core scraper function
def scrape_query(query):
    url = f"https://www.google.com/maps/search/ {quote_plus(query)}"
    headers = get_headers()

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if 'Our systems have detected unusual traffic' in response.text:
            return [{'error': 'CAPTCHA triggered. Try again later.'}]
        
        soup = BeautifulSoup(response.text, 'html.parser')
        businesses = []

        # Extract from known containers (update class names if Google changes them)
        results = soup.find_all('div', class_='Nv2outer')
        for result in results:
            businesses.append({
                'Name': result.find('span', class_='OSrXXb')?.text.strip() or 'Not Available',
                'Address': result.find('div', class_='EI11Pd')?.text.strip() or 'Not Available',
                'Rating': result.find('span', class_='MW4etd')?.text.strip() or 'Not Available',
                'Category': result.find('span', class_='DkEjCd')?.text.strip() or 'Not Available'
            })

        return businesses or [{'error': 'No results found.'}]
    except Exception as e:
        return [{'error': f'Request failed: {str(e)}'}]

# Streamlit UI
def main():
    st.set_page_config(page_title="gMaps Scraper", layout="wide")
    st.title("gMaps Bulk Scraper (Streamlit Cloud)")
    queries = st.text_area("Search Queries", height=200, placeholder="e.g., coffee shops in Dubai\ngyms in New York...")
    start = st.button("Start Scraping")

    if start and queries:
        query_list = [q.strip() for q in queries.split('\n') if q.strip()]
        progress_bar = st.progress(0)
        status = st.empty()
        scraped_data = []

        for i, query in enumerate(query_list):
            status.text(f"Scraping: {query} ({i+1}/{len(query_list)})")
            results = scrape_query(query)
            scraped_data.extend(results)
            progress_bar.progress((i+1)/len(query_list))
            time.sleep(3)  # Avoid rate-limiting

        df = pd.DataFrame(scraped_data)
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv(index=False), "results.csv")

main()
