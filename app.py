import time
import logging
import os
import traceback
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# USING SELENIUM-WIRE TO ALLOW PREMIUM AUTHENTICATED PROXIES
from seleniumwire import webdriver 
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# =====================================================================
# LOGGING CONFIGURATION
# =====================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

def step(msg: str):
    log.info(f"{'─' * 60}\n  ▶  {msg}\n{'─' * 60}")

def ok(msg: str):
    log.info(f"  ✔  {msg}")

def warn(msg: str):
    log.warning(f"  ⚠  {msg}")

def fail(msg: str):
    log.error(f"  ✖  {msg}")

# =====================================================================
# SECURE CONFIGURATION & SETTINGS
# =====================================================================

WEBPT_URL     = "https://app.webpt.com"
WAIT_TIMEOUT  = 20
DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads")

# Load secure credentials from Streamlit Cloud Secrets safely
try:
    USERNAME       = st.secrets["WEBPT_USERNAME"]
    PASSWORD       = st.secrets["WEBPT_PASSWORD"]
    
    # Premium Proxy Configurations
    PROXY_USER     = st.secrets["PROXY_USER"]
    PROXY_PASS     = st.secrets["PROXY_PASS"]
    PROXY_ENDPOINT = st.secrets["PROXY_ENDPOINT"]
    USE_PROXY      = True
except Exception as e:
    # Fallback placeholders for local environments
    USERNAME      = "Mahmoudabdelaziz.CC"
    PASSWORD      = "CityPT10$"
    USE_PROXY     = False
    warn("Could not load secrets from Streamlit Cloud. Operating without Proxy context.")

# =====================================================================
# PANDAS DATA PROCESSING
# =====================================================================

def process_downloaded_data(csv_path):
    step("Processing CSV Data with Pandas")
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')

        df = df.map(
            lambda x: x.replace('\u201a', ',').replace('â€š', ',')
            if isinstance(x, str) else x
        )
        ok("Replaced all corrupted commas with regular commas")

        target_columns = [
            "Patient ID", "Patient Name", "Clinic Name",
            "Treating Therapist", "Appointment Type",
            "Appointment Date", "Visit Status"
        ]
        df = df[target_columns]

        df["Appointment Date"] = pd.to_datetime(df["Appointment Date"], errors="coerce")
        df = df.sort_values(
            by=["Visit Status", "Appointment Date", "Clinic Name"],
            ascending=[True, True, True]
        )
        df["Appointment Date"] = df["Appointment Date"].dt.strftime("%Y-%m-%d")

        df.to_csv(csv_path, index=False, encoding='utf-8')
        ok(f"File processed and overwritten at: {csv_path}")
        return csv_path
        
    except Exception as e:
        fail(f"Pandas processing failed: {e}")
        return None

# =====================================================================
# DRIVER CREATION (PREMIUM AUTHENTICATED PROXY MIGRATION)
# =====================================================================

def create_driver() -> webdriver.Chrome:
    step("Launching Headless Chrome browser via Authenticated Premium Proxy")
    options = webdriver.ChromeOptions()
    
    # Headless Environment Configurations
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking") 
    
    prefs = {
        "download.default_directory": DOWNLOAD_PATH,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.geolocation": 1 
    }
    options.add_experimental_option("prefs", prefs)
    
    # Build Selenium-Wire parameters to pass the username & password securely
    wire_options = {}
    if USE_PROXY:
        log.info(f"  → Tunneling network traffic through private proxy node...")
        proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_ENDPOINT}"
        wire_options = {
            'proxy': {
                'http': proxy_url,
                'https': proxy_url,
                'no_proxy': 'localhost,127.0.0.1'
            }
        }

    # Initialize driver based on execution environment
    if os.name == 'posix': 
        options.binary_location = "/usr/bin/chromium"
        driver = webdriver.Chrome(options=options, seleniumwire_options=wire_options)
    else:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options,
            seleniumwire_options=wire_options
        )
        
    # Force Internal Browser Geolocation API to align with NY physical coordinates
    log.info("  → Aligning device GPS coordinates with New York City baseline...")
    ny_coordinates = {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "accuracy": 100
    }
    driver.execute_cdp_cmd("Emulation.setGeolocationOverride", ny_coordinates)
    
    ok("Headless browser loaded securely within New York context!")
    return driver

# =====================================================================
# DOWNLOAD WATCHER
# =====================================================================

def wait_for_new_csv(download_dir, before_files, timeout=120):
    log.info(f"  →  Waiting for the file to download...")
    end_time = time.time() + timeout
    
    while time.time() < end_time:
        current_files = set(os.listdir(download_dir))
        new_files = current_files - before_files
        
        new_csvs = [f for f in new_files if f.endswith('.csv')]
        active_downloads = [f for f in new_files if f.endswith('.crdownload') or f.endswith('.tmp')]
        
        if new_csvs and not active_downloads:
            time.sleep(2)
            file_name = new_csvs[0]
            ok(f"Download complete: {file_name}")
            return os.path.join(download_dir, file_name)
        time.sleep(1)
        
    warn("Download timed out.")
    return None

# =====================================================================
# NAVIGATION & ACTIONS
# =====================================================================

def login(driver, wait):
    step("Logging in to WebPT")
    driver.get(WEBPT_URL)
    
    wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(USERNAME)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    wait.until(EC.presence_of_element_located((By.ID, "password"))).send_keys(PASSWORD)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    time.sleep(5) 
    try:
        oust_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Yes, oust them!')]")
        driver.execute_script("arguments[0].click();", oust_btn)
        ok("Clicked 'Yes, oust them!' button")
    except:
        log.info("No 'Oust' prompt appeared.")

    wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Advanced Search")))
    ok("Login successful")

def open_analytics(driver, wait):
    step("Opening Analytics tab")
    main_window = driver.current_window_handle
    
    btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".analytics-icon")))
    driver.execute_script("arguments[0].click();", btn)
    
    wait.until(EC.new_window_is_opened([main_window]))
    new_window = [w for w in driver.window_handles if w != main_window][0]
    driver.switch_to.window(new_window)
    
    WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    ok("Switched to Analytics dashboard")

def locate_options_button(driver, long_wait):
    try:
        btn = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "OptionsBtn"))
        )
        log.info("Options button found in main content")
        return btn
    except:
        log.info("Options not in default content – checking iframes")

    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    log.info(f"Found {len(iframes)} iframes")
    for idx, iframe in enumerate(iframes):
        try:
            driver.switch_to.frame(iframe)
            btn = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.ID, "OptionsBtn"))
            )
            log.info(f"Found Options button inside iframe #{idx}")
            return btn
        except:
            driver.switch_to.default_content()
    return None

def navigate_scheduled_visits(driver, wait):
    step("Navigating to Scheduled Visits Report")
    long_wait = WebDriverWait(driver, 60)
    short_wait = WebDriverWait(driver, 15)

    page_loaded = False
    max_attempts = 3

    for attempt in range(max_attempts):
        log.info(f"  → Attempt {attempt + 1} of {max_attempts} to click Scheduled Visits...")
        try:
            reports_menu = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
                (By.XPATH, "//div[@id='REPORTS'] | //div[text()='REPORTS']")
            ))
            driver.execute_script("arguments[0].click();", reports_menu)
            time.sleep(1.5)

            sv_xpath = "//div[@id='scheduled_visits']//span[text()='Scheduled Visits'] | //div[@id='scheduled_visits']"
            sv_link = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, sv_xpath)))
            
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sv_link)
            time.sleep(0.5)
            
            try:
                sv_link.click()
            except:
                driver.execute_script("arguments[0].click();", sv_link)

            step("Checking if the click registered...")
            short_wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, ".k-grid, #reportContainer, #OptionsBtn")
            ))
            
            ok("Confirmed: Scheduled Visits page is loading!")
            page_loaded = True
            break
            
        except Exception as e:
            warn("The click didn't register or the page didn't load. Retrying...")
            
    if not page_loaded:
        raise Exception("Failed to open the Scheduled Visits report after 3 attempts.")

    step("Waiting for background data to finish loading")
    try:
        long_wait.until_not(EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".k-loading-mask, .blockUI, .progress-indicator")
        ))
        ok("No active loading overlay")
    except:
        pass

    step("Looking for Options button")
    options_btn = locate_options_button(driver, long_wait)
    if not options_btn:
        raise Exception("Could not locate the Options button (ID='OptionsBtn')")

    ok("Options button located – opening column chooser")
    driver.execute_script("arguments[0].click();", options_btn)
    time.sleep(2)

    step("Clearing old selections")
    try:
        mark_all_span = driver.find_element(By.XPATH, "//span[text()='(All)']")
        driver.execute_script("arguments[0].click();", mark_all_span)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", mark_all_span)
        ok("Columns cleared")
    except:
        warn("Could not clear columns – continuing")

    required_columns = [
        "Clinic Name", "Patient Name", "Patient ID",
        "Treating Therapist", "Appointment Type",
        "Appointment Date", "Visit Status"
    ]
    for col in required_columns:
        try:
            xpath = f"//span[text()='{col}']/preceding-sibling::input | //label[contains(., '{col}')]//input"
            cb = driver.find_element(By.XPATH, xpath)
            driver.execute_script("arguments[0].click();", cb)
        except:
            warn(f"Column '{col}' not found – possibly already selected")

    apply_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Apply')] | //*[@id='lblLayoutOk']")
    driver.execute_script("arguments[0].click();", apply_btn)
    time.sleep(3)

    step("Applying date filter")
    today = datetime.now()
    end_date = "12/31/2060" 

    if today.weekday() == 0:
        start_date = (today - timedelta(days=3)).strftime("%m/%d/%Y")
        log.info(f"Monday logic: Extracting from last Friday ({start_date}) through 2060.")
    else:
        start_date = (today - timedelta(days=1)).strftime("%m/%d/%Y")
        log.info(f"Standard logic: Extracting from yesterday ({start_date}) through 2060.")

    try:
        driver.execute_script(
            f"if(document.getElementById('inpDateStart')) document.getElementById('inpDateStart').value = '{start_date}';"
        )
        driver.execute_script(
            f"if(document.getElementById('inpDateEnd')) document.getElementById('inpDateEnd').value = '{end_date}';"
        )
        apply_date = driver.find_element(By.ID, "btnApplyDateFilter")
        driver.execute_script("arguments[0].click();", apply_date)
        ok(f"Date filter applied: {start_date} to {end_date}")
    except:
        warn("Could not set date filter – manually check the report range")
    time.sleep(5)

    step("Exporting to CSV")
    before_files = set(os.listdir(DOWNLOAD_PATH))
    export_btn = wait.until(EC.element_to_be_clickable((By.ID, "ExportDataBtn")))
    driver.execute_script("arguments[0].click();", export_btn)
    
    csv_opt = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[text()='CSV']")))
    driver.execute_script("arguments[0].click();", csv_opt)
    
    return wait_for_new_csv(DOWNLOAD_PATH, before_files)

# =====================================================================
# MAIN
# =====================================================================

def main():
    driver = None
    try:
        driver = create_driver()
        wait = WebDriverWait(driver, WAIT_TIMEOUT)
        
        login(driver, wait)
        open_analytics(driver, wait)
        raw_csv = navigate_scheduled_visits(driver, wait)
        
        if raw_csv:
            final_csv = process_downloaded_data(raw_csv)
            if final_csv:
                ok("Process fully completed!")
        
    except Exception as e:
        fail(f"Script Error: {e}")
        log.error(traceback.format_exc())
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    main()