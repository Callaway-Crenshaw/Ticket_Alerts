# config.py
# This file imports the 'os' module to read all necessary
# configuration values from the GitHub Actions environment variables.

import os

# ConnectWise API Credentials
CW_COMPANY_ID = os.environ.get('CW_COMPANY_ID')
CW_PUBLIC_KEY = os.environ.get('CW_PUBLIC_KEY')
CW_PRIVATE_KEY = os.environ.get('CW_PRIVATE_KEY')
CW_CLIENT_ID = os.environ.get('CW_CLIENT_ID')
CW_BASE_URL = os.environ.get('CW_BASE_URL')

# ConnectWise Monitoring Settings
CW_BOARD_NAME = os.environ.get('CW_BOARD_NAME')
CW_STATUS_NAME = os.environ.get('CW_STATUS_NAME')

# Slack Webhooks
SLACK_WEBHOOK_URL_REGULAR = os.environ.get('SLACK_WEBHOOK_URL_REGULAR')
SLACK_WEBHOOK_URL_URGENT = os.environ.get('SLACK_WEBHOOK_URL_URGENT')

# SMS/Email Settings
SMTP_SERVER = os.environ.get('SMTP_SERVER')
# Convert port to integer, defaulting to 587 if not found/invalid
try:
    SMTP_PORT = int(os.environ.get('SMTP_PORT'))
except (TypeError, ValueError):
    SMTP_PORT = 587

SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
SMS_RECIPIENT_EMAILS = [
    "12627575505@txt.att.net",
    "14054039513@vtext.com"]
