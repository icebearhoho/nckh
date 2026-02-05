import time
import os
import random 
import pandas as pd
import concurrent.futures 
from datetime import datetime
import psycopg2 # <--- CHANGED: Postgres Driver
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException

# --- CONFIGURATION ---
MAX_WORKERS = 3

# --- DATABASE CONFIGURATION
DB_CONFIG = {
    'user': 'postgres',           
    'password': '123456789Hai@',
    'host': 'localhost',
    'database': 'agoda_reviews'
}

# --- DATABASE HELPER FUNCTIONS ---
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def get_or_create_hotel(hotel_url, hotel_name):
    """Gets the Hotel ID from DB, or creates it if it doesn't exist."""
    # Clean URL
    if "?" in hotel_url:
        clean_url = hotel_url.split("?")[0]
    else:
        clean_url = hotel_url

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Try to find existing hotel
        cursor.execute("SELECT id FROM hotels WHERE url = %s", (clean_url,))
        result = cursor.fetchone()
        
        if result:
            return result[0]
        else:
            # 2. Insert new hotel
            try:
                cursor.execute(
                    "INSERT INTO hotels (hotel_name, url, last_updated_at) VALUES (%s, %s, NOW()) RETURNING id", 
                    (hotel_name, clean_url)
                )
                new_id = cursor.fetchone()[0]
                conn.commit()
                return new_id
            except psycopg2.errors.UniqueViolation:
                # Race condition: If another worker inserted it milliseconds ago
                conn.rollback()
                cursor.execute("SELECT id FROM hotels WHERE url = %s", (clean_url,))
                return cursor.fetchone()[0]
                
    finally:
        cursor.close()
        conn.close()

def parse_agoda_date(date_text):
    """Converts 'Stayed 2 nights in August 2025' -> '2025-08-01'"""
    try:
        if " in " in date_text:
            date_part = date_text.split(" in ")[-1].strip()
        else:
            date_part = date_text.strip()
        
        # Default to 1st of the month
        dt = datetime.strptime(date_part, "%B %Y")
        return dt.strftime("%Y-%m-%d")
    except:
        return datetime.now().strftime("%Y-%m-%d") # Fallback to today

def save_batch_to_sql(hotel_id, reviews):
    """Saves a batch of reviews to PostgreSQL"""
    if not reviews: return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = """INSERT INTO comments 
             (hotel_id, author, comment_text, comment_date, score) 
             VALUES (%s, %s, %s, %s, %s)"""
             
    values = []
    for r in reviews:
        try: score_float = float(r['User Score'])
        except: score_float = 0.0
            
        values.append((
            hotel_id,
            r['Author'],
            r['Comment'],
            r['Date'],
            score_float
        ))
        
    try:
        cursor.executemany(sql, values)
        conn.commit()
        print(f"    -> Saved {len(reviews)} reviews to DB.")
    except Exception as e:
        print(f"    -> DB Error: {e}")
        conn.rollback() #reset connection after error
    finally:
        cursor.close()
        conn.close()

# --- EXISTING HOTEL URLS CHECKER ---
def get_existing_hotel_urls():
    """Returns a set of all Hotel URLs that are already in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT url FROM hotels")
        # Clean the URLs from DB just in case
        existing_urls = {row[0].split("?")[0] for row in cursor.fetchall()}
        return existing_urls
    except Exception as e:
        print(f"Error checking DB: {e}")
        return set()
    finally:
        cursor.close()
        conn.close()

# --- DRIVER SETUP ---
def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new") 
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--lang=en-US")
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    options.add_argument(f"user-agent={user_agent}")
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }})
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def kill_popups(driver):
    try:
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(random.uniform(0.5, 1.5))
    except: pass
    try:
        title = driver.find_element(By.TAG_NAME, "h1")
        driver.execute_script("arguments[0].click();", title)
    except: pass
    try:
        search_btn = driver.find_element(By.CSS_SELECTOR, "button[data-element-name='search-button']")
        if search_btn.is_displayed():
            driver.execute_script("arguments[0].click();", search_btn)
    except: pass
    keywords = ["Continue", "No thanks", "Later", "Dismiss"]
    for text in keywords:
        try:
            xpath = f"//*[contains(text(), '{text}')]"
            btn = driver.find_element(By.XPATH, xpath)
            driver.execute_script("arguments[0].click();", btn)
            break
        except: pass

# --- PART 1: LINK COLLECTOR (Unchanged) ---
def collect_hotel_links(driver, search_url):
    driver.get(search_url)
    time.sleep(random.uniform(10, 15))
    
    print(f"--- 1. STARTING LINK COLLECTION ---")
    all_links = []
    page = 1
    
    while True:
        print(f"Scraping Hotel List Page {page}...")
        for i in range(1, 15): 
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * arguments[0] / 15);", i)
                time.sleep(0.5)
            except: pass
            
        hotel_cards = driver.find_elements(By.CSS_SELECTOR, "a[href*='/hotel/']")
        current_page_links = []
        for card in hotel_cards:
            try:
                raw_url = card.get_attribute("href")
                if raw_url and "/hotel/" in raw_url:
                    if "?" in raw_url:
                        clean_url = raw_url.split("?")[0]
                    else:
                        clean_url = raw_url
                    current_page_links.append(clean_url)
            except StaleElementReferenceException:
                continue
        
        current_page_links = list(set(current_page_links))
        all_links.extend(current_page_links)
        print(f"Found {len(current_page_links)} hotels on this page.")
        
        try:
            next_btn = None
            try: next_btn = driver.find_element(By.ID, "paginationNext")
            except: pass
            
            if not next_btn:
                try: next_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Next page']")
                except: pass
            
            if next_btn:
                if "disabled" in next_btn.get_attribute("class") or next_btn.get_attribute("aria-disabled") == "true":
                    print("End of list reached.")
                    break
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(random.uniform(5, 8))
                page += 1
            else:
                print("No 'Next' button found. Stopping collection.")
                break
        except:
            break
    
    unique_links = list(set(all_links))
    print(f"Collection Complete! Found {len(unique_links)} unique hotels.\n")
    return unique_links

# --- PART 2: REVIEW SCRAPER---
def scrape_single_hotel(driver, hotel_url):
    driver.get(hotel_url)
    time.sleep(random.uniform(2, 3))
    kill_popups(driver)
    
    hotel_name = "Unknown Hotel"
    try:
        hotel_name = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-selenium='hotel-header-name']"))
        ).text
    except:
        try: hotel_name = driver.find_element(By.TAG_NAME, "h1").text
        except: pass

    # Get or create hotel in DB
    hotel_id = get_or_create_hotel(hotel_url, hotel_name)
    print(f"[{hotel_name}] Processing...")

    try:
        review_section = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "reviewSection")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", review_section)
    except: pass
    time.sleep(random.uniform(2, 3))

    review_page = 1
    last_first_author = "" 
    
    while True: 
        try:
            driver.execute_script("window.scrollBy(0, -200);")
            time.sleep(random.uniform(0.5, 1))
            review_container = driver.find_element(By.ID, "reviewSection")
            driver.execute_script("arguments[0].scrollIntoView({block: 'end'});", review_container)
            time.sleep(random.uniform(1, 2))
        except: pass

        cards = driver.find_elements(By.CSS_SELECTOR, ".Review-comment")
        if not cards: 
            print("  -> No reviews found. Stopping.")
            break

        try:
            current_first_author = cards[0].find_element(By.CSS_SELECTOR, ".Review-comment-reviewer").text
            if current_first_author == last_first_author and len(cards) > 0:
                print(f"  -> [STUCK] Page {review_page} same as previous. Moving to next hotel.")
                break
            last_first_author = current_first_author
        except: pass

        page_reviews = []
        for card in cards:
            try:
                score = "0"
                try:
                    score = card.find_element(By.CSS_SELECTOR, ".Review-comment-leftScore").text.strip()
                except:
                    try:
                        header_text = card.find_element(By.CSS_SELECTOR, ".Review-comment-leftScoreText").text
                        import re
                        match = re.search(r"(\d+(\.\d+)?)", header_text)
                        if match: score = match.group(1)
                    except: pass
                
                author = "Unknown"
                try:
                    author_element = card.find_element(By.CSS_SELECTOR, "div[data-info-type='reviewer-name'] strong")
                    author = author_element.text.strip()
                except:
                    try:
                        raw_text = card.find_element(By.CSS_SELECTOR, ".Review-comment-reviewer").text
                        if " from " in raw_text:
                            author = raw_text.split(" from ")[0].strip()
                        else:
                            author = raw_text.strip()
                    except: pass

                comment = ""
                selectors = ["[data-selenium='comment']", ".Review-comment-bodyText", ".Review-comment-body", "p[data-testid='review-comment']"]
                for sel in selectors:
                    try:
                        text_found = card.find_element(By.CSS_SELECTOR, sel).text.strip()
                        if text_found:
                            comment = text_found
                            break
                    except: continue

                raw_date = ""
                try: raw_date = card.find_element(By.CSS_SELECTOR, "div[data-info-type='stay-detail']").text.strip()
                except: pass
                
                if comment:
                    page_reviews.append({
                        "User Score": score,
                        "Author": author,
                        "Comment": comment,
                        "Date": parse_agoda_date(raw_date)
                    })
            except: continue 
        
        # Save batch to DB
        save_batch_to_sql(hotel_id, page_reviews)
        print(f"  - [{hotel_name}] Page {review_page}: Saved {len(page_reviews)} reviews.")
        time.sleep(random.uniform(1, 2))
        # Try to go to next page
        next_page_clicked = False
        next_page_num = review_page + 1
        potential_xpaths = [
            f"//div[@data-selenium='reviews-pagination']//*[text()='{next_page_num}']",
            f"//span[text()='{next_page_num}']",
            "//i[contains(@class, 'ficon-carrousel-arrow-right')]"
        ]
        # Try multiple xpaths to find the Next button
        for xpath in potential_xpaths:
            try:
                btn = driver.find_element(By.XPATH, xpath)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                time.sleep(random.uniform(0.5, 1))
                driver.execute_script("arguments[0].click();", btn)
                next_page_clicked = True
                break
            except: continue
            
        if next_page_clicked:
            time.sleep(random.uniform(2, 3.5))
            review_page += 1
        else:
            print("  -> No 'Next Page' button found. Finished Hotel.")
            break
            
    return

# --- WORKER ---
def worker_scrape_task(url):
    driver = create_driver()
    try:
        scrape_single_hotel(driver, url)
    except Exception as e:
        print(f"Error scraping {url}: {e}")
    finally:
        driver.quit()

# --- MAIN ---
def main():
    start_time = time.time()
    print("--- Phase 1: Finding Hotels ---")
    driver = create_driver()
    start_url = "https://www.agoda.com/search?city=15932&checkIn=2026-03-10&los=3&adults=1&rooms=1"    
    found_links = collect_hotel_links(driver, start_url)
    driver.quit()
    
    if not found_links:
        print("No hotels found! Exiting.")
        return

    print("\n--- Phase 2: Filtering Duplicates (Checking Postgres) ---")
    existing_urls = get_existing_hotel_urls() 
    
    hotels_to_scrape = []
    for url in found_links:
        clean_url = url.split("?")[0]
        if clean_url not in existing_urls:
            hotels_to_scrape.append(url)
            
    skipped_count = len(found_links) - len(hotels_to_scrape)
    print(f"Total Found: {len(found_links)}")
    print(f"Already Done: {skipped_count} (Skipping these!)")
    print(f"Remaining To Scrape: {len(hotels_to_scrape)}")
    
    if not hotels_to_scrape:
        print("All hotels are already in the database! Good job.")
        return

    print(f"\n--- Phase 3: Starting Scrape ({MAX_WORKERS} Workers) ---")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for i, link in enumerate(hotels_to_scrape):
            if i < MAX_WORKERS:
                print(f"  -> Staggering start: Waiting ...")
                time.sleep(random.uniform(2, 5))
            futures.append(executor.submit(worker_scrape_task, link))
            
    print(f"Done! Total time: {round((time.time() - start_time)/60, 2)} minutes.")

if __name__ == "__main__":
    main()