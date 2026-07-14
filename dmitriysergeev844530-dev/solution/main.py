from __future__ import annotations

import os

from flask import Flask, jsonify, request


app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/configure")
def configure():
    payload = request.get_json(force=True)
    adapters = payload["adapters"]

    # TODO: save adapters in memory and return exactly {"status": "ok"}.
    return jsonify({
        "status": "todo",
        "message": f"TODO: store {len(adapters)} adapter(s)",
    })


@app.post("/route")
def route():
    payload = request.get_json(force=True)
    src = payload["from"]
    dst = payload["to"]
    message = payload["message"]

    # TODO: find the best route from src to dst for message.
    return jsonify({
        "status": "todo",
        "message": f"TODO: route from {src} to {dst} with {len(message)} field(s)",
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
