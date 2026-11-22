"""Channel providers (ADR-005, ADR-011). Each returns a `Result`; none raises for a refused message
(that is a delivery failure with a reason), only `Transient` for a retryable network problem.

Credentials are read from the environment variable NAMED on the ChannelConfig — never stored in
the database.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

WHATSAPP_API = os.environ.get("WHATSAPP_API_BASE", "https://graph.facebook.com/v20.0")
TIMEOUT = 15


@dataclass
class Result:
    status: str  # sent | delivered | failed | simulated
    ref: str = ""
    error: str = ""


class Transient(Exception):
    """Network / 5xx / rate limit — retry later."""


def _secret(cfg) -> str:
    return os.environ.get(cfg.credential_env, "") if cfg.credential_env else ""


def _http(req: urllib.request.Request) -> tuple[int, str]:
    """Isolated for tests (patched)."""
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 — https endpoints from config
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise Transient(str(exc)) from exc


def log_only(msg, cfg) -> Result:
    return Result("simulated", ref=f"log-{msg.pk}")


def whatsapp_cloud(msg, cfg) -> Result:
    token = _secret(cfg)
    if not (token and cfg.sender):
        return Result("failed", error="WhatsApp is not configured (phone-number id or token missing).")
    to = "".join(ch for ch in msg.to if ch.isdigit())
    if len(to) == 10:
        to = "91" + to
    if msg.provider_template:
        name, _, lang = msg.provider_template.partition(":")
        payload = {"messaging_product": "whatsapp", "to": to, "type": "template",
                   "template": {"name": name, "language": {"code": lang or ("hi" if msg.language == "hi" else "en")},
                                "components": [{"type": "body", "parameters": [{"type": "text", "text": msg.body[:1000]}]}]}}
    else:  # free text only works inside a 24-hour customer window; templates are the norm
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": msg.body[:4000]}}
    req = urllib.request.Request(f"{WHATSAPP_API}/{cfg.sender}/messages", data=json.dumps(payload).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    status, body = _http(req)
    if status == 429 or status >= 500:
        raise Transient(f"WhatsApp HTTP {status}")
    try:
        data = json.loads(body or "{}")
    except ValueError:
        data = {}
    if 200 <= status < 300 and data.get("messages"):
        return Result("sent", ref=data["messages"][0].get("id", ""))
    err = (data.get("error") or {}).get("message") or f"HTTP {status}"
    return Result("failed", error=f"WhatsApp: {err}"[:500])


def sms_http(msg, cfg) -> Result:
    """Generic DLT SMS gateway: `endpoint` is a URL template with {to} {text} {sender} {template_id} {key}."""
    key = _secret(cfg)
    if not (cfg.endpoint and cfg.sender):
        return Result("failed", error="SMS gateway is not configured (URL or DLT sender missing).")
    to = "".join(ch for ch in msg.to if ch.isdigit())[-10:]
    q = urllib.parse.quote
    url = (cfg.endpoint.replace("{to}", q(to)).replace("{text}", q(msg.body)).replace("{sender}", q(cfg.sender))
           .replace("{template_id}", q(msg.provider_template)).replace("{key}", q(key)))
    if not url.startswith("https://"):
        return Result("failed", error="SMS gateway URL must use https.")
    status, body = _http(urllib.request.Request(url, method="GET"))
    if status == 429 or status >= 500:
        raise Transient(f"SMS HTTP {status}")
    if 200 <= status < 300:
        ref = ""
        try:
            data = json.loads(body)
            ref = str(data.get("id") or data.get("message_id") or data.get("request_id") or "")
        except ValueError:
            ref = body.strip()[:120]
        return Result("sent", ref=ref)
    return Result("failed", error=f"SMS gateway: HTTP {status} {body[:200]}")


def smtp(msg, cfg) -> Result:
    from django.core.mail import EmailMessage
    from django.conf import settings

    subject = msg.body.split(":", 1)[0][:80] if ":" in msg.body[:80] else "Message from your institution"
    try:
        EmailMessage(subject=subject, body=msg.body, from_email=cfg.sender or settings.DEFAULT_FROM_EMAIL, to=[msg.to]).send()
    except OSError as exc:
        raise Transient(str(exc)) from exc
    except Exception as exc:  # SMTP refused the address etc.
        return Result("failed", error=f"Email: {exc}"[:500])
    return Result("sent")


SEND = {"log_only": log_only, "whatsapp_cloud": whatsapp_cloud, "sms_http": sms_http, "smtp": smtp}
