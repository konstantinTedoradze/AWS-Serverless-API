from unittest.mock import Mock, patch

import pytest

from lambda_code.retry_utils import retry_with_exponential_backoff


def test_returns_result_on_first_attempt():
    func = Mock(return_value="success")

    result = retry_with_exponential_backoff(func)

    assert result == "success"
    assert func.call_count == 1


def test_retries_then_succeeds():
    func = Mock(
        side_effect=[
            TimeoutError("Temporary failure"),
            TimeoutError("Temporary failure"),
            "success",
        ]
    )

    with patch("lambda_code.retry_utils.time.sleep"):
        result = retry_with_exponential_backoff(func)

    assert result == "success"
    assert func.call_count == 3


def test_raises_after_all_attempts_fail():
    func = Mock(side_effect=TimeoutError("Service unavailable"))

    with patch("lambda_code.retry_utils.time.sleep"):
        with pytest.raises(TimeoutError, match="Service unavailable"):
            retry_with_exponential_backoff(func, max_retries=2)

    assert func.call_count == 3


def test_rejects_negative_retries():
    with pytest.raises(ValueError):
        retry_with_exponential_backoff(lambda: "success", max_retries=-1)
