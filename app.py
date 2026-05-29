import time
import logging
import os
import traceback
import sys
import io
import zipfile
import re
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

from selenium import webdriver 
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

import sync_processor

# =====================================================================
# STREAMLIT PAGE SETUP
# =====================================================================
st.set_page_config(page_title="WebPT Automation Tool", page_icon="🤖", layout="centered")

st.title("🤖 WebPT Automated Report Downloader & Assigner")
st.write("Configure active agents and click run to execute the automated task pipeline.")

# =====================================================================
# LOGGING CONFIGURATION
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger(__name__)

class StreamlitLogHandler(io.StringIO):
    def __init__(self, placeholder):
        super().__init__()
        self.placeholder = placeholder
        self.log_text = ""

    def write(self, msg):
        if msg.strip():
            self.log_text += msg + "\n"
            self.placeholder.code(self.log_text)
        return len(msg)

# =====================================================================
# SECURE CONFIGURATION & PATH CORRECTIONS
# =====================================================================
WEBPT_URL     = "https://app.webpt.com"
WAIT_TIMEOUT  = 20
DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads")

if not os.path.exists(DOWNLOAD_PATH):
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)

try:
    USERNAME       = st.secrets["WEBPT_USERNAME"]
    PASSWORD       = st.secrets["WEBPT_PASSWORD"]
    PROXY_USER     = st.secrets["PROXY_USER"]
    PROXY_PASS     = st.secrets["PROXY_PASS"]
    PROXY_ENDPOINT = st.secrets["PROXY_ENDPOINT"]
    USE_PROXY      = True
except Exception as e:
    USERNAME      = "Mahmoudabdelaziz.CC"
    PASSWORD      = "CityPT10$"
    USE_PROXY     = False

# =====================================================================
# UTILITY AND SELENIUM PIPELINE FUNCTIONS
# =====================================================================
def create_proxy_auth_extension(proxy_host, proxy_port, proxy_user, proxy_pass, folder_path="/tmp"):
    manifest_json = '{"version": "1.0.0", "manifest_version": 3, "name": "Chrome Proxy Auth Extension", "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestAuthProvider"], "background": { "service_worker": "background.js" }}'
    background_js = f'var config = {{ mode: "fixed_servers", rules: {{ singleProxy: {{ scheme: "http", host: "{proxy_host}", port: parseInt({proxy_port}) }}, bypassList: [] }} }}; chrome.proxy.settings.set({{value: config, scope: "regular"}}, function({{}}); chrome.webRequest.onAuthRequired.addListener(function(details) {{ return {{ authCredentials: {{ username: "{proxy_user}", password: "{proxy_pass}" }} }}; }}, {{urls: ["<all_urls>"]}}, ["blocking"]);'
    if not os.path.exists(folder_path): 
        os.makedirs(folder_path)
    plugin_path = os.path.join(folder_path, "proxy_auth_plugin.zip")
    with zipfile.ZipFile(plugin_path, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
    return plugin_path

def process_downloaded_data(csv_path):
    print("🧹 Cleaning and parsing WebPT CSV structures...")
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
        
        # Strip columns down to lowercase alphabetic strings only to handle spacing or special character variations
        raw_to_alpha = {c: re.sub(r'[^a-z]', '', str(c).lower()) for c in df.columns}
        
        # Map dynamic alphabetic combinations to required standard structures
        column_mapping = {
            "clinicname": "Clinic Name",
            "patientname": "Patient Name",
            "patientid": "Patient ID",
            "treatingtherapist": "Treating Therapist",
            "appointmenttype": "Appointment Type",
            "appttype": "Appointment Type",
            "appointmentdate": "Appointment Date",
            "apptdate": "Appointment Date",
            "visitstatus": "Visit Status",
            "status": "Visit Status"
        }
        
        rename_dict = {}
        for raw_col, alpha_col in raw_to_alpha.items():
            if alpha_col in column_mapping:
                rename_dict[raw_col] = column_mapping[alpha_col]
        
        # Apply normalization rename transformations
        df = df.rename(columns=rename_dict)
        
        # Validate that all required structural indices are cleanly present
        target_columns = ["Patient ID", "Patient Name", "Clinic Name", "Treating Therapist", "Appointment Type", "Appointment Date", "Visit Status"]
        for col in target_columns:
            if col not in df.columns:
                raise KeyError(f"Critical index column '{col}' could not be resolved from CSV source.")
                
        # Retain and rearrange target columns
        df = df[target_columns]
        
        # Vectorized string sanitization instead of cell-by-cell loops
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).str.replace('\u201a', ',', regex=False).str.replace('â€š', ',', regex=False).str.strip()
            
        excluded_clinics = {'Home Care', 'Sensory Freeway', 'PTOC - Telehealth', '[PTOC - Telehealth]'}
        df = df[~df["Clinic Name"].isin(excluded_clinics)]
        
        df["Appointment Date"] = pd.to_datetime(df["Appointment Date"], errors="coerce")
        df = df.sort_values(by=["Visit Status", "Appointment Date", "Clinic Name"], ascending=[True, True, True])
        df["Appointment Date"] = df["Appointment Date"].dt.strftime("%Y-%m-%d")
        
        df.to_csv(csv_path, index=False, encoding='utf-8')
        print("✨ CSV data structures cleaned successfully!")
        return csv_path
    except Exception as e: 
        print(f"❌ Failed to parse data rows: {e}")
        return None

def create_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking") 
    options.add_argument("--ignore-certificate-errors")
    
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    prefs = {
        "download.default_directory": DOWNLOAD_PATH,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": False
    }
    options.add_experimental_option("prefs", prefs)
    
    if USE_PROXY:
        try:
            host, port = PROXY_ENDPOINT.strip().split(":")
            plugin_file = create_proxy_auth_extension(host, port, PROXY_USER.strip(), PROXY_PASS.strip())
            options.add_argument(f'--load-extension={os.path.dirname(plugin_file)}')
        except: 
            pass
            
    if os.name == 'posix':
        if os.path.exists("/usr/bin/chromium-browser"): 
            options.binary_location = "/usr/bin/chromium-browser"
        elif os.path.exists("/usr/bin/chromium"): 
            options.binary_location = "/usr/bin/chromium"
        driver = webdriver.Chrome(options=options)
    else:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": DOWNLOAD_PATH
    })
    
    return driver

def wait_for_new_csv(download_dir, before_files, timeout=60):
    print("⏳ Watching target folder for incoming WebPT report...")
    end_time = time.time() + timeout
    while time.time() < end_time:
        current_files = set(os.listdir(download_dir))
        new_files = current_files - before_files
        new_csvs = [f for f in new_files if f.endswith('.csv')]
        active_downloads = [f for f in new_files if f.endswith('.crdownload') or f.endswith('.tmp')]
        
        if new_csvs and not active_downloads: 
            target_file = os.path.join(download_dir, new_csvs[0])
            print(f"📥 File captured successfully: {new_csvs[0]}")
            return target_file
            
        time.sleep(1.5)
    raise TimeoutError(f"WebPT initiated export, but no file arrived in {timeout} seconds.")

def login(driver, wait):
    print("🚀 Navigating to WebPT Login Page...")
    driver.get(WEBPT_URL)
    print("✍️ Entering Credentials...")
    wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(USERNAME)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    wait.until(EC.presence_of_element_located((By.ID, "password"))).send_keys(PASSWORD)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(4)
    try: 
        driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, "//button[contains(text(), 'Yes, oust them!')]"))
        print("💥 Displaced another active session token successfully.")
    except: 
        pass
    wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Advanced Search")))
    print("🔓 Logged in successfully!")

def open_analytics(driver, wait):
    print("📊 Accessing WebPT Analytics Engine Hub...")
    main_window = driver.current_window_handle
    driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".analytics-icon"))))
    
    window_wait_timeout = time.time() + 15
    while len(driver.window_handles) == 1:
        if time.time() > window_wait_timeout:
            raise TimeoutError("WebPT Analytics multi-window execution target took too long to load.")
        time.sleep(0.5)
        
    driver.switch_to.window([w for w in driver.window_handles if w != main_window][0])
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    print("🎯 Successfully focused Analytics tab frame.")

def navigate_scheduled_visits(driver, wait):
    print("📂 Expanding Reports UI layout...")
    WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.XPATH, "//div[@id='REPORTS'] | //div[text()='REPORTS']"))).click()
    time.sleep(1)
    sv = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//div[@id='scheduled_visits']")))
    driver.execute_script("arguments[0].click();", sv)
    
    print("⚙️ Adjusting data column overlays...")
    options_btn = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.ID, "OptionsBtn")))
    driver.execute_script("arguments[0].click();", options_btn)
    time.sleep(1)
    
    required_columns = ["Clinic Name", "Patient Name", "Patient ID", "Treating Therapist", "Appointment Type", "Appointment Date", "Visit Status"]
    for col in required_columns:
        try: 
            driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, f"//span[text()='{col}']/preceding-sibling::input"))
        except: 
            pass
            
    print("💾 Confirming changes...")
    apply_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Apply')] | //*[@id='lblLayoutOk']")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", apply_btn)
    time.sleep(0.5)
    driver.execute_script("arguments[0].click();", apply_btn)
    time.sleep(2)
    
    print("📅 Applying date range filters...")
    start_date = (datetime.now() - timedelta(days=3 if datetime.now().weekday() == 0 else 1)).strftime("%m/%d/%Y")
    try:
        driver.execute_script(f"if(document.getElementById('inpDateStart')) document.getElementById('inpDateStart').value = '{start_date}';")
        driver.execute_script("if(document.getElementById('inpDateEnd')) document.getElementById('inpDateEnd').value = '12/31/2060';")
        driver.find_element(By.ID, "btnApplyDateFilter").click()
    except: 
        pass
    time.sleep(4)
    
    print("📥 Triggering report download click...")
    before_files = set(os.listdir(DOWNLOAD_PATH))
    driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.ID, "ExportDataBtn"))))
    driver.execute_script("arguments[0].click();", wait.until(EC.element_to_be_clickable((By.XPATH, "//*[text()='CSV']"))))
    
    return wait_for_new_csv(DOWNLOAD_PATH, before_files)


# =====================================================================
# STREAMLIT USER INTERFACE FORM CONTROLS
# =====================================================================
available_agents = sync_processor.get_valid_agents()

with st.form("automation_form"):
    st.subheader("📋 Step 1: Select Active Assignment Team")
    chosen_agents = st.multiselect(
        "Select working agents for today's data distribution:",
        options=available_agents,
        default=[]
    )
    submit = st.form_submit_button("🚀 Launch Scraper & Sheet Sync Pipeline")

if submit:
    status_box = st.status("Connecting to Google Sheets for structural pre-check...", expanded=True)
    log_container = status_box.empty()
    
    streamlit_handler = StreamlitLogHandler(log_container)
    sys.stdout = streamlit_handler
    root_logger = logging.getLogger()
    stream_handler = logging.StreamHandler(streamlit_handler)
    root_logger.addHandler(stream_handler)
    
    driver = None
    try:
        sync_needed, matched_rows = sync_processor.check_if_sync_needed()
        
        if not sync_needed:
            status_box.update(label="✅ Sheet Already Up To Date. No extraction needed!", state="complete", expanded=True)
            st.success("The Approval worksheet is completely up-to-date with yesterday's approved records. WebPT scraper process skipped safely.")
        else:
            st.info("New entries detected! Initializing WebPT headless interface processing...")
            
            driver = create_driver()
            wait = WebDriverWait(driver, WAIT_TIMEOUT)
            
            login(driver, wait)
            open_analytics(driver, wait)
            raw_csv = navigate_scheduled_visits(driver, wait)
            
            if raw_csv:
                final_csv = process_downloaded_data(raw_csv)
                if final_csv:
                    sync_success = sync_processor.sync_data_to_google_sheets(final_csv, matched_rows, selected_agents=chosen_agents)
                    if sync_success:
                        status_box.update(label="🎉 Process & Google Sheets Sync Completed Successfully!", state="complete", expanded=False)
                        st.success("Synchronization finished smoothly.")
                    else:
                        status_box.update(label="⚠️ WebPT Scraped, but Google Sheets Sync Failed", state="error", expanded=True)
            else:
                st.error("No CSV was recovered from the pipeline execution matrix.")
                status_box.update(label="❌ Automation script execution halted.", state="error")
                
    except Exception as e:
        status_box.update(label="💥 Runtime Exception Encountered", state="error")
        st.error(f"Execution Error: {e}")
        
        if driver:
            try:
                screenshot_path = "error_screenshot.png"
                driver.save_screenshot(screenshot_path)
                st.warning("🤖 Selenium has taken a screenshot of the page where it got stuck.")
                with open(screenshot_path, "rb") as f:
                    st.image(f.read(), caption="Headless Browser View at Crash State")
            except Exception as img_err:
                st.error(f"Could not extract crash view image: {img_err}")

        with st.expander("Show Technical Stack Trace"):
            st.code(traceback.format_exc())
            
    finally:
        root_logger.removeHandler(stream_handler)
        sys.stdout = sys.__stdout__
        if driver:
            driver.quit()
