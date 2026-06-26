from datetime import datetime, timezone
import json
import uuid

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from scoring import llm_scoring, stylo_scoring, confidence_and_label

LOG_PATH = "audit_log.jsonl"

app = Flask(__name__)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


def log_event(entry: dict) -> None:
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        app.logger.error("Failed to write to audit log: %s", e)


def get_log(limit=3):
    try:
        with open(LOG_PATH) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines[-limit:]]


@app.route("/")
def home():
    return "<p>Provenance Guard is running.</p>"


# curl -H "Content-Type: application/json" -d '{"text": "", "creator_id": "test-user-1"}' -v http://127.0.0.1:5000/submit
@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def submit():
    data = request.get_json()
    text = data.get("text")
    creator_id = data.get("creator_id")
    content_id = str(uuid.uuid4())

    llm_verdict = llm_scoring(text)
    stylo_score = stylo_scoring(text)
    signals = confidence_and_label(llm_verdict["score"], stylo_score)

    log_event({
        "content_id": content_id,
        "creator_id": creator_id,
        "text": text,
        "attribution": signals["attribution"],
        "confidence": signals["confidence"],
        "llm_score": llm_verdict["score"],
        "stylo_score": stylo_score,
        "status": "labeled",
    })

    return jsonify({
        "content_id": content_id,
        "attribution": signals["attribution"],
        "confidence": round(signals["confidence"], 2),
        "label": "We're not sure who wrote this.",
    })


@app.route("/appeal", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def appeal():
    data = request.get_json()
    content_id = data.get("content_id")
    reasoning = data.get("creator_reasoning")

    # Update the content's status and log the appeal (see section 6).
    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Your appeal was received and is under review.",
    })


# curl http://127.0.0.1:5000/log
@app.route("/log", methods=["GET"])
def view_log():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
