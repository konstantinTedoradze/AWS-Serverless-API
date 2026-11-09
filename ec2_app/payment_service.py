
import stripe


def process_payment(amount, currency, payment_method):
    # Stripe expects amounts in the smallest currency unit.
    # For USD, $199.99 = 19999 cents.
    amount_in_cents = round(amount * 100)

    payment = stripe.PaymentIntent.create(
        amount=amount_in_cents,
        currency=currency,
        payment_method=payment_method,
        confirm=True
    )

    if payment.status == "succeeded":
        return {
            "status": "success",
            "transaction_id": payment.id
        }

    return {
        "status": "failed",
        "transaction_id": payment.id
    }
