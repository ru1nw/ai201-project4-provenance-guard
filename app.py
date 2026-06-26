import uuid

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from appeal import request_appeal
from log import get_log, log_event
from scoring import llm_scoring, stylo_scoring, confidence_scoring

app = Flask(__name__)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


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
    if llm_verdict["score"] < 0:
        log_event({
            "status": "error",
            "content_id": content_id,
            "attribution": "uncertain",
            "confidence": 0,
            "llm_score": llm_verdict["score"],
            "llm_reasoning": llm_verdict["reasoning"],
            "stylo_score": -1,
            "text": text,
            "creator_id": creator_id,
        })
        return jsonify({
            "content_id": content_id,
            "attribution": "uncertain",
            "confidence": 0,
            "label": llm_verdict["reasoning"],
        })
    
    stylo_score = stylo_scoring(text)
    scorings = confidence_scoring(llm_verdict["score"], stylo_score, content_id)

    log_event({
        "status": "labeled",
        "content_id": content_id,
        "attribution": scorings["attribution"],
        "confidence": scorings["confidence"],
        "llm_score": llm_verdict["score"],
        "llm_reasoning": llm_verdict["reasoning"],
        "stylo_score": stylo_score,
        "text": text,
        "creator_id": creator_id,
    })

    return jsonify({
        "content_id": content_id,
        "attribution": scorings["attribution"],
        "confidence": round(scorings["confidence"], 2),
        "label": scorings["label"],
    })


# curl -H "Content-Type: application/json" -d '{"content_id": "", "creator_reasoning": "test-reasoning"}' -v http://127.0.0.1:5000/appeal
@app.route("/appeal", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
def appeal():
    data = request.get_json()
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    appeal_result = request_appeal(content_id)
    if appeal_result["status"] == "under_review":
        log_event({
            "status": appeal_result["status"],
            "content_id": content_id,
            "creator_reasoning": creator_reasoning,
            "attribution": appeal_result["labeled_content"]["attribution"],
            "confidence": appeal_result["labeled_content"]["confidence"],
            "llm_score": appeal_result["labeled_content"]["llm_score"],
            "llm_reasoning": appeal_result["labeled_content"]["llm_reasoning"],
            "stylo_score": appeal_result["labeled_content"]["stylo_score"],
            "text": appeal_result["labeled_content"]["text"],
            "creator_id": appeal_result["labeled_content"]["creator_id"],
        })

    # Update the content's status and log the appeal (see section 6).
    return jsonify({
        "content_id": content_id,
        "creator_reasoning": creator_reasoning,
        "message": appeal_result["message"],
    })


# curl http://127.0.0.1:5000/log
@app.route("/log", methods=["GET"])
def view_log():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
