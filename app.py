# app.py
import streamlit as st
import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from fake_useragent import UserAgent
import tempfile
import os

# Setup Chrome options for headless browsing
@st.cache_resource
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    ua = UserAgent()
    chrome_options.add_argument(f'--user-agent={ua.random}')
    return webdriver.Chrome(options=chrome_options)

def scroll_to_bottom(driver, pause_time=2):
    """Scroll to the bottom of the page to load all results"""
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    while True:
        # Scroll down to bottom
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        
        # Wait to load page
        time.sleep(pause_time)
        
        # Calculate new scroll height and compare to last height
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def extract_business_info(driver, keyword):
    """Extract business information from search results"""
    businesses = []
    
    try:
        # Wait for results to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "bfdHYd"))
        )
    except:
        st.warning(f"No results found for: {keyword}")
        return businesses
    
    # Scroll to load all results
    scroll_to_bottom(driver)
    
    # Find all business listings
    listings = driver.find_elements(By.CLASS_NAME, "bfdHYd")
    
    for listing in listings:
        try:
            # Business Name
            try:
                name_elem = listing.find_element(By.CLASS_NAME, "qBF1Pd")
                name = name_elem.text.strip()
            except:
                name = "N/A"
            
            # Rating
            try:
                rating_elem = listing.find_element(By.CLASS_NAME, "MW4etd")
                rating = rating_elem.text.strip()
            except:
                rating = "N/A"
            
            # Reviews Count
            try:
                reviews_elem = listing.find_element(By.CLASS_NAME, "UY7F9")
                reviews = reviews_elem.text.strip().replace("(", "").replace(")", "")
            except:
                reviews = "N/A"
            
            # Address and Category
            try:
                address_elem = listing.find_element(By.CLASS_NAME, "W4Efsd")
                address_info = address_elem.text.strip()
            except:
                address_info = "N/A"
            
            # Phone Number
            try:
                phone_elem = listing.find_element(By.CLASS_NAME, "UsdlK")
                phone = phone_elem.text.strip()
            except:
                phone = "N/A"
            
            # Website
            try:
                website_elem = listing.find_element(By.CLASS_NAME, "lcr4fd")
                website = website_elem.get_attribute("href")
            except:
                website = "N/A"
            
            # Profile Link
            try:
                profile_elem = listing.find_element(By.CLASS_NAME, "hfpxzc")
                profile_link = profile_elem.get_attribute("href")
            except:
                profile_link = "N/A"
            
            # Email (usually not available in search results)
            email = "N/A"
            
            businesses.append({
                "Business Name": name,
                "Email": email,
                "Phone": phone,
                "Website": website,
                "GMB Profile Link": profile_link,
                "Rating": rating,
                "Total Reviews": reviews,
                "Address": address_info,
                "Keyword": keyword
            })
            
        except Exception as e:
            st.warning(f"Error extracting business info: {str(e)}")
            continue
    
    return businesses

def scrape_keyword(driver, keyword):
    """Scrape businesses for a single keyword"""
    search_url = f"https://www.google.com/maps/search/{keyword.replace(' ', '+')}"
    
    try:
        driver.get(search_url)
        time.sleep(3)  # Allow page to load
        
        businesses = extract_business_info(driver, keyword)
        return businesses
    
    except Exception as e:
        st.error(f"Error scraping {keyword}: {str(e)}")
        return []

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
        st.markdown("**Note:** This tool may take several minutes for large keyword lists.")
    
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
        scroll_pause = st.slider("Scroll pause time (seconds)", 1, 5, 2)
    
    # Start scraping button
    if st.button("🚀 Start Scraping", use_container_width=True):
        if not keywords_input.strip():
            st.warning("Please enter at least one keyword")
            return
        
        keywords = [kw.strip() for kw in keywords_input.split('\n') if kw.strip()]
        if not keywords:
            st.warning("Please enter valid keywords")
            return
        
        # Initialize driver
        with st.spinner("Initializing browser..."):
            try:
                driver = setup_driver()
            except Exception as e:
                st.error(f"Failed to initialize browser: {str(e)}")
                return
        
        all_results = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            for i, keyword in enumerate(keywords):
                status_text.info(f"Scraping: {keyword} ({i+1}/{len(keywords)})")
                
                # Scrape keyword
                results = scrape_keyword(driver, keyword)
                all_results.extend(results)
                
                progress_bar.progress((i + 1) / len(keywords))
                
                # Delay between requests
                if i < len(keywords) - 1:  # No delay after last keyword
                    time.sleep(delay)
            
            # Close driver
            driver.quit()
            
            # Convert to DataFrame
            if all_results:
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
            else:
                st.warning("No businesses found for the given keywords")
                
        except Exception as e:
            st.error(f"An error occurred during scraping: {str(e)}")
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    main()
