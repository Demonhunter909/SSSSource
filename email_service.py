import os
import requests

BREVO_API_KEY = os.getenv("BREVO_API_KEY")

def send_email(to, subject, html):
    print("SEND_EMAIL FUNCTION WAS CALLED (BREVO)")

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "api-key": BREVO_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "sender": {
            "email": "brandonbarbee512@gmail.com",
            "name": "The SSSSource"
        },
        "to": [
            {"email": to}
        ],
        "subject": subject,
        "htmlContent": html
    }

    response = requests.post(url, json=payload, headers=headers)

    print("BREVO RESPONSE:", response.status_code, response.text)

    return response
