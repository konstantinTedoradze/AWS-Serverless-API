from unittest.mock import Mock, patch

from ec2_app.payment_service import process_payment


class TestPaymentService:

    @patch("ec2_app.payment_service.stripe.PaymentIntent.create")
    def test_process_payment_success(self, mock_stripe):

        # Arrange
        mock_stripe.return_value = Mock(
            id="pi_123",
            status="succeeded"
        )

        # Act
        result = process_payment(
            amount=1000,
            currency="usd",
            payment_method="pm_card_visa"
        )

        # Assert
        assert result["status"] == "success"
        assert result["transaction_id"] == "pi_123"

        mock_stripe.assert_called_once_with(
            amount=100000,
            currency="usd",
            payment_method="pm_card_visa",
            confirm=True
        )