"""Publisher metadata for signed bundles."""

import json

PUBLISHER_FILE = "publisher.json"


def make_publisher(name, identity=None, contact=None, public_record=None):
    record = {
        "name": name,
    }
    if identity:
        record["identity"] = identity
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
