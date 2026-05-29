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

MAIN_SHEET_ID = "1VVM9vExR_4xUN0dp25IF7PiKlTqKTEj-EZ8IwqYn5RA"
AGENT_SHEET_ID = "1LgPyUHsxZMioLIOgNRk2IgQOEEU70cHA45fUtoCed6c"
EXCLUDED_CLINICS = {'Home Care', 'Sensory Freeway', 'PTOC - Telehealth', '[PTOC - Telehealth]'}

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

def get_gspread_client():
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    return gspread.authorize(creds)

def get_valid_agents():
    """Fetches the unique historic agent options from the Google Sheet to populate the UI dropdown."""
    try:
        client = get_gspread_client()
        agent_ss = client.open_by_key(AGENT_SHEET_ID)
        approval_ws = agent_ss.worksheet("Approval")
        existing_rows = approval_ws.get_all_values()
        
        if len(existing_rows) > 1:
            agents = list(set([r[7].strip() for r in existing_rows[1:] if len(r) > 7 and r[7].strip()]))
            return sorted(agents)
    except Exception as e:
        pass
    return ["Mazen", "Mohamed Elgendi", "Nada", "Mohamed Elsherif", "Omar Abdelaziz", "Rana", "Youssef", "Mostafa Kamal", "Philo"]

def fetch_and_filter_main_rows(client):
    """Loads and filters main sheet entries matching criteria from yesterday."""
    main_ss = client.open_by_key(MAIN_SHEET_ID)
    auth_ws = main_ss.worksheet("AuthSheet2026")
    main_rows = auth_ws.get_all_values()
    if not main_rows or len(main_rows) <= 1:
        return []

    main_data_rows = main_rows[1:]
    yesterday_date = (datetime.now() - timedelta(days=1)).date()
    
    matched_main_rows = []
    for row in main_data_rows:
        if len(row) < 6:
            continue
        
        clinic_name = row[0].strip()
        status_val = row[3].strip()   
        date_str = row[5].strip()     
        
        if clinic_name in EXCLUDED_CLINICS:
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
    return matched_main_rows

def get_existing_agent_keys(client):
    """Returns unique (Patient ID, Update Date) signatures already existing in the approval sheet."""
    agent_ss = client.open_by_key(AGENT_SHEET_ID)
    approval_ws = agent_ss.worksheet("Approval")
    existing_rows = approval_ws.get_all_values()
    
    existing_keys = set()
    if len(existing_rows) > 1:
        for r in existing_rows[1:]:
            if len(r) > 3:
                existing_keys.add((r[1].strip(), r[3].strip()))
    return existing_keys, approval_ws

def check_if_sync_needed():
    """
    Step 0: Connects to Google Sheets BEFORE scraper runs.
    Returns (True, matched_main_rows) if there are new items to process.
    Returns (False, []) if everything is already updated.
    """
    step("Pre-checking Google Sheets to see if execution is necessary...")
    try:
        client = get_gspread_client()
        matched_main_rows = fetch_and_filter_main_rows(client)
        
        if not matched_main_rows:
            ok("No rows matched criteria for yesterday in Main Sheet. Execution skipped.")
            return False, []
            
        existing_keys, _ = get_existing_agent_keys(client)
        
        # Check if there's any row from yesterday that does NOT exist yet in Agent sheet
        unprocessed_rows = [r for r in matched_main_rows if (r[1].strip(), r[5].strip()) not in existing_keys]
        
        if not unprocessed_rows:
            ok("All records from yesterday are already present in the Approval Sheet. Skipping WebPT Extraction entirely!")
            return False, []
            
        ok(f"Found {len(unprocessed_rows)} unprocessed rows. Proceeding with WebPT extraction.")
        return True, matched_main_rows
        
    except Exception as e:
        fail(f"Error during Google Sheets pre-check phase: {e}")
        # If the check fails due to network issues, default to True to remain safe
        return True, []

def sync_data_to_google_sheets(csv_path, matched_main_rows, selected_agents=None):
    """Processes WebPT CSV against pre-fetched rows and uploads results."""
    step("Connecting to Google Sheets API to append final structured data")
    try:
        client = get_gspread_client()
        if not matched_main_rows:
            matched_main_rows = fetch_and_filter_main_rows(client)
            
        existing_keys, approval_ws = get_existing_agent_keys(client)
    except Exception as e:
        fail(f"Failed to access Google Sheets endpoints during update phase: {e}")
        return False

    if not matched_main_rows:
        warn("No target rows matched criteria. Ending Sync Process cleanly.")
        return True

    # Read and process WebPT report data
    step("Reading and filtering WebPT report data")
    try:
        report_df = pd.read_csv(csv_path, encoding='utf-8')
    except Exception as e:
        fail(f"Failed to read WebPT report: {e}")
        return False
        
    if "Clinic Name" in report_df.columns:
        report_df = report_df[~report_df["Clinic Name"].str.strip().isin(EXCLUDED_CLINICS)]
    
    today_date = datetime.now().date()
    if "Appointment Date" in report_df.columns:
        report_df["Parsed Date"] = pd.to_datetime(report_df["Appointment Date"], errors="coerce")
        filtered_report_df = report_df[report_df["Parsed Date"].dt.date >= today_date]
    else:
        filtered_report_df = report_df

    # Cross-match Patient ID and check upcoming statuses
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

    # Filter out records that are already posted
    final_upcoming = [r for r in group_upcoming if (r[1], r[3]) not in existing_keys]
    final_no_upcoming = [r for r in group_no_upcoming if (r[1], r[3]) not in existing_keys]
    
    total_working_count = len(final_no_upcoming)
    
    # Process Workload Split
    if total_working_count > 0 and selected_agents:
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
        ok("All processed rows already exist in the Agent Sheet.")

    return True
