from log import get_log_from_id

def request_appeal(content_id: str) -> dict:
    logs = get_log_from_id(content_id)
    labeled_content = {}
    for l in logs:
        if l.get("status") == "under_review":
            return {
                "content_id": content_id,
                "status": "error",
                "message": "content is already appealed",
            }
        if l.get("status") == "labeled":
            labeled_content = l
    if (not logs) or (not labeled_content):
        return {
            "content_id": content_id,
            "status": "error",
            "message": "content_id not found",
        }
    return {
        "content_id": content_id,
        "status": "under_review",
        "message": "Your appeal was received and is under review.",
        "labeled_content": labeled_content,
    }