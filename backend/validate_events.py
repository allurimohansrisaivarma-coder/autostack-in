"""Validate exported synthetic events; schema checks are not an authorization decision."""
import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

CONTRACTS = Path(__file__).resolve().parents[1] / "shared" / "contracts"
FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=(ValueError, TypeError))
def date_time(value):
    # jsonschema's default date-time checker depends on an optional package. Validate explicitly
    # so a minimal install cannot silently skip time checks.
    if not isinstance(value, str):
        return True
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})", value):
        return False
    return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None


def validator(name):
    schema = json.loads((CONTRACTS / f"{name}.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FORMATS)


def validate_events(events):
    if not isinstance(events, list) or len(events) > 100:
        raise ValueError("Expected a bounded list of at most 100 synthetic events")
    event_validator = validator("event")
    seen = set()
    for event in events:
        event_validator.validate(event)
        if event["event_id"] in seen:
            raise ValueError("Duplicate event ID")
        seen.add(event["event_id"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    args = parser.parse_args()
    with args.events.open(encoding="utf-8") as stream:
        events = json.load(stream)
    validate_events(events)
    print(f"Validated {len(events)} synthetic events. No execution approval granted.")
