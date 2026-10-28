import random
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def retry_with_exponential_backoff(
    func: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 5.0,
) -> T:
    """
    Retry a function using exponential backoff and jitter.

    max_retries is the number of retries after the initial attempt.
    """
    if max_retries < 0:
        raise ValueError("max_retries cannot be negative")

    if base_delay < 0 or max_delay < 0:
        raise ValueError("Delay values cannot be negative")

    for attempt in range(max_retries + 1):
        try:
            return func()

        except Exception:
            if attempt == max_retries:
                raise

            exponential_delay = base_delay * (2 ** attempt)
            jitter = random.uniform(0, exponential_delay * 0.1)
            wait_time = min(exponential_delay + jitter, max_delay)

            print(
                f"Attempt {attempt + 1} failed. "
                f"Retrying in {wait_time:.2f} seconds."
            )
            time.sleep(wait_time)

    raise RuntimeError("Unexpected retry loop exit")
