"""
executors/cost_tracking.py
==========================
Resource-consumption tracking for the agent. Three things are priced:

  1. Anthropic / Claude token usage   →  llm_cost_usd(tokens_in, tokens_out)
  2. BigQuery bytes scanned           →  bq_cost_usd(bytes_scanned)
  3. Platform API HTTP calls          →  count via track_api_calls() context manager

All numbers come back in USD. Pricing is a constants dict — when Anthropic
or BQ change rates, edit one place.

Why a single module:
  - The activity_logger only needs to call helpers from here, not know pricing.
  - Wrappers stay thin: the LLM wrapper extracts response.usage and calls
    llm_cost_usd(); the BQ wrapper reads query_job.total_bytes_processed and
    calls bq_cost_usd().
  - Tests can monkey-patch one constant, not seven.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

# ─── Pricing (USD) ───────────────────────────────────────────────────────────
# Anthropic — Claude Sonnet 4.5 list price as of 2026-05.
# https://www.anthropic.com/pricing
LLM_PRICE_PER_M_INPUT  = 3.00      # per 1,000,000 input tokens
LLM_PRICE_PER_M_OUTPUT = 15.00     # per 1,000,000 output tokens

# BigQuery — on-demand pricing. $6.25 per TiB scanned (us-central1, 2026-05).
# https://cloud.google.com/bigquery/pricing
BQ_PRICE_PER_TIB_SCANNED = 6.25
BQ_BYTES_PER_TIB         = 1024 ** 4   # 1 TiB = 2^40 bytes


# ─── Pricing helpers ─────────────────────────────────────────────────────────
def llm_cost_usd(tokens_in: int, tokens_out: int) -> float:
    """Return the USD cost of one Anthropic call."""
    if tokens_in is None and tokens_out is None:
        return 0.0
    cost = (
        (tokens_in or 0)  / 1_000_000 * LLM_PRICE_PER_M_INPUT +
        (tokens_out or 0) / 1_000_000 * LLM_PRICE_PER_M_OUTPUT
    )
    return round(cost, 6)


def bq_cost_usd(bytes_scanned: int | None) -> float:
    """Return the USD cost of a BigQuery query given total_bytes_processed."""
    if not bytes_scanned:
        return 0.0
    return round(bytes_scanned / BQ_BYTES_PER_TIB * BQ_PRICE_PER_TIB_SCANNED, 6)


# ─── API call counter (thread-local) ─────────────────────────────────────────
# Monkey-patches httpx.Client.send and requests.Session.send for the duration
# of a `with track_api_calls():` block. Increments a thread-local counter on
# each outbound HTTP call. Most platform SDKs (google-ads-python, snowflake,
# facebook-business, meta-business-sdk, hubspot-api-client, microsoft Bing
# ads, etc.) ultimately go through one of these libraries, so this is the
# cleanest single hook point.

_local = threading.local()


def _get_counter() -> int:
    return getattr(_local, "api_calls", 0)


def _bump(n: int = 1) -> None:
    _local.api_calls = getattr(_local, "api_calls", 0) + n


@contextmanager
def track_api_calls() -> Iterator[dict]:
    """
    Counts outbound HTTP calls inside the block.

    Usage:
        with track_api_calls() as counter:
            collect_meta_ads()
        # counter['count'] now holds the total HTTP calls made

    Patches httpx.Client.send and requests.Session.send while the block runs;
    restores both on exit. Safe to nest (each nested block sees only its own
    delta because we snapshot/diff the thread-local).
    """
    counter: dict = {"count": 0}
    start_count = _get_counter()

    # Patch httpx if present
    httpx_send_orig = None
    try:
        import httpx
        httpx_send_orig = httpx.Client.send

        def _httpx_send(self, request, *a, **kw):
            _bump()
            return httpx_send_orig(self, request, *a, **kw)
        httpx.Client.send = _httpx_send
    except Exception:
        httpx_send_orig = None

    # Patch requests if present
    requests_send_orig = None
    try:
        import requests
        requests_send_orig = requests.Session.send

        def _requests_send(self, request, **kw):
            _bump()
            return requests_send_orig(self, request, **kw)
        requests.Session.send = _requests_send
    except Exception:
        requests_send_orig = None

    try:
        yield counter
    finally:
        # Restore patches
        if httpx_send_orig is not None:
            try:
                import httpx
                httpx.Client.send = httpx_send_orig
            except Exception:
                pass
        if requests_send_orig is not None:
            try:
                import requests
                requests.Session.send = requests_send_orig
            except Exception:
                pass
        counter["count"] = _get_counter() - start_count


# ─── Anthropic response helper ───────────────────────────────────────────────
def extract_anthropic_usage(message) -> tuple[int, int]:
    """
    Pull (input_tokens, output_tokens) from an Anthropic Messages response.
    Returns (0, 0) if the shape isn't what we expected — never raises.
    """
    try:
        usage = getattr(message, "usage", None)
        if usage is None:
            return (0, 0)
        return (
            int(getattr(usage, "input_tokens", 0) or 0),
            int(getattr(usage, "output_tokens", 0) or 0),
        )
    except Exception:
        return (0, 0)


# ─── Anthropic call wrapper ──────────────────────────────────────────────────
def call_anthropic_tracked(client, *, log_role: str, log_action: str,
                            log_details: dict | None = None, **kwargs):
    """
    Drop-in replacement for `client.messages.create(**kwargs)` that:
      - times the call
      - extracts tokens_in/tokens_out from response.usage
      - computes USD cost
      - logs one row to agent_activity_log (role=log_role, action=log_action)
      - returns the original Anthropic message unchanged

    Usage:
        from executors.cost_tracking import call_anthropic_tracked
        msg = call_anthropic_tracked(
            client, log_role="llm_cadence", log_action="slack_listener_reply",
            model=CLAUDE_MODEL, max_tokens=1500,
            system=AGENT_SYSTEM, messages=[{"role": "user", "content": text}],
        )
    """
    import time as _t
    from logs.activity_logger import log_activity_async

    t0 = _t.time()
    msg = client.messages.create(**kwargs)
    duration_s = _t.time() - t0

    tokens_in, tokens_out = extract_anthropic_usage(msg)
    cost = llm_cost_usd(tokens_in, tokens_out)
    try:
        log_activity_async(
            role=log_role,
            action=log_action,
            status="success",
            details={"model": kwargs.get("model"), **(log_details or {})},
            duration_s=duration_s,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
        )
    except Exception:
        pass
    return msg


# ─── BQ bytes-scanned tracker ────────────────────────────────────────────────
# Same pattern as track_api_calls but for BigQuery. Monkey-patches
# bigquery.Client.query so every query inside the block accumulates
# total_bytes_processed into a thread-local counter. Zero changes needed at
# call sites — just wrap the outer loop.

def _bump_bq_bytes(n: int) -> None:
    _local.bq_bytes_scanned = getattr(_local, "bq_bytes_scanned", 0) + (n or 0)


def _get_bq_bytes() -> int:
    return getattr(_local, "bq_bytes_scanned", 0)


@contextmanager
def track_bq_bytes() -> Iterator[dict]:
    """
    Counts bytes scanned by BigQuery queries inside the block.

    Usage:
        with track_bq_bytes() as bq:
            run_audit()
            run_digest()
        # bq['bytes'] now holds total_bytes_processed across all queries

    Wraps `bigquery.Client.query` so every query's `total_bytes_processed`
    is added to a thread-local counter. Restored on exit. Safe to nest.
    """
    counter: dict = {"bytes": 0}
    start_bytes = _get_bq_bytes()

    query_orig = None
    try:
        from google.cloud import bigquery
        query_orig = bigquery.Client.query

        def _query_tracked(self, sql, *a, **kw):
            job = query_orig(self, sql, *a, **kw)

            # Hook the job's result() so bytes are counted only after the
            # query actually runs (BQ jobs are lazy until result() is called).
            result_orig = job.result

            def _result(*ra, **rkw):
                rows = result_orig(*ra, **rkw)
                try:
                    _bump_bq_bytes(int(getattr(job, "total_bytes_processed", 0) or 0))
                except Exception:
                    pass
                return rows
            job.result = _result
            return job

        bigquery.Client.query = _query_tracked
    except Exception:
        query_orig = None

    try:
        yield counter
    finally:
        if query_orig is not None:
            try:
                from google.cloud import bigquery
                bigquery.Client.query = query_orig
            except Exception:
                pass
        counter["bytes"] = _get_bq_bytes() - start_bytes


# ─── BQ query wrapper (per-call, opt-in) ─────────────────────────────────────
def run_query_tracked(client, sql: str, **kwargs):
    """
    Drop-in replacement for `client.query(sql).result()` that returns
    (rows_iter, bytes_scanned). Use anywhere we want to track BQ cost.

    Usage:
        from executors.cost_tracking import run_query_tracked
        rows, bytes_scanned = run_query_tracked(client, "SELECT * FROM ...")
        for row in rows:
            ...

    `bytes_scanned` is the total_bytes_processed from the finished job.
    """
    job = client.query(sql, **kwargs)
    rows = job.result()
    bytes_scanned = int(getattr(job, "total_bytes_processed", 0) or 0)
    return rows, bytes_scanned
