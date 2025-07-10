import streamlit as st
import pandas as pd
import time
import re
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager, ChromeType
from fake_useragent import UserAgent
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def scrape_query(query):
    ua = UserAgent()
    chrome_options = Options()
    chrome_options.add_argument(f'user-agent={ua.random}')
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    search_url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
    driver.get(search_url)
    
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "hfpxzc"))
        )
    except:
        driver.quit()
        return []
    
    listings = driver.find_elements(By.CLASS_NAME, "hfpxzc")[:5]  # Limit to 5 businesses
    business_data = []
    
    for listing in listings:
        try:
            listing_url = listing.get_attribute("href")
            driver.get(listing_url)
            time.sleep(5)  # Delay to mimic human behavior
            
            name = driver.find_element(By.TAG_NAME, "h1").text if driver.find_elements(By.TAG_NAME, "h1") else "N/A"
            
            address_elem = driver.find_elements(By.XPATH, "//button[@data-item-id='address']")
            address = address_elem[0].get_attribute("aria-label").replace("Address: ", "") if address_elem else "N/A"
            
            phone_elem = driver.find_elements(By.XPATH, "//button[contains(@data-item-id, 'phone')]")
            phone = phone_elem[0].get_attribute("aria-label").replace("Phone: ", "") if phone_elem else "N/A"
            
            website_elem = driver.find_elements(By.XPATH, "//a[@data-item-id='authority']")
            website_url = website_elem[0].get_attribute("href") if website_elem else "N/A"
            
            email = "N/A"
            if website_url != "N/A":
                try:
                    response = requests.get(website_url, headers={'User-Agent': ua.random}, timeout=5)
                    if response.status_code == 200:
                        website_soup = BeautifulSoup(response.text, 'html.parser')
                        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', website_soup.text)
                        email = emails[0] if emails else "N/A"
                except:
                    email = "N/A"
            
            business_data.append({
                "Name": name,
                "Address": address,
                "Phone": phone,
                "Website": website_url,
                "Email": email
            })
        except Exception as e:
            continue
    
    driver.quit()
    return business_data

st.title("Google Maps Scraper")
st.markdown("""
**Instructions:**
- Enter multiple search queries, one per line (e.g., 'restaurants in New York', 'plumbers in Los Angeles').
- The scraper will process each query and collect data for up to 5 businesses per query.
- Scraping may take several minutes depending on the number of queries.
- Keep this tab open until the process completes.
""")
st.markdown("""
**Note:**
- If errors occur, it might be due to changes in Google Maps' structure or rate limiting.
- Try reducing the number of queries or waiting before retrying.
""")

queries = st.text_area("Search Queries", height=150)
if st.button("Start Scraping"):
    if queries:
        query_list = [q.strip() for q in queries.split('\n') if q.strip()]
        all_data = []
        placeholder = st.empty()
        for i, query in enumerate(query_list):
            placeholder.write(f"Processing query {i+1}/{len(query_list)}: {query}")
            try:
                data = scrape_query(query)
                all_data.extend(data)
            except Exception as e:
                st.error(f"Error processing query '{query}': {str(e)}")
            time.sleep(5)  # Delay between queries
        placeholder.write("Scraping complete!")
        if all_data:
            df = pd.DataFrame(all_data)
            csv = df.to_csv(index=False, encoding='utf-8')
            st.success(f"Scraped {len(all_data)} businesses successfully!")
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="google_maps_data.csv",
                mime="text/csv"
            )
        else:
            st.error("No data found. Please check your queries or try again later.")
    else:
        st.error("Please enter at least one query.")
