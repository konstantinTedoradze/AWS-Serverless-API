
from unittest.mock import Mock, patch

from ec2_app.payment_service import process_payment
from ec2_app.shipping_service import calculate_shipping_rate


class TestPaymentIntegration:

    @patch(
        "ec2_app.payment_service.stripe.PaymentIntent.create"
    )
    def test_successful_payment(self, mock_stripe_payment):

        mock_stripe_payment.return_value = Mock(
            id="pi_123456",
            status="succeeded",
            amount=19999
        )

        result = process_payment(
            amount=199.99,
            currency="usd",
            payment_method="pm_card_visa"
        )

        assert result["status"] == "success"
        assert result["transaction_id"] == "pi_123456"

        mock_stripe_payment.assert_called_once_with(
            amount=19999,
            currency="usd",
            payment_method="pm_card_visa",
            confirm=True
        )


class TestShippingIntegration:

    @patch("ec2_app.shipping_service.requests.post")
    def test_calculate_shipping_rate(self, mock_post):

        mock_response = Mock()
        mock_response.status_code = 200

        mock_response.json.return_value = {
            "RateResponse": {
                "RatedShipment": {
                    "TotalCharges": {
                        "MonetaryValue": "12.50"
                    }
                }
            }
        }

        mock_post.return_value = mock_response

        result = calculate_shipping_rate(
            origin_zip="98101",
            destination_zip="10001",
            weight_lbs=2.5
        )

        assert result["rate"] == 12.50

        mock_post.assert_called_once()
