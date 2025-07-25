# app.py
import streamlit as st
import pandas as pd
import requests
import time
import json
import re
from urllib.parse import quote_plus
from fake_useragent import UserAgent

# Initialize fake user agent
ua = UserAgent()

def get_initial_data(keyword):
    """Get initial search results from Google Maps"""
    query = quote_plus(keyword)
    url = f"https://www.google.com/maps/search/{query}"
    
    headers = {
        'User-Agent': ua.random,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/',
        'Connection': 'keep-alive',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Extract initial data from response
        match = re.search(r'window\.APP_INITIALIZATION_STATE=(.*?);window\.APP_FLAGS', response.text)
        if match:
            data = json.loads(match.group(1))
            return data
    except Exception as e:
        st.error(f"Error fetching initial data for {keyword}: {str(e)}")
        return None

def extract_businesses_from_html(html_content, keyword):
    """Extract business information from HTML content"""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html_content, 'html.parser')
    businesses = []
    
    # Find all business listings
    listings = soup.find_all('div', {'class': 'bfdHYd'})
    
    for listing in listings:
        try:
            # Business Name
            name_elem = listing.find('div', {'class': 'qBF1Pd'})
            name = name_elem.text.strip() if name_elem else "N/A"
            
            # Rating
            rating_elem = listing.find('span', {'class': 'MW4etd'})
            rating = rating_elem.text.strip() if rating_elem else "N/A"
            
            # Reviews Count
            reviews_elem = listing.find('span', {'class': 'UY7F9'})
            reviews = reviews_elem.text.strip().replace('(', '').replace(')', '') if reviews_elem else "N/A"
            
            # Address/Category
            address_elem = listing.find('div', {'class': 'W4Efsd'})
            address = address_elem.text.strip() if address_elem else "N/A"
            
            # Phone Number
            phone_elem = listing.find('span', {'class': 'UsdlK'})
            phone = phone_elem.text.strip() if phone_elem else "N/A"
            
            # Website
            website_elem = listing.find('a', {'class': 'lcr4fd'})
            website = website_elem.get('href') if website_elem else "N/A"
            
            # Profile Link
            profile_elem = listing.find('a', {'class': 'hfpxzc'})
            profile_link = profile_elem.get('href') if profile_elem else "N/A"
            
            # Email (not typically available in search results)
            email = "N/A"
            
            businesses.append({
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
    
    return businesses

def scrape_with_pagination(keyword, max_pages=5):
    """Scrape Google Maps with pagination simulation"""
    businesses = []
    session = requests.Session()
    
    headers = {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    session.headers.update(headers)
    
    query = quote_plus(keyword)
    base_url = f"https://www.google.com/maps/search/{query}"
    
    try:
        response = session.get(base_url, timeout=15)
        response.raise_for_status()
        
        # Extract businesses from initial page
        page_businesses = extract_businesses_from_html(response.text, keyword)
        businesses.extend(page_businesses)
        
        # Try to get more results by simulating scroll/pagination
        # This is a simplified approach - in reality, Google Maps uses complex JS
        for page in range(1, max_pages):
            # Add delay to simulate human behavior
            time.sleep(2)
            
            # Try to get next page (this is a simplified approach)
            next_url = f"{base_url}?page={page+1}"
            try:
                next_response = session.get(next_url, timeout=15)
                next_response.raise_for_status()
                
                next_businesses = extract_businesses_from_html(next_response.text, keyword)
                if not next_businesses:
                    break  # No more results
                
                businesses.extend(next_businesses)
            except:
                break  # Stop if we can't get more pages
                
    except requests.RequestException as e:
        st.error(f"Error scraping {keyword}: {str(e)}")
    
    return businesses

def scrape_google_maps_api_approach(keyword):
    """Alternative approach using Google's internal APIs"""
    businesses = []
    
    # This is a simplified simulation - actual implementation would need
    # to reverse-engineer Google's internal API calls
    
    query = quote_plus(keyword)
    search_url = f"https://www.google.com/maps/search/{query}"
    
    headers = {
        'User-Agent': ua.random,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/',
        'X-Requested-With': 'XMLHttpRequest',
    }
    
    try:
        response = requests.get(search_url, headers=headers, timeout=15)
        businesses = extract_businesses_from_html(response.text, keyword)
    except Exception as e:
        st.error(f"Error with API approach for {keyword}: {str(e)}")
    
    return businesses

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
        st.markdown("**Note:** Results depend on Google's current HTML structure")
    
    # Input area
    keywords_input = st.text_area(
        "Enter keywords (one per line):",
        height=200,
        placeholder="coffee shop\nrestaurant\nplumber\n..."
    )
    
    # Scraping controls
    col1, col2 = st.columns(2)
    with col1:
        delay = st.slider("Delay between requests (seconds)", 1, 10, 3)
    with col2:
        max_pages = st.slider("Max pages per keyword", 1, 10, 3)
    
    # Start scraping button
    if st.button("🚀 Start Scraping", use_container_width=True):
        if not keywords_input.strip():
            st.warning("Please enter at least one keyword")
            return
        
        keywords = [kw.strip() for kw in keywords_input.split('\n') if kw.strip()]
        if not keywords:
            st.warning("Please enter valid keywords")
            return
        
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, keyword in enumerate(keywords):
            status_text.info(f"Scraping: {keyword} ({i+1}/{len(keywords)})")
            
            # Try different approaches
            results = scrape_with_pagination(keyword, max_pages)
            
            # If first approach fails, try alternative
            if not results:
                results = scrape_google_maps_api_approach(keyword)
            
            all_results.extend(results)
            progress_bar.progress((i + 1) / len(keywords))
            
            # Delay between requests
            if i < len(keywords) - 1:
                time.sleep(delay)
        
        # Convert to DataFrame
        if all_results:
            df = pd.DataFrame(all_results)
            
            # Remove duplicates based on business name and address
            df = df.drop_duplicates(subset=['Business Name', 'Address'])
            
            # Display results
            st.success(f"✅ Scraping completed! Found {len(df)} unique businesses")
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
        else:
            st.warning("No businesses found. Try different keywords or check your connection.")

if __name__ == "__main__":
    main()
