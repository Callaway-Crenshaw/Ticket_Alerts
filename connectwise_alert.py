import requests
import base64
import json
import datetime
# Re-adding imports required for SMS/Email
import smtplib
from email.message import EmailMessage
# We keep the import for config, assuming SLACK_WEBHOOK_URLs and CW credentials are here.
# NOTE: Ensure SLACK_WEBHOOK_URL_REGULAR and SLACK_WEBHOOK_URL_URGENT are defined in your config.py
from config import *

# --- 1. CONNECTWISE API FUNCTION ---
def get_all_matching_tickets():
    """
    Connects to CW API and retrieves ALL tickets based on the configured 
    board/status names (ignoring last_id for now).
    Returns a list of all ticket objects matching the criteria.
    """
    all_tickets = []

    # 1. Prepare Authentication Header (uses Basic Auth)
    # Format is CompanyID+PublicKey:PrivateKey
    auth_string = f"{CW_COMPANY_ID}+{CW_PUBLIC_KEY}:{CW_PRIVATE_KEY}"
    encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')

    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "clientID": CW_CLIENT_ID,
        "Content-Type": "application/json"
    }

    # 2. Define the API Request URL and Filter
    # CRITICAL CHANGE: Filter for the correct board and status, but NOT by ID
    conditions = f"board/name=\"{CW_BOARD_NAME}\" and status/name=\"{CW_STATUS_NAME}\""
    url = f"{CW_BASE_URL}/service/tickets?conditions={conditions}&orderBy=id asc&pageSize=100"

    print(f"Checking CW API for ALL matching tickets with condition: {conditions}")
    
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

# --- 2. ALERTING FUNCTIONS ---

# MODIFICATION: Added optional 'webhook_url' argument, defaulting to REGULAR
def send_slack_webhook(message_title, message_body, color=16711680, webhook_url=SLACK_WEBHOOK_URL_REGULAR):
    """
    Sends an alert message using a Slack Webhook to the specified URL.
    Uses the 'attachments' format to include a color sidebar, title, and body.
    Default color is Red (16711680) for alerts.
    """
    # NOTE: Checks the passed/default webhook_url
    if not webhook_url or webhook_url == "SLACK_WEBHOOK_URL_REGULAR" or webhook_url == "SLACK_WEBHOOK_URL_URGENT":
        # A simple check in case the config file has the placeholder
        print(f"⚠️ Slack Webhook URL ({'URGENT' if webhook_url == SLACK_WEBHOOK_URL_URGENT else 'REGULAR'}) not configured. Skipping Slack alert.")
        return False
    
    # Slack colors are hex strings, Discord colors were decimal integers.
    # Convert the decimal integer to a 6-digit hex string for Slack.
    hex_color = f'#{color:06x}'

    # Slack Attachment structure for rich formatting with a color bar
    payload = {
        "attachments": [
            {
                "color": hex_color, 
                # Title uses an optional leading emoji/indicator which is handled in __main__
                "title": message_title,
                "text": message_body,
                # Use Unix timestamp (seconds since epoch) for Slack's timestamp
                "ts": int(datetime.datetime.now().timestamp()),
                "footer": "Automated ConnectWise Alert"
            }
        ]
    }

    try:
        response = requests.post(
            webhook_url, # CRITICAL CHANGE: Use the specific or default URL
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
        
        if color == 3066993: # Green color for 'All Scheduled' success
            print("✅ Slack 'All Current Tickets are Scheduled' confirmation sent.")
        elif color == 16776960: # Yellow/Orange color for 'Existing Tickets' status
            print("✅ Slack existing ticket status update sent.")
        else:
            print(f"✅ Slack Webhook alert sent successfully to {'URGENT' if webhook_url == SLACK_WEBHOOK_URL_URGENT else 'REGULAR'} channel.") # Updated print statement
            
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
        # Connect to SMTP server (using STARTTLS for port 587)
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD) # Uses the App Password
            server.send_message(msg)
        print("✅ SMS/Email alert sent successfully.")
        return True
    except Exception as e:
        print(f"🛑 Failed to send consolidated email/SMS. Error: {e}")
        return False

def format_ticket_message(ticket, for_slack=False):
    """
    Formats a single ticket's data into a concise string.
    Returns rich format for Slack (by setting for_slack=True) by default, or plain format for SMS.
    """
    
    priority_name = ticket.get('priority', {}).get('name', 'N/A')
    site_name = ticket.get('site', {}).get('name', 'N/A')
    
    # Map long priority names to concise abbreviations
    priority_map = {
        'Priority 1 - Critical': 'P1-CRIT',
        'Priority 2 - High': 'P2-HIGH',
        'Priority 3 - Medium': 'P3-MED',
        'Priority 4 - Low': 'P4-LOW',
        'N/A': 'N/A'
    }
    abbreviated_priority = priority_map.get(priority_name, priority_name)
    
    # Renamed parameter to be more explicit for the new target
    if for_slack:
        # Rich Format for Slack/Discord Embed: TICKETID | PRIORITY | SITE_NAME
        # Slack uses Markdown for formatting (bold via *, inline code via `)
        return f"`{ticket['id']}` | *{abbreviated_priority}* | {site_name}"
    else:
        # Plain Format for SMS/Email Subject: TICKETID | PRIORITY | SITE_NAME
        return f"{ticket['id']} | {abbreviated_priority} | {site_name}"

# --- 3. MAIN EXECUTION ---
if __name__ == "__main__":
    
    print("--- ConnectWise Ticket Alert Script Started ---")
    
    # 1. Read the last processed ID from the file (The "Alert Once" Logic)
    try:
        with open('last_run_id.txt', 'r') as f:
            last_id_content = f.read().strip()
            last_id = int(last_id_content) if last_id_content.isdigit() else 0
    except Exception:
        last_id = 0  # Start from 0 if file is missing or cannot be read
    
    print(f"Last processed ID: {last_id}")

    # 2. Get ALL tickets matching the criteria
    all_matching_tickets = get_all_matching_tickets()
    
    # 3. Filter for NEW tickets (those we haven't processed yet)
    new_tickets = [ticket for ticket in all_matching_tickets if ticket['id'] > last_id]
    
    # Lists to store successfully formatted messages
    slack_alert_messages = [] 
    sms_alert_messages = []
    
    # Variable to track the highest ID that was successfully processed
    last_successfully_formatted_id = 0 
    
    # Flags to track success of each alert type
    slack_success = False 
    sms_success = False

    if new_tickets:
        print(f"Processing {len(new_tickets)} new ticket(s)...")
        
        for ticket in new_tickets:
            # 1. Format the message for Slack (rich text)
            # NOTE: Updated format_ticket_message parameter to reflect new target
            slack_message = format_ticket_message(ticket, for_slack=True) 
            slack_alert_messages.append(slack_message)
            
            # 2. Format the message for SMS (plain text)
            sms_message = format_ticket_message(ticket, for_slack=False)
            sms_alert_messages.append(sms_message)
            
            # Use the newest ID for updating the log file
            last_successfully_formatted_id = max(last_successfully_formatted_id, ticket['id'])
        
        # --- PREPARE MESSAGES ---
        
        # 1. Slack Message (using rich format)
        slack_title = f"🚨 {len(new_tickets)} NEW ConnectWise Ticket Alert(s)"
        slack_body = "\n".join(slack_alert_messages) 

        # 2. SMS Message (Compact format for subject line)
        consolidated_alert_string = " / ".join(sms_alert_messages)
        consolidated_subject = f"CW Alert: {consolidated_alert_string}"
        consolidated_body = "" # SMS body is usually left blank when the subject is the content

        # --- SEND ALERTS ---

        # A. Send to Slack URGENT Webhook (New Tickets)
        # CRITICAL CHANGE: Pass SLACK_WEBHOOK_URL_URGENT
        slack_success = send_slack_webhook(slack_title, slack_body, webhook_url=SLACK_WEBHOOK_URL_URGENT)
        
        # B. Send to SMS via Email Gateway (ONLY sent if tickets are found)
        sms_success = send_email(consolidated_subject, consolidated_body, SMS_RECIPIENT_EMAIL)
        
        # --- UPDATE LAST ID LOGIC ---
        
        # Update last_run_id.txt ONLY if at least one alert method succeeded
        send_success = slack_success or sms_success 
        
        if send_success:
            if last_successfully_formatted_id > 0:
                try:
                    with open('last_run_id.txt', 'w') as f:
                        f.write(str(last_successfully_formatted_id))
                    print(f"✅ Last processed ID successfully updated to: {last_successfully_formatted_id}")
                except Exception as e:
                    print(f"🛑 ERROR: Could not write last processed ID to file. Error: {e}")
            else:
                # Should not happen if new_tickets > 0, but good practice
                print("⚠️ No new ID to log, but alerts succeeded.")
        else:
            print("🛑 ALL ALERTS FAILED. last_run_id.txt remains unchanged.")
            
    else: # No NEW tickets found
        
        # Check if ANY tickets exist at all (old or new)
        if len(all_matching_tickets) > 0:
            print(f"No NEW tickets found, but {len(all_matching_tickets)} existing tickets still match criteria. Sending status update to Slack.")
            
            # 1. Format all existing tickets for the Slack status message
            slack_status_messages = []
            for ticket in all_matching_tickets:
                # Use format_ticket_message with for_slack=True for rich formatting
                slack_status_messages.append(format_ticket_message(ticket, for_slack=True))

            # 2. Send Status Update to REGULAR Webhook
            status_title = f"⚠️ {len(all_matching_tickets)} Existing Ticket(s) Acknowledged"
            status_body = "\n".join(slack_status_messages)
            # Use Yellow/Orange color (16776960 is decimal for #FFFF00)
            # CRITICAL CHANGE: Pass SLACK_WEBHOOK_URL_REGULAR
            send_slack_webhook(status_title, status_body, color=16776960, webhook_url=SLACK_WEBHOOK_URL_REGULAR) 
            
        else:
            # TRULY NO tickets exist at all - Send the 'All Scheduled' status message to REGULAR Webhook
            print("No new tickets and no existing tickets found on the monitored board/status.")
            no_ticket_title = "✅ Ticket Status Update"
            no_ticket_body = "All Current Tickets are Scheduled"
            # Use Green color (3066993 is decimal for #2ecc71) for the success message
            # CRITICAL CHANGE: Pass SLACK_WEBHOOK_URL_REGULAR
            send_slack_webhook(no_ticket_title, no_ticket_body, color=3066993, webhook_url=SLACK_WEBHOOK_URL_REGULAR) 
        
        # SMS is SKIPPED entirely when no NEW tickets are found.
    
    print("--- Script Finished ---")