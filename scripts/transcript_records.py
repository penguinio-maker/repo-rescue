"""Structural rollout compatibility; no IO, scope decisions or extraction."""

RECORD_KINDS = {
    "session_meta": "boundary", "turn_context": "scope",
    "world_state": "metadata", "response_item": "content", "event_msg": "content",
}


def record_kind(record):
    if not isinstance(record, dict) or not isinstance(record.get("type"), str):
        return None, "unsafe_record_envelope"
    kind = RECORD_KINDS.get(record.get("type"))
    if kind is None:
        return None, "unsupported_record"
    if (not isinstance(record.get("payload"), dict)
            or set(record) - {"type", "timestamp", "ordinal", "payload", "metadata"}):
        return None, "unsafe_record_envelope"
    ordinal = record.get("ordinal")
    if ordinal is not None and (type(ordinal) is not int or not 0 <= ordinal < 2 ** 64):
        return None, "unsafe_record_envelope"
    if "metadata" in record and record["metadata"] is not None and not isinstance(record["metadata"], dict):
        return None, "unsafe_record_envelope"
    return kind, None


def world_state_structure(record):
    """WorldStateItem's state is an extensible map, not a section-name enum."""
    payload = record.get("payload")
    if (set(record) - {"type", "timestamp", "ordinal", "payload"}
            or not isinstance(payload, dict) or set(payload) != {"full", "state"}
            or type(payload["full"]) is not bool or not isinstance(payload["state"], dict)):
        return False
    stack, visited = [(payload["state"], 0)], 0
    while stack:
        value, depth = stack.pop()
        visited += 1
        if visited > 4096 or depth > 64:
            return False
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
    return True
