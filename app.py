# app.py
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import time
import re
from urllib.parse import quote_plus

# Initialize fake user agent
ua = UserAgent()

def scrape_google_maps(keyword, max_results=100):
    """Scrape Google Maps for businesses based on keyword"""
    # Format the search URL
    query = quote_plus(keyword)
    url = f"https://www.google.com/maps/search/{query}"
    
    headers = {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        st.error(f"Error fetching data for {keyword}: {str(e)}")
        return []
    
    soup = BeautifulSoup(response.content, 'html.parser')
    results = []
    
    # Find business listings
    listings = soup.find_all('div', class_='bfdHYd')
    
    for listing in listings[:max_results]:
        try:
            # Extract business name
            name_elem = listing.find('div', class_='qBF1Pd')
            name = name_elem.text.strip() if name_elem else "N/A"
            
            # Extract rating
            rating_elem = listing.find('span', class_='MW4etd')
            rating = rating_elem.text.strip() if rating_elem else "N/A"
            
            # Extract review count
            reviews_elem = listing.find('span', class_='UY7F9')
            reviews = reviews_elem.text.strip() if reviews_elem else "N/A"
            
            # Extract address
            address_elem = listing.find('div', class_='W4Efsd')
            address = address_elem.text.strip() if address_elem else "N/A"
            
            # Extract phone number (if available)
            phone_elem = listing.find('span', class_='UsdlK')
            phone = phone_elem.text.strip() if phone_elem else "N/A"
            
            # Extract website (if available)
            website_elem = listing.find('a', class_='lcr4fd')
            website = website_elem['href'] if website_elem else "N/A"
            
            # Extract Google Maps profile link
            profile_link_elem = listing.find('a', class_='hfpxzc')
            profile_link = profile_link_elem['href'] if profile_link_elem else "N/A"
            
            # Email is typically not directly available in search results
            email = "N/A"
            
            results.append({
                "Business Name": name,
                "Email": email,
                "Phone": phone,
                "Website": website,
                "GMB Profile Link": profile_link,
                "Rating": rating,
                "Total Reviews": reviews,
                "Address": address,
                "Keyword": keyword
            })
            
        except Exception as e:
            st.warning(f"Error parsing listing: {str(e)}")
            continue
    
    return results

def main():
    st.set_page_config(page_title="Google Maps Bulk Scraper", layout="wide")
    st.title("🗺️ Google Maps Bulk Business Scraper")
    st.markdown("Extract business details from Google Maps in bulk")
    
    # Sidebar for instructions
    with st.sidebar:
        st.header("Instructions")
        st.markdown("""
        1. Enter keywords (one per line)
        2. Click "Start Scraping"
        3. Wait for completion
        4. Download CSV file
        """)
        st.markdown("---")
        st.markdown("**Note:** This tool respects rate limits. Large batches may take time.")
    
    # Input area
    keywords_input = st.text_area(
        "Enter keywords (one per line):",
        height=200,
        placeholder="coffee shop\nrestaurant\nplumber\n..."
    )
    
    # Scraping controls
    col1, col2 = st.columns(2)
    with col1:
        max_results = st.slider("Results per keyword", 10, 100, 50, 10)
    with col2:
        delay = st.slider("Delay between requests (seconds)", 1, 10, 3)
    
    # Start scraping button
    if st.button("🚀 Start Scraping", use_container_width=True):
        if not keywords_input.strip():
            st.warning("Please enter at least one keyword")
            return
        
        keywords = [kw.strip() for kw in keywords_input.split('\n') if kw.strip()]
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, keyword in enumerate(keywords):
            status_text.info(f"Scraping: {keyword} ({i+1}/{len(keywords)})")
            results = scrape_google_maps(keyword, max_results)
            all_results.extend(results)
            progress_bar.progress((i + 1) / len(keywords))
            time.sleep(delay)  # Rate limiting
        
        # Convert to DataFrame
        df = pd.DataFrame(all_results)
        
        # Display results
        st.success(f"✅ Scraping completed! Found {len(df)} businesses")
        st.dataframe(df, use_container_width=True)
        
        # Download button
        csv = df.to_csv(index=False)
        st.download_button(
            label="💾 Download CSV",
            data=csv,
            file_name="google_maps_businesses.csv",
            mime="text/csv",
            use_container_width=True
        )

if __name__ == "__main__":
    main()
