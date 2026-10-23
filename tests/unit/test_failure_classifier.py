import unittest

from lambda_code.failure_classifier import analyze_failure


class TestAnalyzeFailure(unittest.TestCase):

    def test_timeout_is_retryable(self):
        result = analyze_failure("Task timed out after 30 seconds")

        self.assertEqual(
            result,
            {
                "retryable": True,
                "reason": "timeout",
                "delay_seconds": 300,
            },
        )

    def test_rate_limit_is_retryable(self):
        result = analyze_failure("AWS rate limit exceeded")

        self.assertEqual(result["retryable"], True)
        self.assertEqual(result["reason"], "rate_limit")
        self.assertEqual(result["delay_seconds"], 600)

    def test_validation_error_is_not_retryable(self):
        result = analyze_failure("Product validation failed")

        self.assertEqual(result["retryable"], False)
        self.assertEqual(result["reason"], "validation_error")
        self.assertEqual(result["delay_seconds"], 0)

    def test_not_found_is_not_retryable(self):
        result = analyze_failure("Product not found")

        self.assertEqual(result["retryable"], False)
        self.assertEqual(result["reason"], "resource_not_found")

    def test_unknown_error_is_not_automatically_retryable(self):
        result = analyze_failure("Unexpected internal failure")

        self.assertEqual(result["retryable"], False)
        self.assertEqual(result["reason"], "unknown")
        self.assertEqual(result["delay_seconds"], 0)

    def test_empty_error_is_handled(self):
        result = analyze_failure(None)

        self.assertEqual(result["retryable"], False)
        self.assertEqual(result["reason"], "unknown")


if __name__ == "__main__":
    unittest.main()
