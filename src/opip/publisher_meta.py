"""Publisher metadata for signed bundles."""

import json

PUBLISHER_FILE = "publisher.json"


def make_publisher(name, key_id=None, contact=None, public_record=None):
    record = {
        "name": name,
    }
    if key_id:
        record["key_id"] = key_id
    if contact:
        record["contact"] = contact
    if public_record:
        record["trust"] = public_record
    return record


def dump_publisher(record):
    return json.dumps(record, indent=2, sort_keys=True) + "\n"


def load_publisher(data):
    if isinstance(data, str):
        return json.loads(data)
    return data
