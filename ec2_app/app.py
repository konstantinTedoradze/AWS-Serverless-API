
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify({"status": "healthy"})

@app.route("/api/products")
def get_products():
    return jsonify([
        {
            "id": 1,
            "title": "Widget",
            "price": 9.99
        },
        {
            "id": 2,
            "title": "Gadget",
            "price": 19.99
        }
    ])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
