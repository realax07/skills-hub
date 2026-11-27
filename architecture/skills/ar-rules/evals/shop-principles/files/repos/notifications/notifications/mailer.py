import os

import requests


def send_email(to: str, subject: str, text: str) -> None:
    r = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {os.environ['SENDGRID_API_KEY']}"},
        json={"personalizations": [{"to": [{"email": to}]}], "from": {"email": "shop@example.com"},
              "subject": subject, "content": [{"type": "text/plain", "value": text}]},
        timeout=10,
    )
    r.raise_for_status()
