"""Standalone artifact downloader

Usage:
    python3 path/to/download_artifact.py <dest_hash> <group> <repo> <tag> <artifact> [page_node_hash] <output_path>

"""
from __future__ import annotations

import os
import sys
import threading

import RNS


def main() -> None:
    if len(sys.argv) not in (7, 8):
        print("ERROR: Invalid arguments", file=sys.stderr)
        sys.exit(1)

    dest_hash = bytes.fromhex(sys.argv[1])
    group = sys.argv[2]
    repo = sys.argv[3]
    tag = sys.argv[4]
    artifact = sys.argv[5]
    page_hash = bytes.fromhex(sys.argv[6]) if len(sys.argv) >= 7 and sys.argv[6] else dest_hash
    out_path = sys.argv[-1]

    RNS.Reticulum()
    identity = RNS.Identity.recall(page_hash)
    if not identity:
        print("ERROR: Could not recall identity", file=sys.stderr)
        sys.exit(1)

    dest = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "nomadnetwork", "node")

    if not RNS.Transport.await_path(page_hash, timeout=15):
        print("ERROR: Could not resolve path", file=sys.stderr)
        sys.exit(1)

    link_ready = threading.Event()
    resp_ready = threading.Event()
    response_data: bytes | None = None

    def established(link: RNS.Link) -> None:
        ipath = os.path.expanduser("~/.rngit/client_identity")
        if os.path.isfile(ipath):
            link.identify(RNS.Identity.from_file(ipath))
        link_ready.set()

    def closed(link: RNS.Link) -> None:
        pass

    def on_progress(inst: object) -> None:
        pass

    def got_response(receipt: RNS.RequestReceipt) -> None:
        nonlocal response_data
        resp = receipt.response
        if hasattr(resp, "read") and hasattr(resp, "name"):
            response_data = resp.read()
        elif isinstance(resp, list) and len(resp) >= 2:
            response_data = resp[1] if isinstance(resp[1], bytes) else resp[1].read()
        else:
            response_data = resp
        resp_ready.set()

    def failed(receipt: RNS.RequestReceipt) -> None:
        resp_ready.set()

    link = RNS.Link(dest, established_callback=established, closed_callback=closed)
    if not link_ready.wait(timeout=15):
        link.teardown()
        print("ERROR: Link timed out", file=sys.stderr)
        sys.exit(1)

    try:
        receipt = link.request(
            "/file/artifact",
            data={"var_g": group, "var_r": repo, "var_t": tag, "var_a": artifact},
            response_callback=got_response,
            failed_callback=failed,
            progress_callback=on_progress,
        )

        if not receipt:
            print("ERROR: Request failed", file=sys.stderr)
            sys.exit(1)

        if not resp_ready.wait(timeout=60):
            print("ERROR: Request timed out", file=sys.stderr)
            sys.exit(1)

        if response_data is None:
            print("ERROR: No response", file=sys.stderr)
            sys.exit(1)

        with open(out_path, "wb") as f:
            f.write(response_data)

        size = os.path.getsize(out_path)
        print(f"OK {size}")

    finally:
        link.teardown()


if __name__ == "__main__":
    main()
