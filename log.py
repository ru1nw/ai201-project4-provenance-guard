from datetime import datetime, timezone
import json

LOG_PATH = "audit_log.jsonl"


def get_log(limit=3) -> list:
    try:
        with open(LOG_PATH) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    return [json.loads(line) for line in lines[-limit:]]

def get_log_from_id(id: str) -> list:
    try:
        with open(LOG_PATH) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    matched_logs = []
    for line in lines:
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry["content_id"] == id:
            matched_logs.append(entry)
    return matched_logs


def log_event(entry: dict) -> None:
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        print("Failed to write to audit log: %s", e)