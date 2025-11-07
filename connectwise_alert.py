import requests
import base64
import json
import os
import datetime
# Re-adding imports required for SMS/Email
import smtplib
from email.message import EmailMessage
# We keep the import for config, assuming SLACK_WEBHOOK_URLs and CW credentials are here.
# NOTE: Ensure SLACK_WEBHOOK_URL_REGULAR and SLACK_WEBHOOK_URL_URGENT are defined in your config.py
from config import *

def get_all_matching_tickets():
    """
    Connects to CW API and retrieves ALL tickets based on the configured 
    board/status names.
    Returns a list of all ticket objects matching the criteria.
    """
    all_tickets = []

    # 1. Prepare Authentication Header (uses Basic Auth)
    auth_string = f"{CW_COMPANY_ID}+{CW_PUBLIC_KEY}:{CW_PRIVATE_KEY}"
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "clientID": CW_CLIENT_ID,
        "Content-Type": "application/json"
    }

    # 2. Define the API Request URL and Filter
    conditions = f"board/name=\"{CW_BOARD_NAME}\" and status/name=\"{CW_STATUS_NAME}\""
    url = f"{CW_BASE_URL}/service/tickets?conditions={conditions}&orderBy=id asc&pageSize=100"

    print(f"Checking CW API for ALL matching tickets with condition: {conditions}")
    
    # *** DEBUGGING ADDITION: Print the full URL to verify filter construction ***
    print(f"CW API URL being used: {url}")
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        all_tickets = response.json()
        
        if all_tickets:
            print(f"Found {len(all_tickets)} total ticket(s) matching criteria.")
            
        return all_tickets

    except requests.exceptions.RequestException as e:
        print(f"🛑 CW API Request Failed. Check credentials/URL/filters. Error: {e}")
        return []

# --- 2. ALERTING FUNCTIONS (No changes needed here, relies on config checks) ---

def send_slack_webhook(message_title, message_body, color=16711680, webhook_url=SLACK_WEBHOOK_URL_REGULAR):
    """
    Sends an alert message using a Slack Webhook to the specified URL.
    """
    if not webhook_url or "PLACEHOLDER" in webhook_url:
        print(f"⚠️ Slack Webhook URL not configured. Skipping Slack alert.")
        return False
        
    hex_color = f'#{color:06x}'
    payload = {
        "attachments": [
            {
                "color": hex_color, 
                "title": message_title,
                "text": message_body,
                "ts": int(datetime.datetime.now().timestamp()),
                "footer": "Automated ConnectWise Alert"
            }
        ]
    }

    try:
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        response.raise_for_status()
        
        print(f"✅ Slack Webhook alert sent successfully to {'URGENT' if webhook_url == SLACK_WEBHOOK_URL_URGENT else 'REGULAR'} channel.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"🛑 Failed to send Slack Webhook: {e}")
        return False

def send_email(subject, body, recipient):
    """Generic function to handle email/SMS sending using SMTP settings from config.py."""
    if not all([SMTP_SERVER, SENDER_EMAIL, SENDER_PASSWORD]):
        print("⚠️ SMTP credentials not fully configured. Skipping email/SMS alert.")
        return False
        
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = recipient

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print("✅ SMS/Email alert sent successfully.")
        return True
    except Exception as e:
        print(f"🛑 Failed to send consolidated email/SMS. Error: {e}")
        return False

def format_ticket_message(ticket, for_slack=False):
    """
    Formats a single ticket's data into a concise string.
    """
    priority_name = ticket.get('priority', {}).get('name', 'N/A')
    site_name = ticket.get('site', {}).get('name', 'N/A')
    
    priority_map = {
        'Priority 1 - Critical': 'P1-CRIT',
        'Priority 2 - High': 'P2-HIGH',
        'Priority 3 - Medium': 'P3-MED',
        'Priority 4 - Low': 'P4-LOW',
        'N/A': 'N/A'
    }
    abbreviated_priority = priority_map.get(priority_name, priority_name)
    
    if for_slack:
        # Rich Format for Slack: TICKETID | PRIORITY | SITE_NAME
        return f"`{ticket['id']}` | *{abbreviated_priority}* | {site_name}"
    else:
        # Plain Format for SMS/Email Subject: TICKETID | PRIORITY | SITE_NAME
        return f"{ticket['id']} | {abbreviated_priority} | {site_name}"

# --- 3. MAIN EXECUTION ---
if __name__ == "__main__":
    
    print("--- ConnectWise Ticket Alert Script Started ---")
    
    # 1. NEW LOGIC: Read from Environment Variable (for GitHub/Cloud persistence)
    # Default is 0 if not found or empty
    last_id = int(os.environ.get('LAST_RUN_ID', 0))

    # 2. Fallback: If ENV is 0, try to read the local file (for local VS Code testing)
    if last_id == 0:
        try:
            with open('last_run_id.txt', 'r') as f:
                last_id_content = f.read().strip()
                last_id = int(last_id_content) if last_id_content.isdigit() else 0
        except Exception:
            # If file doesn't exist, last_id remains 0
            pass 
    
    print(f"Last processed ID: {last_id} (Source: {'Environment Variable' if os.environ.get('LAST_RUN_ID') else 'Local File/Default'})")

    # 2. Get ALL tickets matching the criteria
    all_matching_tickets = get_all_matching_tickets()
    
    # 3. Filter for NEW tickets (those we haven't processed yet)
    new_tickets = [ticket for ticket in all_matching_tickets if ticket.get('id', 0) > last_id]
    
    slack_alert_messages = [] 
    sms_alert_messages = []
    
    # Variable to track the highest ID that was successfully formatted
    last_successfully_formatted_id = 0 

    if new_tickets:
        print(f"Processing {len(new_tickets)} new ticket(s)...")
        
        for ticket in new_tickets:
            # 1. Format the message for Slack (rich text)
            slack_message = format_ticket_message(ticket, for_slack=True) 
            slack_alert_messages.append(slack_message)
            
            # 2. Format the message for SMS (plain text)
            sms_message = format_ticket_message(ticket, for_slack=False)
            sms_alert_messages.append(sms_message)
            
            # Use the newest ID for updating the log file
            last_successfully_formatted_id = max(last_successfully_formatted_id, ticket.get('id', 0))
        
        # --- PREPARE MESSAGES ---
        
        # 1. Slack Message (using rich format)
        slack_title = f"🚨 {len(new_tickets)} NEW ConnectWise Ticket Alert(s)"
        slack_body = "\n".join(slack_alert_messages) 

        # 2. SMS Message
        consolidated_alert_string = " / ".join(sms_alert_messages)
        consolidated_subject = f"CW Alert: {consolidated_alert_string}"
        consolidated_body = ""

        # --- SEND ALERTS ---

        # A. Send to Slack URGENT Webhook (New Tickets)
        slack_success = send_slack_webhook(slack_title, slack_body, webhook_url=SLACK_WEBHOOK_URL_URGENT)
        
        # B. Send to SMS via Email Gateway 
        sms_success = send_email(consolidated_subject, consolidated_body, SMS_RECIPIENT_EMAIL)
        
    # --- UPDATE LAST ID LOGIC (The Fix for Repeating Alerts) ---
    
    # NEW LOGIC: Instead of writing to a file (which is lost), print the ID 
    # using the GitHub Actions command format so the workflow can capture it.
    if last_successfully_formatted_id > 0:
        # This print line sets an output variable named 'next_id' in the GitHub Actions step
        print(f"::set-output name=next_id::{last_successfully_formatted_id}")
        print(f"✅ New highest ticket ID processed: {last_successfully_formatted_id}. This value will be saved for the next run.")

        # Revert to local file writing for local testing only
        if not os.environ.get('LAST_RUN_ID'):
            try:
                with open('last_run_id.txt', 'w') as f:
                    f.write(str(last_successfully_formatted_id))
            except Exception as e:
                print(f"🛑 ERROR: Could not write last processed ID to file (Local Test Only). Error: {e}")
    elif new_tickets:
        print("⚠️ No new ID to log, perhaps ticket IDs were not integers.")
    else: # No NEW tickets found
    
        # Check if ANY tickets exist at all (old or new)
        if len(all_matching_tickets) > 0:
            print(f"No NEW tickets found, but {len(all_matching_tickets)} existing tickets still match criteria. Sending status update to Slack.")
            
            # 1. Format all existing tickets for the Slack status message
            slack_status_messages = []
            for ticket in all_matching_tickets:
                slack_status_messages.append(format_ticket_message(ticket, for_slack=True))

            # 2. Send Status Update to REGULAR Webhook
            status_title = f"⚠️ {len(all_matching_tickets)} Existing Ticket(s) Acknowledged"
            status_body = "\n".join(slack_status_messages)
            # Yellow/Orange color (16776960 is decimal for #FFFF00)
            send_slack_webhook(status_title, status_body, color=16776960, webhook_url=SLACK_WEBHOOK_URL_REGULAR) 
            
        else:
            # TRULY NO tickets exist at all - Send the 'All Scheduled' status message to REGULAR Webhook
            print("No new tickets and no existing tickets found on the monitored board/status.")
            no_ticket_title = "✅ Ticket Status Update"
            no_ticket_body = "All Current Tickets are Scheduled"
            # Green color (3066993 is decimal for #2ecc71)
            send_slack_webhook(no_ticket_title, no_ticket_body, color=3066993, webhook_url=SLACK_WEBHOOK_URL_REGULAR) 
            
    print("--- Script Finished ---")

