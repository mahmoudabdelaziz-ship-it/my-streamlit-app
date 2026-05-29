import os
import time  
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
import streamlit as st

log = logging.getLogger(__name__)

def step(msg: str): log.info(f"▶ {msg}")
def ok(msg: str): log.info(f"✔ {msg}")
def warn(msg: str): log.warning(f"⚠ {msg}")
def fail(msg: str): log.error(f"✖ {msg}")

# Telegram Configuration
TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

def send_telegram_alert(message):
    """Dispatches an alert and returns the current epoch time of transmission."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    sent_time = time.time() # Capture precise time local script sent it
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            ok("Telegram notification dispatched successfully.")
            # If Telegram provides a message date, use it, otherwise use local script time
            res_json = response.json()
            if "result" in res_json and "date" in res_json["result"]:
                return res_json["result"]["date"]
            return sent_time
        else:
            warn(f"Telegram returned status code: {response.status_code}")
    except Exception as e:
        fail(f"Failed to transmit Telegram webhook: {e}")
    return sent_time

def fuzzy_match_agent(input_name, valid_dropdown_names):
    """Upgraded matching engine: checks for partial string matches first, then fuzzy."""
    from difflib import SequenceMatcher, get_close_matches
    
    cleaned_input = input_name.strip().lower()
    if not cleaned_input:
        return input_name

    best_partial_match = None
    highest_ratio = 0.0
    
    for valid_name in valid_dropdown_names:
        cleaned_valid = valid_name.strip().lower()
        matcher = SequenceMatcher(None, cleaned_input, cleaned_valid)
        match_ratio = matcher.real_quick_ratio()
        
        if cleaned_input in cleaned_valid:
            highest_ratio = 1.0
            best_partial_match = valid_name
            break
        elif match_ratio > highest_ratio:
            if match_ratio > 0.6:
                highest_ratio = match_ratio
                best_partial_match = valid_name

    if best_partial_match and highest_ratio >= 0.6:
        return best_partial_match

    matches = get_close_matches(input_name.strip(), valid_dropdown_names, n=1, cutoff=0.5)
    if matches:
        return matches[0]
        
    return input_name

def parse_sheet_date(date_str):
    cleaned_str = str(date_str).strip()
    for fmt in ('%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(cleaned_str, fmt)
        except ValueError:
            pass
    return None

    def sync_data_to_google_sheets(csv_path):
    step("Connecting to Google Sheets API via Decoupled Sync Processor")
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        import streamlit as st
    except ImportError:
        fail("Required Google Sheets libraries not installed. Please install gspread and google-auth.")
        return False

    # ❌ REMOVED: Old local hardcoded path variables
    MAIN_SHEET_ID = "1VVM9vExR_4xUN0dp25IF7PiKlTqKTEj-EZ8IwqYn5RA"
    AGENT_SHEET_ID = "1LgPyUHsxZMioLIOgNRk2IgQOEEU70cHA45fUtoCed6c"

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        google_creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(google_creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        ok("Authenticated successfully with Google service account")
    except Exception as e:
        fail(f"Failed to authenticate with Google: {e}")
        return False

    # ❌ REMOVED THE CRASHING BLOCK HERE:
    # (The old code checked if os.path.exists(CREDENTIALS_PATH) here and crashed)

    # 1. Load data from AuthSheet2026 (Main Sheet)
    step("Reading AuthSheet2026 data from Main Sheet")
    try:
        main_ss = client.open_by_key(MAIN_SHEET_ID)
        auth_ws = main_ss.worksheet("AuthSheet2026")
        main_rows = auth_ws.get_all_values()
        
        # ... Rest of your sync_processor.py code continues exactly as before ...
        # 🔥 FIX: Load credentials directly from Streamlit secure secrets dictionary
        google_creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(google_creds_dict, scopes=scopes)
        
        client = gspread.authorize(creds)
        ok("Authenticated successfully with Google service account")
    except Exception as e:
        fail(f"Failed to authenticate with Google: {e}")
        return False

    MAIN_SHEET_ID = "1VVM9vExR_4xUN0dp25IF7PiKlTqKTEj-EZ8IwqYn5RA"
    AGENT_SHEET_ID = "1LgPyUHsxZMioLIOgNRk2IgQOEEU70cHA45fUtoCed6c"
    
    # ... The rest of your sync_processor.py code continues exactly as before ...
    
    if not os.path.exists(CREDENTIALS_PATH):
        fail(f"Google credentials file not found at: {CREDENTIALS_PATH}")
        return False

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=scopes)
        client = gspread.authorize(creds)
        ok("Authenticated successfully with Google service account")
    except Exception as e:
        fail(f"Failed to authenticate with Google: {e}")
        return False

    # 1. Load data from AuthSheet2026 (Main Sheet)
    step("Reading AuthSheet2026 data from Main Sheet")
    try:
        main_ss = client.open_by_key(MAIN_SHEET_ID)
        auth_ws = main_ss.worksheet("AuthSheet2026")
        main_rows = auth_ws.get_all_values()
        if not main_rows or len(main_rows) <= 1:
            fail("No data found in AuthSheet2026 worksheet.")
            return False
        
        main_data_rows = main_rows[1:]
        ok(f"Successfully loaded {len(main_data_rows)} rows from Main Sheet")
    except Exception as e:
        fail(f"Failed to read from Main Sheet: {e}")
        return False

    excluded_clinics = {'Home Care', 'Sensory Freeway', 'PTOC - Telehealth', '[PTOC - Telehealth]'}

    # 2. Filter Main Sheet by Yesterday's date (Col F) & Statuses (Col D)
    yesterday_date = (datetime.now() - timedelta(days=1)).date()
    target_date_str = yesterday_date.strftime("%m/%d/%Y") 
    step(f"Filtering Main Sheet rows for Yesterday ({target_date_str}) & Status = 'Approved' OR 'Not Required'")
    
    matched_main_rows = []
    for row in main_data_rows:
        if len(row) < 6:
            continue
        
        clinic_name = row[0].strip()
        status_val = row[3].strip()   
        date_str = row[5].strip()     
        
        if clinic_name in excluded_clinics:
            continue
            
        parsed_date = parse_sheet_date(date_str)
        
        if parsed_date and parsed_date.date() == yesterday_date:
            if status_val.lower() in ["approved", "not required", "approved - not required"]:
                matched_main_rows.append(row)
                
    ok(f"Found {len(matched_main_rows)} matching target rows from yesterday ({target_date_str}).")
    if not matched_main_rows:
        warn("No rows matched criteria. Ending Sync Process smoothly.")
        return True

    # 3. Read and process WebPT report data (Filter Today onwards)
    step("Reading and filtering WebPT report data")
    try:
        report_df = pd.read_csv(csv_path, encoding='utf-8')
    except Exception as e:
        fail(f"Failed to read WebPT report: {e}")
        return False
        
    if "Clinic Name" in report_df.columns:
        report_df = report_df[~report_df["Clinic Name"].str.strip().isin(excluded_clinics)]
    
    today_date = datetime.now().date()
    if "Appointment Date" in report_df.columns:
        report_df["Parsed Date"] = pd.to_datetime(report_df["Appointment Date"], errors="coerce")
        filtered_report_df = report_df[report_df["Parsed Date"].dt.date >= today_date]
        ok(f"Filtered report for today onwards. Retained {len(filtered_report_df)} active appointments.")
    else:
        warn("Appointment Date column missing from report. Proceeding without date filter.")
        filtered_report_df = report_df

    # 4. Cross-match Patient ID and check upcoming statuses
    step("Cross-matching Patient IDs to construct data objects...")
    upcoming_statuses = {"Checked-In", "Checked-Out", "Confirmed", "Other"}
    
    report_dict = {}
    if "Patient ID" in filtered_report_df.columns:
        for _, r in filtered_report_df.iterrows():
            pid = str(r["Patient ID"]).strip().split('.')[0]
            v_status = str(r["Visit Status"]).strip()
            if pid not in report_dict:
                report_dict[pid] = []
            report_dict[pid].append(v_status)

    group_upcoming = []
    group_no_upcoming = []
    today_stamp = datetime.now().strftime("%m/%d/%Y")

    for row in matched_main_rows:
        clinic = row[0].strip()       
        emr_id = row[1].strip()       
        patient_name = row[2].strip() 
        update_date = row[5].strip()  
        
        has_upcoming = False
        matched_statuses = report_dict.get(emr_id, [])
        for status in matched_statuses:
            if status in upcoming_statuses:
                has_upcoming = True
                break
        
        new_row = [
            clinic,       # Column A
            emr_id,       # Column B
            patient_name, # Column C
            update_date,  # Column D
            "",           # Column E
            "",           # Column F
            "",           # Column G
            "",           # Column H
            today_stamp   # Column I
        ]
        
        if has_upcoming:
            new_row[4] = "Already Scheduled"
            group_upcoming.append(new_row)
        else:
            new_row[4] = "" 
            group_no_upcoming.append(new_row)

    # 5. Connect to Agent Sheet and filter out historical duplicates
    step("Checking current records inside Agent Sheet to avoid adding duplicates")
    try:
        agent_ss = client.open_by_key(AGENT_SHEET_ID)
        approval_ws = agent_ss.worksheet("Approval")
        existing_rows = approval_ws.get_all_values()
        
        existing_keys = set()
        if len(existing_rows) > 1:
            for r in existing_rows[1:]:
                if len(r) > 3:
                    existing_keys.add((r[1].strip(), r[3].strip()))
    except Exception as e:
        fail(f"Failed to access Agent Sheet records: {e}")
        return False

    final_upcoming = [r for r in group_upcoming if (r[1], r[3]) not in existing_keys]
    final_no_upcoming = [r for r in group_no_upcoming if (r[1], r[3]) not in existing_keys]
    
    total_working_count = len(final_no_upcoming)
    
    # 6. Fetch Telemetry Parameters via Telegram Intercept
    if total_working_count > 0:
        alert_msg = (
            f"🔔 *WebPT Automation Notice*\n\n"
            f"Pipeline has discovered *{total_working_count}* unique blank target rows needing assignment.\n"
            f"Please reply with active agent names separated by commas.\n"
            f"Example: `John, Mah, Alex`"
        )
        # 🔥 CRITICAL FIX: Send alert and record the exact timestamp it arrived in Telegram
        notification_timestamp = send_telegram_alert(alert_msg)
        
        step("Awaiting a BRAND NEW Agent assignment list from Telegram...")
        assigned_agents = []
        offset = None
        timeout_limit = time.time() + 300 # 5-minute timeout window
        poll_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        
        while time.time() < timeout_limit:
            params = {"timeout": 20, "allowed_updates": ["message"]}
            if offset:
                params["offset"] = offset
                
            try:
                updates_resp = requests.get(poll_url, params=params, timeout=30).json()
                if "result" in updates_resp and updates_resp["result"]:
                    for update in updates_resp["result"]:
                        offset = update["update_id"] + 1
                        if "message" in update and str(update["message"]["chat"]["id"]) == str(TELEGRAM_CHAT_ID):
                            msg_date = update["message"].get("date", 0)
                            
                            # 🔥 STRICTOR TIME-GATE WALL:
                            # Only accept the message if its timestamp is strictly greater than our notification timestamp!
                            if msg_date > notification_timestamp:
                                text_reply = update["message"].get("text", "")
                                if text_reply:
                                    assigned_agents = [name.strip() for name in text_reply.split(",") if name.strip()]
                                    break
                            else:
                                # Skips old messages found in history log
                                continue
                    if assigned_agents:
                        break
            except Exception as err:
                warn(f"Polling warning encountered: {err}")
            time.sleep(2)
            
        if assigned_agents:
            ok(f"Received agent parameters from Telegram: {assigned_agents}")
            
            try:
                valid_dropdown_options = list(set([r[7].strip() for r in existing_rows[1:] if len(r) > 7 and r[7].strip()]))
                if not valid_dropdown_options:
                    valid_dropdown_options = assigned_agents 
            except:
                valid_dropdown_options = assigned_agents
                
            cleaned_agents = [fuzzy_match_agent(name, valid_dropdown_options) for name in assigned_agents]
            ok(f"Fuzzy matching conversion engine finalized names: {cleaned_agents}")
            
            num_agents = len(cleaned_agents)
            base_share = total_working_count // num_agents
            remainder = total_working_count % num_agents
            
            current_idx = 0
            for i, agent in enumerate(cleaned_agents):
                share_allocation = base_share + (remainder if i == num_agents - 1 else 0)
                for _ in range(share_allocation):
                    if current_idx < len(final_no_upcoming):
                        final_no_upcoming[current_idx][7] = agent 
                        current_idx += 1
            ok("Workload distribution split cleanly across designated team members.")
        else:
            warn("Telegram response timed out or was invalid. Appending rows with blank agent fields.")
            
    rows_to_append = final_upcoming + final_no_upcoming
    
    if rows_to_append:
        step(f"Appending {len(rows_to_append)} unique structural rows to Agent Sheet...")
        try:
            approval_ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            ok("Google Sheets append pipeline ran successfully.")
            
            completion_summary = (
                f"✅ *Sync Pipeline Complete!*\n\n"
                f"• Already Scheduled Rows: {len(final_upcoming)}\n"
                f"• Assigned Agent Working Rows: {len(final_no_upcoming)}\n"
                f"• Today's Stamp Added to Column I."
            )
            send_telegram_alert(completion_summary)
        except Exception as e:
            fail(f"Failed to push rows to Google Sheets endpoint: {e}")
            return False
    else:
        ok("All processed rows already exist in the Agent Sheet. No new entries were added.")

    return True
