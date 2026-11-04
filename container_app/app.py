from flask import Flask, jsonify
import os

app = Flask(__name__)


@app.route("/health")
def health_check():
    return jsonify({"status": "healthy"})


@app.route("/")
def index():
    return "Container deployment successful"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
