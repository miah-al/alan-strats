"""
WhatsApp (and generic) notifications.

Two providers, picked by whichever env vars are set:

  CallMeBot (simplest, free, personal use):
    WHATSAPP_PHONE     e.g. +14155551234   (your own number, with country code)
    CALLMEBOT_APIKEY   the key CallMeBot DMs you after you message their number
    → one-time setup: https://www.callmebot.com/blog/free-api-whatsapp-messages/

  Twilio (production-grade, paid):
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_WHATSAPP_FROM   e.g. whatsapp:+14155238886  (Twilio sandbox/sender)
    WHATSAPP_PHONE         destination, e.g. +14155551234

send_whatsapp() returns (ok: bool, detail: str) and never raises — a failed
alert must never crash the caller.
"""
from __future__ import annotations

import os
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


def _env(*names: str) -> str:
    for n in names:
        v = os.environ.get(n, "")
        if v:
            return v.strip()
    return ""


def whatsapp_configured() -> bool:
    phone = _env("WHATSAPP_PHONE")
    return bool(phone and (_env("CALLMEBOT_APIKEY") or _env("TWILIO_ACCOUNT_SID")))


def send_whatsapp(message: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Send a WhatsApp message to WHATSAPP_PHONE via whichever provider is set."""
    phone = _env("WHATSAPP_PHONE")
    if not phone:
        return False, "WHATSAPP_PHONE not set"

    # Prefer CallMeBot when its key is present (zero-cost personal path).
    cmb = _env("CALLMEBOT_APIKEY")
    if cmb:
        try:
            url = ("https://api.callmebot.com/whatsapp.php?"
                   + urllib.parse.urlencode({"phone": phone, "text": message, "apikey": cmb}))
            with urllib.request.urlopen(url, timeout=timeout) as r:
                body = r.read().decode("utf-8", "ignore")
            ok = r.status == 200 and "ERROR" not in body.upper()
            return ok, (body[:200] if body else f"HTTP {r.status}")
        except Exception as e:
            return False, f"CallMeBot failed: {e}"

    sid = _env("TWILIO_ACCOUNT_SID")
    if sid:
        try:
            tok  = _env("TWILIO_AUTH_TOKEN")
            frm  = _env("TWILIO_WHATSAPP_FROM") or "whatsapp:+14155238886"
            to   = phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"
            data = urllib.parse.urlencode({"From": frm, "To": to, "Body": message}).encode()
            req  = urllib.request.Request(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", data=data)
            import base64
            auth = base64.b64encode(f"{sid}:{tok}".encode()).decode()
            req.add_header("Authorization", f"Basic {auth}")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return (r.status in (200, 201)), f"Twilio HTTP {r.status}"
        except Exception as e:
            return False, f"Twilio failed: {e}"

    return False, "No provider configured (set CALLMEBOT_APIKEY or TWILIO_ACCOUNT_SID)"
