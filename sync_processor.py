import os
import time  
import logging
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

def step(msg: str): log.info(f"▶ {msg}")
def ok(msg: str): log.info(f"✔ {msg}")
def warn(msg: str): log.warning(f"⚠ {msg}")
def fail(msg: str): log.error(f"✖ {msg}")

TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]

def send_telegram_alert(message):
    """Dispatches pipeline status alerts to Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            ok("Telegram notification dispatched successfully.")
        else:
            warn(f"Telegram returned status code: {response.status_code}")
    except Exception as e:
        fail(f"Failed to transmit Telegram webhook: {e}")

def get_valid_agents():
    """Fetches the unique historic agent options from the Google Sheet to populate the UI dropdown."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        
        agent_ss = client.open_by_key("1LgPyUHsxZMioLIOgNRk2IgQOEEU70cHA45fUtoCed6c")
        approval_ws = agent_ss.worksheet("Approval")
        existing_rows = approval_ws.get_all_values()
        
        if len(existing_rows) > 1:
            agents = list(set([r[7].strip() for r in existing_rows[1:] if len(r) > 7 and r[7].strip()]))
            return sorted(agents)
    except Exception as e:
        pass
    # Fallback default pool if sheet connection is slow or unpopulated
    return ["Mazen", "Mohamed Elgendi", "Nada", "Mohamed Elsherif", "Omar Abdelaziz", "Rana", "Youssef", "Mostafa Kamal", "Philo"]

def sync_data_to_google_sheets(csv_path, selected_agents=None):
    step("Connecting to Google Sheets API via Decoupled Sync Processor")
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        fail("Required Google Sheets libraries not installed. Please install gspread and google-auth.")
        return False

    MAIN_SHEET_ID = "1VVM9vExR_4xUN0dp25IF7PiKlTqKTEj-EZ8IwqYn5RA"
    AGENT_SHEET_ID = "1LgPyUHsxZMioLIOgNRk2IgQOEEU70cHA45fUtoCed6c"

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
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

    # 2. Filter Main Sheet by Yesterday's date & Statuses
    yesterday_date = (datetime.now() - timedelta(days=1)).date()
    target_date_str = yesterday_date.strftime("%m/%d/%Y") 
    step(f"Filtering Main Sheet rows for Yesterday ({target_date_str})")
    
    matched_main_rows = []
    for row in main_data_rows:
        if len(row) < 6:
            continue
        
        clinic_name = row[0].strip()
        status_val = row[3].strip()   
        date_str = row[5].strip()     
        
        if clinic_name in excluded_clinics:
            continue
            
        cleaned_str = str(date_str).strip()
        parsed_date = None
        for fmt in ('%m/%d/%Y', '%m-%d-%Y', '%Y-%m-%d'):
            try:
                parsed_date = datetime.strptime(cleaned_str, fmt)
                break
            except ValueError:
                pass
        
        if parsed_date and parsed_date.date() == yesterday_date:
            if status_val.lower() in ["approved", "not required", "approved - not required"]:
                matched_main_rows.append(row)
                
    ok(f"Found {len(matched_main_rows)} matching target rows from yesterday.")
    if not matched_main_rows:
        warn("No rows matched criteria. Ending Sync Process smoothly.")
        return True

    # 3. Read and process WebPT report data
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
        
        new_row = [clinic, emr_id, patient_name, update_date, "", "", "", "", today_stamp]
        
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
    
    # 6. Process Workload Split from UI parameters
    if total_working_count > 0 and selected_agents:
        ok(f"Distributing tasks among selected agents: {selected_agents}")
        num_agents = len(selected_agents)
        base_share = total_working_count // num_agents
        remainder = total_working_count % num_agents
        
        current_idx = 0
        for i, agent in enumerate(selected_agents):
            share_allocation = base_share + (remainder if i == num_agents - 1 else 0)
            for _ in range(share_allocation):
                if current_idx < len(final_no_upcoming):
                    final_no_upcoming[current_idx][7] = agent 
                    current_idx += 1
        ok("Workload distribution split cleanly across designated team members.")
    elif total_working_count > 0:
        warn("No active agents selected in UI form. Leaving agent fields blank.")
            
    rows_to_append = final_upcoming + final_no_upcoming
    
    if rows_to_append:
        step(f"Appending {len(rows_to_append)} unique structural rows to Agent Sheet...")
        try:
            approval_ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
            ok("Google Sheets append pipeline ran successfully.")
            
            completion_summary = (
                f"🔔 *WebPT Automation Notice*\n\n"
                f"Pipeline has completed processing entries!\n"
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
