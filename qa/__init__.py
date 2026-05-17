"""QA Gate — locked verification layer.

Mandatory pre-delivery checks that block outbound results when underlying
numbers, freshness, or attribution don't reconcile. Wired into:
  - notifications/slack.py    (every post)
  - executors/asana.py        (every task)
  - collectors/bq_writer.py   (every upsert)
  - reports/app.py            (freshness banner color)

Usage:
    from qa.gate import gate
    gate.verify_slack(text, channel)   # raises QAGateError on hard fail
    gate.verify_asana(task_dict)
    gate.verify_bq_write(table, rows, key_fields)
    status = gate.dashboard_status()   # returns 'green'|'yellow'|'red'

Disable for tests with env: QA_GATE_DISABLED=1
"""
from .errors import QAGateError, QACheckResult
from .gate import gate

__all__ = ["gate", "QAGateError", "QACheckResult"]
