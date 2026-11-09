
import requests


def calculate_shipping_rate(
    origin_zip,
    destination_zip,
    weight_lbs
):
    response = requests.post(
        "https://api.example.com/shipping/rates",
        json={
            "origin_zip": origin_zip,
            "destination_zip": destination_zip,
            "weight_lbs": weight_lbs
        },
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    rate = data["RateResponse"]["RatedShipment"][
        "TotalCharges"
    ]["MonetaryValue"]

    return {
        "rate": float(rate)
    }
