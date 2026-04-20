import time
from notifications.slack import check_approval


def wait_for_approval(message_ts: str, timeout_minutes: int = 60) -> str:
    """
    Poll Slack every 30 seconds for an approval reaction.
    Times out after timeout_minutes - returns 'timeout' if no response.
    """
    max_checks = (timeout_minutes * 60) // 30
    checks = 0

    while checks < max_checks:
        status = check_approval(message_ts)
        if status in ("approved", "rejected"):
            return status
        time.sleep(30)
        checks += 1

    return "timeout"
