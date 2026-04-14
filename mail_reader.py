import imaplib
import email
import re

import os
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file
app_password = os.getenv("app_password")

# --- Config ---
EMAIL         = "opmcaped@gmail.com"
PASSWORD      = app_password
TARGET_SENDER = "narutouzumaki99871@gmail.com"


def connect():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, PASSWORD)
    mail.select("inbox")
    return mail


def get_tweets_from_mail():
    mail = connect()

    _, data = mail.search(None, f'UNSEEN FROM "{TARGET_SENDER}"')
    email_ids = data[0].split()

    tweets = []

    for eid in email_ids:
        _, msg_data = mail.fetch(eid, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        # Get body
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="ignore").strip()
                    break
        else:
            body = msg.get_payload(decode=True).decode(errors="ignore").strip()

        # Parse "link : ..." and "context : ..." directly from the email body
        link_match    = re.search(r'link\s*:\s*(https?://\S+)', body, re.IGNORECASE)
        context_match = re.search(r'context\s*:\s*(.+)', body, re.IGNORECASE)

        if not link_match:
            continue  # skip if no link found

        tweets.append({
            "link":    link_match.group(1).strip(),
            "context": context_match.group(1).strip() if context_match else ""
        })

    mail.logout()
    return tweets


# --- Run ---
if __name__ == "__main__":
    tweets = get_tweets_from_mail()
    print(tweets)

    for i, tweet in enumerate(tweets): 
        print(f"Tweet {i+1}:")
        print("link:", tweets[i]["link"])
        print("context:", tweets[i]["context"])
        print("=="*50)
