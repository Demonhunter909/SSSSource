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
        "from_email": "brandonbarbee512@gmail.com",  # or your verified sender
        "from_name": "The SSSSource",
        "subject": subject,
        "to": [{"email": to}],
        "html": html
    }

    response = requests.post(url, json=payload, headers=headers)

    # Optional: print errors to Render logs
    if response.status_code >= 300:
        print("Klaviyo Email Error:", response.status_code, response.text)
