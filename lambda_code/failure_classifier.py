"""Classify failures found while investigating Lambda DLQ messages."""


def analyze_failure(error_message):
    """Classify an error and return a retry recommendation."""

    message = str(error_message or "").lower()

    if "timeout" in message or "timed out" in message:
        return {
            "retryable": True,
            "reason": "timeout",
            "delay_seconds": 300,
        }

    if any(term in message for term in (
        "rate limit",
        "throttl",
        "too many requests",
    )):
        return {
            "retryable": True,
            "reason": "rate_limit",
            "delay_seconds": 600,
        }

    if any(term in message for term in (
        "validation",
        "invalid input",
        "validationerror",
    )):
        return {
            "retryable": False,
            "reason": "validation_error",
            "delay_seconds": 0,
        }

    if any(term in message for term in (
        "not found",
        "resource_not_found",
        "resourcenotfound",
    )):
        return {
            "retryable": False,
            "reason": "resource_not_found",
            "delay_seconds": 0,
        }

    return {
        "retryable": False,
        "reason": "unknown",
        "delay_seconds": 0,
    }
