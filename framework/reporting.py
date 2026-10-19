"""Standards-compliant JSON: represent positive infinity explicitly."""
import json
import math


def json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        if value == float("inf"):
            return "Infinity"
        raise ValueError("Unexpected non-finite value in backtest output.")
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def write_json(path, value):
    path.write_text(json.dumps(json_safe(value), indent=2, allow_nan=False), encoding="utf-8")
