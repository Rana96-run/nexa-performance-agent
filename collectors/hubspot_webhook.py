"""
collectors/hubspot_webhook.py
==============================
Flask Blueprint — receives HubSpot webhook events, acts on them in real time.

Priority order (most → least important):
  1. Lead module (0-136)  — lead.creation, lead.propertyChange → hs_pipeline_stage
  2. Deal                 — deal.propertyChange → dealstage
  3. Contact (fallback)   — contact.propertyChange → lifecyclestage / hs_lead_status

The Lead module (0-136) is the primary CRM object used by the ops team.
Qualification / disqualification is driven by hs_pipeline_stage labels
(e.g. "Qualified", "Disqualified"), NOT by contact lifecyclestage.

Signature verification
-----------------------
HubSpot v3: HMAC-SHA256( client_secret, method + url + body + timestamp )
The existing HUBSPOT_CLIENT_SECRET env var is used — no new secret needed.

HubSpot webhook subscription setup (Settings -> Private Apps -> Webhooks)
---------------------------------------------------------------------------
Object   | Subscription type         | Property
---------|---------------------------|------------------
lead     | lead.creation             | (all creations)
lead     | lead.propertyChange       | hs_pipeline_stage
deal     | deal.propertyChange       | dealstage
contact  | contact.propertyChange    | lifecyclestage    (optional fallback)

Target URL: https://<your-railway-domain>/webhooks/hubspot
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import requests
from flask import Blueprint, abort, jsonify, request
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import HUBSPOT_TOKEN, SLACK_BOT_TOKEN, SLACK_CHANNEL_NOTIFY

hubspot_bp = Blueprint("hubspot_webhook", __name__)

# ─── Config ───────────────────────────────────────────────────────────────────
_WEBHOOK_SECRET = (
    os.getenv("HUBSPOT_WEBHOOK_SECRET") or os.getenv("HUBSPOT_CLIENT_SECRET", "")
)
_SLACK   = WebClient(token=SLACK_BOT_TOKEN)
_BASE    = "https://api.hubapi.com"
_LEAD_OBJ = "0-136"

# Lead module properties to fetch when an event fires
_LEAD_PROPS = [
    "hs_pipeline", "hs_pipeline_stage", "hs_lead_is_open",
    "lead_qoyod_source",
    "lead_utm_campaign", "lead_utm_audience", "lead_utm_content",
    "lead_utm_source", "lead_utm_medium",
    "leads_disqualification_reason__ops",
    "leads_disqualification_reason__ops_qflavour",
    "disqualification_reason_bookkeeping",
    # Associated contact fields (fetched via association if needed)
    "hs_object_id",
]

# Deal properties
_DEAL_PROPS = [
    "dealname", "dealstage", "amount", "currency",
    "deal_utm_campaign", "deal_utm_content", "deal_qoyod_source",
]

# Contact properties (fallback path only)
_CONTACT_PROPS = [
    "firstname", "lastname", "email", "company",
    "hs_analytics_source", "lead_utm_campaign", "lead_utm_content",
]

# Stage label keywords — matched case-insensitively against hs_pipeline_stage label
_QUAL_KEYWORDS  = {"qualified"}
_DISQ_KEYWORDS  = {"disqualified"}
_EXCL_KEYWORDS  = {"dis"}   # exclude "disqualified" from "qualified" match

# Deal stages
_WON_STAGE  = "closedwon"
_LOST_STAGE = "closedlost"


# ─── Signature verification ───────────────────────────────────────────────────

def _verify_signature(req: request) -> bool:
    """HMAC-SHA256 verification. Pass-through if secret not configured (dev)."""
    if not _WEBHOOK_SECRET:
        return True  # dev mode

    sig = req.headers.get("X-HubSpot-Signature-v3", "")
    ts  = req.headers.get("X-HubSpot-Request-Timestamp", "")
    if not sig or not ts:
        return False

    try:
        if abs(time.time() * 1000 - int(ts)) > 300_000:
            return False  # replay older than 5 min
    except ValueError:
        return False

    body = req.get_data(as_text=True)
    msg  = req.method + req.url + body + ts
    expected = hmac.new(
        _WEBHOOK_SECRET.encode(), msg.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig)


# ─── Pipeline stage cache ─────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _stage_map() -> dict[str, tuple[str, str]]:
    """
    Returns {stage_id: (pipeline_label, stage_label)} for the Lead object.
    Cached in-process; refreshes on next deploy.
    """
    try:
        r = requests.get(
            f"{_BASE}/crm/v3/pipelines/{_LEAD_OBJ}",
            headers={"Authorization": f"Bearer {HUBSPOT_TOKEN}"},
            timeout=10,
        )
        r.raise_for_status()
        result = {}
        for p in r.json().get("results", []):
            pl = p["label"]
            for s in p.get("stages", []):
                result[s["id"]] = (pl, s["label"])
        print(f"[webhook] Loaded {len(result)} Lead pipeline stages")
        return result
    except Exception as e:
        print(f"[webhook] Pipeline stage fetch failed: {e}")
        return {}


def _stage_label(stage_id: str) -> tuple[str, str]:
    """Returns (pipeline_label, stage_label) or ('', '') if unknown."""
    return _stage_map().get(stage_id, ("", ""))


def _is_qualified(stage_label: str) -> bool:
    sl = stage_label.lower()
    return any(k in sl for k in _QUAL_KEYWORDS) and not any(k in sl for k in _DISQ_KEYWORDS)


def _is_disqualified(stage_label: str) -> bool:
    return any(k in stage_label.lower() for k in _DISQ_KEYWORDS)


# ─── HubSpot API helpers ──────────────────────────────────────────────────────

def _hs_get(url: str) -> dict:
    try:
        r = requests.get(
            url, headers={"Authorization": f"Bearer {HUBSPOT_TOKEN}"}, timeout=8
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[webhook] GET {url} failed: {e}")
        return {}


def _get_lead(lead_id: str) -> dict:
    props = ",".join(_LEAD_PROPS)
    data = _hs_get(
        f"{_BASE}/crm/v3/objects/{_LEAD_OBJ}/{lead_id}"
        f"?properties={props}&associations=contacts"
    )
    return data.get("properties", {}), data.get("associations", {})


def _get_associated_contact(associations: dict) -> dict:
    """Fetch the first associated contact to get name/company."""
    try:
        contacts = associations.get("contacts", {}).get("results", [])
        if not contacts:
            return {}
        contact_id = contacts[0]["id"]
        props = ",".join(_CONTACT_PROPS)
        data = _hs_get(
            f"{_BASE}/crm/v3/objects/contacts/{contact_id}?properties={props}"
        )
        return data.get("properties", {})
    except Exception:
        return {}


def _get_deal(deal_id: str) -> dict:
    props = ",".join(_DEAL_PROPS)
    return _hs_get(
        f"{_BASE}/crm/v3/objects/deals/{deal_id}?properties={props}"
    ).get("properties", {})


def _deal_amount_usd(props: dict) -> float | None:
    raw = props.get("amount")
    if raw is None:
        return None
    try:
        amount = float(raw)
    except (ValueError, TypeError):
        return None
    currency = (props.get("currency") or "SAR").upper()
    if currency == "SAR":
        from config import USD_SAR_PEG
        return round(amount / USD_SAR_PEG, 2)
    return round(amount, 2)


# ─── Formatting helpers ───────────────────────────────────────────────────────

def _now_riyadh() -> str:
    tz = timezone(timedelta(hours=3))
    return datetime.now(tz).strftime("%d %b %Y %H:%M")


def _slack_post(blocks: list, text: str) -> None:
    try:
        _SLACK.chat_postMessage(
            channel=SLACK_CHANNEL_NOTIFY, blocks=blocks, text=text
        )
    except SlackApiError as e:
        print(f"[webhook] Slack error: {e}")


def _disq_reason(props: dict) -> str:
    return (
        props.get("leads_disqualification_reason__ops")
        or props.get("leads_disqualification_reason__ops_qflavour")
        or props.get("disqualification_reason_bookkeeping")
        or "—"
    )


# ─── Lead module handlers ─────────────────────────────────────────────────────

def _handle_lead_created(lead_id: str) -> None:
    """New Lead object created — quick Slack ping with source/UTM."""
    props, assoc = _get_lead(lead_id)
    contact      = _get_associated_contact(assoc)

    name = (
        f"{contact.get('firstname','')} {contact.get('lastname','')}".strip()
        or f"Lead {lead_id}"
    )
    src  = props.get("lead_qoyod_source") or "Unknown"
    cmp  = props.get("lead_utm_campaign") or "—"
    ctn  = props.get("lead_utm_content")  or "—"
    aud  = props.get("lead_utm_audience") or "—"
    pl_label, st_label = _stage_label(props.get("hs_pipeline_stage", ""))

    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f":inbox_tray: *New Lead — {name}*\n"
                f"*Source:* {src}  |  *Stage:* {st_label or 'New'}\n"
                f"*Campaign:* `{cmp}`  |  *Audience:* `{aud}`  |  *Content:* `{ctn}`\n"
                f"_Created {_now_riyadh()}_"
            ),
        },
    }]
    _slack_post(blocks, f"New Lead: {name} ({src})")
    print(f"[webhook] New lead {lead_id} ({name}) — {src} / {cmp}")


def _handle_lead_qualified(lead_id: str, stage_label: str) -> None:
    """Lead moved to a Qualified stage — Slack alert + Asana SQL task."""
    props, assoc = _get_lead(lead_id)
    contact      = _get_associated_contact(assoc)

    name = (
        f"{contact.get('firstname','')} {contact.get('lastname','')}".strip()
        or f"Lead {lead_id}"
    )
    company = contact.get("company") or "—"
    src     = props.get("lead_qoyod_source") or "Unknown"
    cmp     = props.get("lead_utm_campaign") or "—"
    ctn     = props.get("lead_utm_content")  or "—"

    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f":star: *Lead Qualified (SQL) — {name}*\n"
                f"*Company:* {company}  |  *Stage:* {stage_label}\n"
                f"*Source:* {src}  |  *Campaign:* `{cmp}`  |  *Content:* `{ctn}`\n"
                f"_Qualified {_now_riyadh()}_"
            ),
        },
    }]
    _slack_post(blocks, f"Lead Qualified: {name} from {src}")
    print(f"[webhook] Lead {lead_id} qualified as SQL ({stage_label})")

    try:
        from executors.asana import create_task
        create_task(
            title=f"SQL Follow-up — {name} ({company})",
            description=(
                f"Lead ID: {lead_id}\nName: {name}\nCompany: {company}\n"
                f"Source: {src}\nCampaign: {cmp}\nContent: {ctn}\n"
                f"Stage: {stage_label}\nQualified: {_now_riyadh()}"
            ),
            project_key="daily_activity",
            task_type="SQL Follow-up",
        )
    except Exception as e:
        print(f"[webhook] Asana task skipped: {e}")


def _handle_lead_disqualified(lead_id: str, stage_label: str) -> None:
    """Lead moved to a Disqualified stage — Slack alert with reason."""
    props, assoc = _get_lead(lead_id)
    contact      = _get_associated_contact(assoc)

    name   = (
        f"{contact.get('firstname','')} {contact.get('lastname','')}".strip()
        or f"Lead {lead_id}"
    )
    src    = props.get("lead_qoyod_source") or "Unknown"
    cmp    = props.get("lead_utm_campaign") or "—"
    reason = _disq_reason(props)

    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f":x: *Lead Disqualified — {name}*\n"
                f"*Stage:* {stage_label}  |  *Reason:* {reason}\n"
                f"*Source:* {src}  |  *Campaign:* `{cmp}`\n"
                f"_Disqualified {_now_riyadh()}_"
            ),
        },
    }]
    _slack_post(blocks, f"Lead Disqualified: {name} — {reason}")
    print(f"[webhook] Lead {lead_id} disqualified: {reason}")


def _handle_lead_stage_change(lead_id: str, new_stage_id: str) -> None:
    """Route a hs_pipeline_stage change to the right handler."""
    _, stage_label = _stage_label(new_stage_id)
    if not stage_label:
        # Stage ID not in cache — reload once and retry
        _stage_map.cache_clear()
        _, stage_label = _stage_label(new_stage_id)

    if _is_qualified(stage_label):
        _handle_lead_qualified(lead_id, stage_label)
    elif _is_disqualified(stage_label):
        _handle_lead_disqualified(lead_id, stage_label)
    else:
        print(f"[webhook] Lead {lead_id} moved to '{stage_label}' — no action needed")


# ─── Deal handlers ────────────────────────────────────────────────────────────

def _handle_deal_won(deal_id: str) -> None:
    p       = _get_deal(deal_id)
    name    = p.get("dealname") or f"Deal {deal_id}"
    amount  = _deal_amount_usd(p)
    src     = p.get("deal_qoyod_source") or "Unknown"
    cmp     = p.get("deal_utm_campaign") or "—"
    ctn     = p.get("deal_utm_content")  or "—"
    amt_str = f"${amount:,.2f}" if amount else "—"

    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f":trophy: *Deal Closed Won — {name}*\n"
                f"*Amount:* {amt_str} USD\n"
                f"*Source:* {src}  |  *Campaign:* `{cmp}`  |  *Content:* `{ctn}`\n"
                f"_Closed {_now_riyadh()}_"
            ),
        },
    }]
    _slack_post(blocks, f"Deal Won: {name} — {amt_str}")
    print(f"[webhook] Deal won: {name} ({amt_str})")


def _handle_deal_lost(deal_id: str) -> None:
    p    = _get_deal(deal_id)
    name = p.get("dealname") or f"Deal {deal_id}"
    print(f"[webhook] Deal lost: {name} — logged, no alert")


# ─── Contact handlers (fallback — lower priority than Lead module) ────────────

def _handle_contact_sql(contact_id: str) -> None:
    """Fires only if Lead module events are not configured."""
    props = _hs_get(
        f"{_BASE}/crm/v3/objects/contacts/{contact_id}"
        f"?properties={','.join(_CONTACT_PROPS)}"
    ).get("properties", {})
    name = f"{props.get('firstname','')} {props.get('lastname','')}".strip() or f"Contact {contact_id}"
    src  = props.get("hs_analytics_source") or "Unknown"
    cmp  = props.get("lead_utm_campaign") or "—"
    blocks = [{
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f":star: *New SQL (Contact) — {name}*\n"
                f"*Source:* {src}  |  *Campaign:* `{cmp}`\n"
                f"_Converted {_now_riyadh()}_"
            ),
        },
    }]
    _slack_post(blocks, f"New SQL: {name}")
    print(f"[webhook] Contact SQL: {contact_id} ({name})")


# ─── Event router ─────────────────────────────────────────────────────────────

def _route_event(event: dict) -> None:
    sub_type = event.get("subscriptionType", "")
    obj_id   = str(event.get("objectId", ""))
    prop     = event.get("propertyName", "")
    value    = event.get("propertyValue") or ""

    # ── Lead module (primary) ────────────────────────────────────────────────
    if sub_type == "lead.creation":
        _handle_lead_created(obj_id)

    elif sub_type == "lead.propertyChange":
        if prop == "hs_pipeline_stage":
            _handle_lead_stage_change(obj_id, value)

    # ── Deals ────────────────────────────────────────────────────────────────
    elif sub_type == "deal.propertyChange":
        if prop == "dealstage":
            if value.lower() == _WON_STAGE:
                _handle_deal_won(obj_id)
            elif value.lower() == _LOST_STAGE:
                _handle_deal_lost(obj_id)

    # ── Contacts (optional fallback) ─────────────────────────────────────────
    elif sub_type == "contact.propertyChange":
        if prop == "lifecyclestage" and value.lower() == "salesqualifiedlead":
            _handle_contact_sql(obj_id)


# ─── Flask routes ─────────────────────────────────────────────────────────────

@hubspot_bp.route("/webhooks/hubspot", methods=["POST"])
def receive_hubspot_events():
    """
    HubSpot POSTs a JSON array of events.
    Always return 200 — HubSpot retries non-2xx responses.
    """
    if not _verify_signature(request):
        print("[webhook] Signature verification failed")
        abort(401)

    try:
        events = request.get_json(force=True) or []
    except Exception:
        events = []

    if not isinstance(events, list):
        events = [events]

    print(f"[webhook] Received {len(events)} event(s)")
    for ev in events:
        try:
            _route_event(ev)
        except Exception as e:
            print(f"[webhook] Routing error: {e}  event={ev}")

    return jsonify({"received": len(events)}), 200


@hubspot_bp.route("/webhooks/hubspot", methods=["GET"])
def hubspot_health():
    """HubSpot verifies the endpoint with a GET before activating."""
    return jsonify({"status": "ok", "service": "nexa-hubspot-webhook"}), 200
