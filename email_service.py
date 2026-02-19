# email_service.py

import os
import requests

KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY")

def send_email(to, subject, html):
    url = "https://a.klaviyo.com/api/email-send"

    headers = {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "from_email": "brandonbarbee512@gmail.com",
        "from_name": "The SSSSource",
        "subject": subject,
        "to": [{"email": to}],
        "html": html
    }

    # Make the API request
    response = requests.post(url, json=payload, headers=headers)

    # ⭐ THIS is where the log line must go ⭐
    print("KLAVIYO RESPONSE:", response.status_code, response.text)

    return response
