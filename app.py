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

# NATIVE, STABLE SELENIUM IMPORTS
from selenium import webdriver 
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Import the decoupled sync processor file
import sync_processor

# =====================================================================
# STREAMLIT PAGE SETUP
# =====================================================================
st.set_page_config(page_title="WebPT Automation Tool", page_icon="🤖", layout="centered")

st.title("🤖 WebPT Automated Report Downloader")
st.write("Click the button below to launch the background headless Chrome browser, route through your New York proxy, and extract your Scheduled Visits report.")

# =====================================================================
# LOGGING CONFIGURATION & STREAMLIT STREAMER
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

def step(msg: str):
    log.info(f"▶ {msg}")

def ok(msg: str):
    log.info(f"✔ {msg}")

def warn(msg: str):
    log.warning(f"⚠ {msg}")

def fail(msg: str):
    log.error(f"✖ {msg}")

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
# NATIVE AUTHENTICATED PROXY EXTENSION GENERATOR
# =====================================================================
def create_proxy_auth_extension(proxy_host, proxy_port, proxy_user, proxy_pass, folder_path="/tmp"):
    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 3,
        "name": "Chrome Proxy Auth Extension",
        "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestAuthProvider"],
        "background": {
            "service_worker": "background.js"
        }
    }
    """

    background_js = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{
            singleProxy: {{
                scheme: "http",
                host: "{proxy_host}",
                port: parseInt({proxy_port})
            }},
            bypassList: []
        }}
    }};

    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function({{}});

    chrome.webRequest.onAuthRequired.addListener(
        function(details) {{
            return {{
                authCredentials: {{
                    username: "{proxy_user}",
                    password: "{proxy_pass}"
                }}
            }};
        }},
        {{urls: ["<all_urls>"]}},
        ["blocking"]
    );
    """
    
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
        
    plugin_path = os.path.join(folder_path, "proxy_auth_plugin.zip")
    with zipfile.ZipFile(plugin_path, 'w') as zp:
        zp.writestr("manifest.json", manifest_json)
        zp.writestr("background.js", background_js)
        
    return plugin_path

# =====================================================================
# CORE AUTOMATION LOGIC
# =====================================================================
def process_downloaded_data(csv_path):
    step("Processing CSV Data with Pandas")
    try:
        df = pd.read_csv(csv_path, encoding='utf-8')
        df = df.map(lambda x: x.replace('\u201a', ',').replace('â€š', ',') if isinstance(x, str) else x)
        ok("Replaced all corrupted commas with regular commas")

        target_columns = ["Patient ID", "Patient Name", "Clinic Name", "Treating Therapist", "Appointment Type", "Appointment Date", "Visit Status"]
        df = df[target_columns]
        
        excluded_clinics = {'Home Care', 'Sensory Freeway', 'PTOC - Telehealth', '[PTOC - Telehealth]'}
        df = df[~df["Clinic Name"].str.strip().isin(excluded_clinics)]
        ok("Filtered and deleted excluded clinics from the CSV file download context")

        df["Appointment Date"] = pd.to_datetime(df["Appointment Date"], errors="coerce")
        df = df.sort_values(by=["Visit Status", "Appointment Date", "Clinic Name"], ascending=[True, True, True])
        df["Appointment Date"] = df["Appointment Date"].dt.strftime("%Y-%m-%d")

        df.to_csv(csv_path, index=False, encoding='utf-8')
        ok("File processed and overwritten successfully")
        return csv_path
    except Exception as e:
        fail(f"Pandas processing failed: {e}")
        return None

def create_driver() -> webdriver.Chrome:
    step("Launching Native Headless Chrome via Secure Extension Routing")
    options = webdriver.ChromeOptions()
    
    # 🔥 CRITICAL EXTRA FLAGS FOR DEPLOYED LINUX ENVIRONMENTS
    options.add_argument("--headless=new") # Run completely behind the scenes without a GUI
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking") 
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-running-insecure-content")
    
    # ... Rest of your existing create_driver() code stays exactly the same    
    prefs = {
        "download.default_directory": DOWNLOAD_PATH,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.geolocation": 1 
    }
    options.add_experimental_option("prefs", prefs)
    
    if USE_PROXY:
        log.info("Injecting credential authentication parameters natively into Chrome context...")
        try:
            host, port = PROXY_ENDPOINT.strip().split(":")
            plugin_file = create_proxy_auth_extension(
                proxy_host=host,
                proxy_port=port,
                proxy_user=PROXY_USER.strip(),
                proxy_pass=PROXY_PASS.strip()
            )
            options.add_argument(f'--load-extension={os.path.dirname(plugin_file)}')
        except Exception as proxy_err:
            log.error(f"Failed to load native proxy configuration details: {proxy_err}")

    if os.name == 'posix': 
        if os.path.exists("/usr/bin/chromium-browser"):
            options.binary_location = "/usr/bin/chromium-browser"
        elif os.path.exists("/usr/bin/chromium"):
            options.binary_location = "/usr/bin/chromium"
        driver = webdriver.Chrome(options=options)
    else:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
    ny_coordinates = {"latitude": 40.7128, "longitude": -74.0060, "accuracy": 100}
    driver.execute_cdp_cmd("Emulation.setGeolocationOverride", ny_coordinates)
    ok("Headless browser loaded securely within New York context!")
    return driver

def wait_for_new_csv(download_dir, before_files, timeout=120):
    log.info("Waiting for the server file transmission to complete...")
    end_time = time.time() + timeout
    while time.time() < end_time:
        current_files = set(os.listdir(download_dir))
        new_files = current_files - before_files
        new_csvs = [f for f in new_files if f.endswith('.csv')]
        active_downloads = [f for f in new_files if f.endswith('.crdownload') or f.endswith('.tmp')]
        
        if new_csvs and not active_downloads:
            time.sleep(2)
            return os.path.join(download_dir, new_csvs[0])
        time.sleep(1)
    warn("Download timed out.")
    return None

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
        ok("Handled multiple session 'Oust' validation checkpoint.")
    except:
        pass
        
    wait.until(EC.presence_of_element_located((By.LINK_TEXT, "Advanced Search")))
    ok("Login credentials accepted!")

def open_analytics(driver, wait):
    step("Opening Analytics tab dashboard")
    main_window = driver.current_window_handle
    btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".analytics-icon")))
    driver.execute_script("arguments[0].click();", btn)
    wait.until(EC.new_window_is_opened([main_window]))
    new_window = [w for w in driver.window_handles if w != main_window][0]
    driver.switch_to.window(new_window)
    WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    ok("Switched viewport context to Analytics frame")

def locate_options_button(driver, long_wait):
    try:
        return WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.ID, "OptionsBtn")))
    except:
        pass
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for iframe in iframes:
        try:
            driver.switch_to.frame(iframe)
            return WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.ID, "OptionsBtn")))
        except:
            driver.switch_to.default_content()
    return None

def navigate_scheduled_visits(driver, wait):
    step("Navigating to Scheduled Visits Report and mapping column attributes")
    long_wait = WebDriverWait(driver, 60)
    short_wait = WebDriverWait(driver, 15)
    page_loaded = False

    for attempt in range(3):
        try:
            reports_menu = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//div[@id='REPORTS'] | //div[text()='REPORTS']")))
            driver.execute_script("arguments[0].click();", reports_menu)
            time.sleep(1.5)
            sv_link = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//div[@id='scheduled_visits']//span[text()='Scheduled Visits'] | //div[@id='scheduled_visits']")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sv_link)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", sv_link)
            short_wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".k-grid, #reportContainer, #OptionsBtn")))
            page_loaded = True
            break
        except:
            warn("Click interaction failed to register. Retrying pipeline synchronization block...")
            
    if not page_loaded:
        raise Exception("Failed to sync structural elements inside Scheduled Visits layout.")

    try:
        long_wait.until_not(EC.presence_of_element_located((By.CSS_SELECTOR, ".k-loading-mask, .blockUI, .progress-indicator")))
    except:
        pass

    options_btn = locate_options_button(driver, long_wait)
    if not options_btn:
        raise Exception("Options UI overlay failed to target structural selectors.")

    driver.execute_script("arguments[0].click();", options_btn)
    time.sleep(2)

    try:
        mark_all_span = driver.find_element(By.XPATH, "//span[text()='(All)']")
        driver.execute_script("arguments[0].click();", mark_all_span)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", mark_all_span)
        ok("Form criteria mapping filters cleared.")
    except:
        pass

    required_columns = ["Clinic Name", "Patient Name", "Patient ID", "Treating Therapist", "Appointment Type", "Appointment Date", "Visit Status"]
    for col in required_columns:
        try:
            cb = driver.find_element(By.XPATH, f"//span[text()='{col}']/preceding-sibling::input | //label[contains(., '{col}')]//input")
            driver.execute_script("arguments[0].click();", cb)
        except:
            pass

    apply_btn = driver.find_element(By.XPATH, "//button[contains(text(),'Apply')] | //*[@id='lblLayoutOk']")
    driver.execute_script("arguments[0].click();", apply_btn)
    time.sleep(3)

    today = datetime.now()
    end_date = "12/31/2060"
    start_date = (today - timedelta(days=3)).strftime("%m/%d/%Y") if today.weekday() == 0 else (today - timedelta(days=1)).strftime("%m/%d/%Y")

    try:
        driver.execute_script(f"if(document.getElementById('inpDateStart')) document.getElementById('inpDateStart').value = '{start_date}';")
        driver.execute_script(f"if(document.getElementById('inpDateEnd')) document.getElementById('inpDateEnd').value = '{end_date}';")
        apply_date = driver.find_element(By.ID, "btnApplyDateFilter")
        driver.execute_script("arguments[0].click();", apply_date)
        ok(f"Applied date contextual scope filter from {start_date} to {end_date}")
    except:
        warn("Failed to automatically update target calendar dimensions.")
    time.sleep(5)

    before_files = set(os.listdir(DOWNLOAD_PATH))
    export_btn = wait.until(EC.element_to_be_clickable((By.ID, "ExportDataBtn")))
    driver.execute_script("arguments[0].click();", export_btn)
    csv_opt = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[text()='CSV']")))
    driver.execute_script("arguments[0].click();", csv_opt)
    
    return wait_for_new_csv(DOWNLOAD_PATH, before_files)

# =====================================================================
# USER INTERFACE INTERACTION ROUTER
# =====================================================================
with st.form("automation_form"):
    st.info("System will verify local variables and secrets configurations automatically.")
    submit = st.form_submit_button("🚀 Run Automation Process Now")

if submit:
    status_box = st.status("Initializing Background Server Tasks...", expanded=True)
    log_container = status_box.empty()
    
    streamlit_handler = StreamlitLogHandler(log_container)
    sys.stdout = streamlit_handler
    root_logger = logging.getLogger()
    stream_handler = logging.StreamHandler(streamlit_handler)
    root_logger.addHandler(stream_handler)
    
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
                sync_success = sync_processor.sync_data_to_google_sheets(final_csv)
                if sync_success:
                    status_box.update(label="🎉 Process & Google Sheets Sync Completed Successfully!", state="complete", expanded=False)
                    st.success("The operations pipeline and Google Sheets synchronization completed cleanly.")
                else:
                    status_box.update(label="⚠️ WebPT Scraped, but Google Sheets Sync Failed", state="error", expanded=True)
                    st.warning("WebPT extraction was successful, but the Google Sheets sync failed. Please check the log details above.")
                
                with open(final_csv, "rb") as file:
                    st.download_button(
                        label="📥 Download Cleaned CSV File",
                        data=file,
                        file_name=os.path.basename(final_csv),
                        mime="text/csv"
                    )
        else:
            status_box.update(label="❌ Automation script execution halted.", state="error")
            st.error("No file was recovered from the pipeline.")
            
    except Exception as e:
        status_box.update(label="💥 Runtime Exception Encountered", state="error")
        st.error(f"Execution Error: {e}")
        with st.expander("Show Technical Stack Trace"):
            st.code(traceback.format_exc())
            
    finally:
        root_logger.removeHandler(stream_handler)
        sys.stdout = sys.__stdout__
        if driver:
            driver.quit()
