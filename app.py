import time
import logging
import os
import traceback
import sys
import io
import zipfile
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
st.set_page_config(page_title="WebPT Automation Dashboard", page_icon="⚡", layout="centered")

st.markdown("""
    <style>
    .main-title { font-size: 2.2rem; font-weight: 700; color: #1E88E5; margin-bottom: 0.5rem; }
    .sub-title { font-size: 1rem; color: #666; margin-bottom: 2rem; }
    .step-header { font-size: 1.2rem; font-weight: 600; margin-top: 1rem; margin-bottom: 0.5rem; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">⚡ WebPT Advanced Automation Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Streamlined report extractions, intelligent cross-matching, and automated team task distribution.</div>', unsafe_allow_html=True)

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
    print("🧹 [PANDAS] Starting CSV sanitation and transformation pipeline...")
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')

        df = df.map(
            lambda x: x.replace('\u201a', ',').replace('â€š', ',')
            if isinstance(x, str) else x
        )
        print("✨ [PANDAS] Corrupted character string fragments successfully fixed.")

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
        print("📊 [PANDAS] Final data frames cleaned and restructured efficiently.")
        return csv_path
        
    except Exception as e:
        print(f"❌ [PANDAS] Processing failed: {e}")
        return None

def create_driver() -> webdriver.Chrome:
    print("🌐 [BROWSER] Initializing headless Chrome automation engine...")
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

def wait_for_new_csv(download_dir, before_files, timeout=120):
    print("⏳ [BROWSER] Awaiting secure file export handoff from cloud environment...")
    end_time = time.time() + timeout
    while time.time() < end_time:
        current_files = set(os.listdir(download_dir))
        new_files = current_files - before_files
        new_csvs = [f for f in new_files if f.endswith('.csv')]
        active_downloads = [f for f in new_files if f.endswith('.crdownload') or f.endswith('.tmp')]
        
        if new_csvs and not active_downloads: 
            time.sleep(2)
            file_name = new_csvs[0]
            return os.path.join(download_dir, file_name)
            
        time.sleep(1)
    print("⚠️ [BROWSER] Download pipeline handoff timed out.")
    return None

def login(driver, wait):
    print("🔐 [BROWSER] Passing secure credentials to WebPT authentication portal...")
    driver.get(WEBPT_URL)
    
    wait.until(EC.presence_of_element_located((By.ID, "username"))).send_keys(USERNAME)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    wait.until(EC.presence_of_element_located((By.ID, "password"))).send_keys(PASSWORD)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(5)
    try: 
        oust_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Yes, oust them!')]")
        driver.execute_script("arguments[0].click();", oust_btn)
    except: 
        pass
        
    wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Advanced Search")))

def open_analytics(driver, wait):
    print("📊 [BROWSER] Spawning isolated Analytics engine process handle...")
    main_window = driver.current_window_handle
    btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".analytics-icon")))
    driver.execute_script("arguments[0].click();", btn)
    
    wait.until(EC.new_window_is_opened([main_window]))
    new_window = [w for w in driver.window_handles if w != main_window][0]
    driver.switch_to.window(new_window)
    WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

def locate_options_button(driver):
    try:
        btn = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "OptionsBtn")))
        return btn
    except:
        pass

    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for idx, iframe in enumerate(iframes):
        try:
            driver.switch_to.frame(iframe)
            btn = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "OptionsBtn")))
            return btn
        except:
            driver.switch_to.default_content()
    return None

def navigate_scheduled_visits(driver, wait):
    print("📂 [BROWSER] Navigating layout trees to locate Scheduled Visits Report...")
    long_wait = WebDriverWait(driver, 60)
    short_wait = WebDriverWait(driver, 15)
    
    page_loaded = False
    max_attempts = 3

    for attempt in range(max_attempts):
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

            short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".k-grid, #reportContainer, #OptionsBtn")))
            page_loaded = True
            break
        except:
            pass
            
    if not page_loaded:
        raise Exception("Failed to open the Scheduled Visits report after 3 attempts.")
        
    try:
        long_wait.until_not(EC.presence_of_element_located((By.CSS_SELECTOR, ".k-loading-mask, .blockUI, .progress-indicator")))
    except:
        pass
        
    options_btn = locate_options_button(driver)
    if not options_btn:
        raise Exception("Could not locate the Options button (ID='OptionsBtn')")
        
    driver.execute_script("arguments[0].click();", options_btn)
    time.sleep(2)
    
    try:
        mark_all_span = driver.find_element(By.XPATH, "//span[text()='(All)']")
        driver.execute_script("arguments[0].click();", mark_all_span)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", mark_all_span)
    except:
        pass
        
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
            pass
            
    apply_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Apply')] | //*[@id='lblLayoutOk']")
    driver.execute_script("arguments[0].click();", apply_btn)
    time.sleep(3)
    
    print("📅 [BROWSER] Calibrating calendar filter ranges (Yesterday -> 2060)...")
    today = datetime.now()
    end_date = "12/31/2060"
    if today.weekday() == 0:
        start_date = (today - timedelta(days=3)).strftime("%m/%d/%Y")
    else:
        start_date = (today - timedelta(days=1)).strftime("%m/%d/%Y")
        
    try:
        driver.execute_script(f"if(document.getElementById('inpDateStart')) document.getElementById('inpDateStart').value = '{start_date}';")
        driver.execute_script(f"if(document.getElementById('inpDateEnd')) document.getElementById('inpDateEnd').value = '{end_date}';")
        apply_date = driver.find_element(By.ID, "btnApplyDateFilter")
        driver.execute_script("arguments[0].click();", apply_date)
    except: 
        pass
    time.sleep(5)
    
    print("🚀 [BROWSER] Triggering native cloud data matrix export request...")
    before_files = set(os.listdir(DOWNLOAD_PATH))
    export_btn = wait.until(EC.element_to_be_clickable((By.ID, "ExportDataBtn")))
    driver.execute_script("arguments[0].click();", export_btn)
    
    csv_opt = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[text()='CSV']")))
    driver.execute_script("arguments[0].click();", csv_opt)
    
    return wait_for_new_csv(DOWNLOAD_PATH, before_files)

# =====================================================================
# STREAMLIT USER INTERFACE FORM CONTROLS
# =====================================================================
available_agents = sync_processor.get_valid_agents()

with st.container(border=True):
    st.markdown('<div class="step-header">👥 Step 1: Assign Active Team Members</div>', unsafe_allow_html=True)
    chosen_agents = st.multiselect(
        "Choose who is working today to evenly distribute the active workload balance:",
        options=available_agents,
        default=[],
        placeholder="Select team members..."
    )
    
    st.markdown('<div style="margin-top: 1.5rem;"></div>', unsafe_allow_html=True)
    submit = st.button("🚀 Initialize Automation Pipeline", use_container_width=True, type="primary")

if submit:
    st.markdown('<div class="step-header">⚙️ Live Pipeline Execution Console</div>', unsafe_allow_html=True)
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
            st.info("ℹ️ Cloud approval tracking rows are currently up to date. Extracting WebPT report data anyway...")
        else:
            st.info("🆕 Queued modifications detected. Initializing WebPT data extraction match...")
            
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
                    status_box.update(label="🎉 System task operations concluded perfectly!", state="complete", expanded=False)
                    st.success("🚀 Optimization logs compiled, WebPT report exported, and data alignment check completed successfully.")
                    
                    # 🔥 RESTORED: Local UI download feature exposes the cleaned CSV frame to user screen
                    with open(final_csv, "rb") as file:
                        st.download_button(
                            label="📥 Download Cleaned WebPT Report CSV File",
                            data=file,
                            file_name=os.path.basename(final_csv),
                            mime="text/csv",
                            use_container_width=True
                        )
                else:
                    status_box.update(label="⚠️ Cloud Synchronization Failure", state="error", expanded=True)
        else:
            st.error("❌ Pipeline data collection anomaly. Browser context terminated prematurely.")
            status_box.update(label="❌ Automation script execution halted.", state="error")
                
    except Exception as e:
        status_box.update(label="💥 Fatal Pipeline Crash Encountered", state="error")
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
