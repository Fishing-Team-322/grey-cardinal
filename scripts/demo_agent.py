#!/usr/bin/env python3
"""Grey Cardinal demo agent / ingestion simulator.

Simulates what the native desktop agent does over the public API:
registers a device, then posts a (final) transcript line. The backend extracts
a task proposal, emits live WebSocket events (transcript_line, task_proposed,
and — when DESKTOP_AUTO_CONFIRM_PROPOSALS=true — task_created) which appear in
the dashboard "Live events" panel in real time.

Stdlib only, runs anywhere with Python 3:

    python scripts/demo_agent.py \
        --base-url https://fishingteam.su \
        --token "$INTERNAL_API_TOKEN" \
        --text "Петя, подготовь оплату к четвергу"

The token must equal INTERNAL_API_TOKEN configured on the server.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import random
import urllib.error
import urllib.request


def _post(url: str, body: dict, headers: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SystemExit(f"HTTP {exc.code} from {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach {url}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Grey Cardinal demo ingestion agent")
    parser.add_argument("--base-url", default=os.getenv("GC_BASE_URL", "https://fishingteam.su"))
    parser.add_argument("--token", default=os.getenv("GC_INTERNAL_TOKEN", os.getenv("INTERNAL_API_TOKEN", "")))
    parser.add_argument("--text", default="Петя, подготовь оплату к четвергу")
    # The desktop meeting flow expects a public id of the form "MTG-<number>".
    parser.add_argument("--meeting-id", default=f"MTG-{random.randint(100000, 999999)}")
    parser.add_argument("--display-name", default="Demo Agent")
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("Missing internal token. Pass --token or set GC_INTERNAL_TOKEN.")

    base = args.base_url.rstrip("/")
    auth = {"X-Internal-Token": args.token}

    print(f"[1/2] Registering device at {base}/desktop/devices/register ...")
    reg = _post(
        f"{base}/desktop/devices/register",
        {"display_name": args.display_name, "device_name": "demo-agent", "platform": "linux"},
        auth,
    )
    print(f"      user_id={reg['user_id']} device_id={reg['device_id']} session={reg['client_session_id']}")

    identity = {
        **auth,
        "X-GC-User-Id": reg["user_id"],
        "X-GC-Device-Id": reg["device_id"],
        "X-GC-Client-Session-Id": reg["client_session_id"],
    }

    print(f'[2/2] Posting transcript to meeting "{args.meeting_id}": {args.text!r}')
    res = _post(
        f"{base}/desktop/transcripts",
        {"meeting_id": args.meeting_id, "text": args.text, "is_final": True, "capture_mode": "microphone"},
        identity,
    )
    print(f"      transcript_id={res.get('transcript_id')} proposal_created={res.get('proposal_created')}")
    print()
    print("Done. Open the dashboard and watch the 'Live events' panel.")
    print(f"  GET proposals: curl -H 'X-Internal-Token: <token>' -H 'X-GC-User-Id: {reg['user_id']}' \\")
    print(f"    -H 'X-GC-Device-Id: {reg['device_id']}' -H 'X-GC-Client-Session-Id: {reg['client_session_id']}' \\")
    print(f"    {base}/desktop/tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
