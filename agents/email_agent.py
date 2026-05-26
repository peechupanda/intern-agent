"""
Email Agent — Gmail-powered recruiter inbox monitor + AI draft responder
Monitors inbox for recruiter replies and drafts responses using Groq/Llama.

Usage:
    python -m agents.email_agent              # monitor + draft replies
    python -m agents.email_agent --check-only # just print unread recruiter emails
    python -m agents.email_agent --auth-only  # just authenticate and exit
"""

import os
import base64
import json
import logging
import argparse
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from groq import Groq

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

# Keywords to identify recruiter/internship emails
RECRUITER_KEYWORDS = [
    "internship", "intern", "opportunity", "application", "interview",
    "shortlisted", "selected", "offer", "hiring", "position", "role",
    "recruiter", "hr", "talent", "candidate", "resume", "cv",
    "assessment", "test", "assignment", "next steps", "follow up"
]


# ---------------------------------------------------------------------------
# Gmail Auth
# ---------------------------------------------------------------------------

def get_gmail_service():
    """Authenticate and return Gmail API service."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"credentials.json not found. Download it from Google Cloud Console "
                    f"and place it in the project root."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        log.info("✅ Gmail authenticated — token saved to token.json")

    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Email Fetching
# ---------------------------------------------------------------------------

def get_message_body(service, msg_id: str) -> str:
    """Extract plain text body from a Gmail message."""
    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()

        payload = msg.get("payload", {})
        parts = payload.get("parts", [])

        # Single-part message
        if not parts:
            data = payload.get("body", {}).get("data", "")
            if data:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        # Multi-part — look for text/plain
        for part in parts:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        # Fallback to text/html
        for part in parts:
            if part.get("mimeType") == "text/html":
                data = part.get("body", {}).get("data", "")
                if data:
                    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

        return ""
    except Exception as e:
        log.warning(f"Could not extract body for {msg_id}: {e}")
        return ""


def get_email_headers(msg: dict) -> dict:
    """Extract From, Subject, Date from message headers."""
    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "from":    headers.get("From", "Unknown"),
        "subject": headers.get("Subject", "(no subject)"),
        "date":    headers.get("Date", ""),
        "to":      headers.get("To", ""),
        "message_id": headers.get("Message-ID", ""),
    }


def fetch_recruiter_emails(service, max_results: int = 20) -> list[dict]:
    """Fetch unread emails likely from recruiters."""
    log.info("📬 Scanning inbox for recruiter emails...")

    # Build Gmail search query
    keyword_query = " OR ".join(f'"{kw}"' for kw in RECRUITER_KEYWORDS[:10])
    query = f"is:unread ({keyword_query})"

    try:
        results = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            log.info("📭 No unread recruiter emails found")
            return []

        log.info(f"📨 Found {len(messages)} potential recruiter email(s)")

        emails = []
        for m in messages:
            try:
                msg = service.users().messages().get(
                    userId="me", id=m["id"], format="full"
                ).execute()

                headers = get_email_headers(msg)
                body = get_message_body(service, m["id"])

                emails.append({
                    "id":         m["id"],
                    "thread_id":  msg.get("threadId", ""),
                    "from":       headers["from"],
                    "subject":    headers["subject"],
                    "date":       headers["date"],
                    "to":         headers["to"],
                    "message_id": headers["message_id"],
                    "body":       body[:3000],  # cap at 3000 chars for LLM
                    "snippet":    msg.get("snippet", ""),
                })
            except Exception as e:
                log.warning(f"Could not fetch email {m['id']}: {e}")
                continue

        return emails

    except HttpError as e:
        log.error(f"❌ Gmail API error: {e}")
        return []


# ---------------------------------------------------------------------------
# AI Draft Generation
# ---------------------------------------------------------------------------

def draft_reply(email: dict, profile: dict) -> str:
    """Use Groq/Llama to draft a reply to a recruiter email."""
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    candidate_summary = f"""
Name: {profile.get('name', 'Pratyush Talwar')}
College: {profile.get('college', 'Delhi Technological University')}
Degree: {profile.get('degree', 'B.Tech Information Technology')}
Year: {profile.get('year', '1st Year')}
Skills: {', '.join(profile.get('skills', {}).get('languages', []) + profile.get('skills', {}).get('frontend', []) + profile.get('skills', {}).get('backend', []))}
""".strip()

    prompt = f"""You are drafting a professional reply to a recruiter email on behalf of a student.

CANDIDATE PROFILE:
{candidate_summary}

RECRUITER EMAIL:
From: {email['from']}
Subject: {email['subject']}
Body:
{email['body'][:2000]}

INSTRUCTIONS:
- Write a concise, professional reply (150-250 words)
- Be enthusiastic but not desperate
- If it's an interview invite: confirm availability and ask for details
- If it's a rejection: thank them gracefully and ask to be considered for future roles
- If it's a shortlist/next steps: express excitement and ask what to prepare
- If it's an assessment/task: acknowledge receipt and confirm submission timeline
- Sign off as {profile.get('name', 'Pratyush Talwar')}
- Do NOT include a subject line, just the email body

Write only the email body, nothing else.
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        temperature=0.7,
    )

    return response.choices[0].message.content.strip()


def save_draft(service, to: str, subject: str, body: str, thread_id: str = None) -> str:
    """Save a draft reply in Gmail."""
    message = MIMEMultipart()
    message["to"] = to
    message["subject"] = f"Re: {subject}" if not subject.startswith("Re:") else subject

    message.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft_body = {"message": {"raw": raw}}

    if thread_id:
        draft_body["message"]["threadId"] = thread_id

    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return draft["id"]


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

def run_email_agent(check_only: bool = False, max_emails: int = 10) -> list[dict]:
    """
    Main entry point for the email agent.
    Returns list of processed email results.
    """
    log.info("\n" + "="*60)
    log.info("  Email Agent — Gmail Monitor + AI Drafter")
    log.info("="*60)

    # Load profile
    try:
        from tools.profile_loader import load_profile
        profile = load_profile()
    except Exception:
        profile = {"name": "Pratyush Talwar"}

    # Authenticate
    try:
        service = get_gmail_service()
    except Exception as e:
        log.error(f"❌ Gmail auth failed: {e}")
        return []

    # Fetch recruiter emails
    emails = fetch_recruiter_emails(service, max_results=max_emails)
    if not emails:
        return []

    results = []

    for i, email in enumerate(emails, 1):
        log.info(f"\n  [{i}/{len(emails)}] {email['subject']}")
        log.info(f"  From   : {email['from']}")
        log.info(f"  Date   : {email['date']}")
        log.info(f"  Snippet: {email['snippet'][:100]}...")

        result = {
            "email_id":  email["id"],
            "from":      email["from"],
            "subject":   email["subject"],
            "date":      email["date"],
            "draft_id":  None,
            "draft_body": None,
            "error":     None,
        }

        if not check_only:
            try:
                log.info("  🤖 Drafting reply with Llama...")
                draft_body = draft_reply(email, profile)
                result["draft_body"] = draft_body

                draft_id = save_draft(
                    service,
                    to=email["from"],
                    subject=email["subject"],
                    body=draft_body,
                    thread_id=email["thread_id"],
                )
                result["draft_id"] = draft_id

                log.info(f"  ✅ Draft saved (ID: {draft_id})")
                log.info(f"\n  --- DRAFT PREVIEW ---")
                log.info(draft_body[:300] + "..." if len(draft_body) > 300 else draft_body)
                log.info(f"  ---------------------")

            except Exception as e:
                log.error(f"  ❌ Draft failed: {e}")
                result["error"] = str(e)

        results.append(result)

    log.info(f"\n✅ Email agent complete — {len(results)} email(s) processed")
    if not check_only:
        log.info("  📝 Drafts saved to Gmail — review before sending!")

    return results


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Email Agent — Gmail monitor + AI drafter")
    parser.add_argument("--check-only", action="store_true",
                        help="Only list recruiter emails, don't draft replies")
    parser.add_argument("--auth-only", action="store_true",
                        help="Just authenticate Gmail and exit")
    parser.add_argument("--max", type=int, default=10,
                        help="Max emails to process (default: 10)")
    args = parser.parse_args()

    if args.auth_only:
        service = get_gmail_service()
        log.info("✅ Authentication successful!")
    else:
        run_email_agent(check_only=args.check_only, max_emails=args.max)