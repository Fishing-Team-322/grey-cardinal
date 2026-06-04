#!/usr/bin/env python3
"""Grey Cardinal daemon simulator.

Runs the exact pairing → heartbeat → record → upload flow the Windows tray
daemon performs, so the account/workspace ownership chain can be verified end to
end without a Windows build. Stdlib only.

    python scripts/daemon_sim.py --base-url https://fishingteam.su \
        --pairing-code GC-123456 \
        --transcript "Максим, сделай сайт до пятницы"

Get the pairing code from the cockpit ("Сгенерировать код привязки").
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid


def _req(url: str, *, data: bytes | None, headers: dict, method: str) -> dict:
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"HTTP {exc.code} from {url}: {exc.read().decode('utf-8', 'replace')}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Cannot reach {url}: {exc}") from exc


def _post_json(url: str, body: dict, headers: dict | None = None) -> dict:
    h = {"Content-Type": "application/json", **(headers or {})}
    return _req(url, data=json.dumps(body).encode("utf-8"), headers=h, method="POST")


def _multipart(
    fields: dict[str, str], file_field: str, filename: str, content: bytes
) -> tuple[bytes, str]:
    boundary = "----gcsim" + uuid.uuid4().hex
    parts: list[bytes] = []
    for name, value in fields.items():
        head = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
        parts.append(f"{head}{value}\r\n".encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
    )
    parts.append(content)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), boundary


def main() -> int:
    p = argparse.ArgumentParser(description="Grey Cardinal daemon simulator")
    p.add_argument("--base-url", default=os.getenv("GC_BASE_URL", "https://fishingteam.su"))
    p.add_argument("--pairing-code", required=True)
    p.add_argument("--device-name", default="Sim laptop")
    p.add_argument("--transcript", default="Максим, сделай сайт до пятницы")
    args = p.parse_args()
    base = args.base_url.rstrip("/")

    print(f"[1/4] Register with pairing code {args.pairing_code} ...")
    reg = _post_json(
        f"{base}/api/agents/register",
        {
            "pairing_code": args.pairing_code,
            "device_name": args.device_name,
            "os": "windows",
            "daemon_version": "0.4.0",
        },
    )
    token = reg["agent_token"]
    auth = {"X-Agent-Token": token}
    print(f"      agent_id={reg['agent_id']} workspace_id={reg['workspace_id']}")
    print(f"      backend={reg.get('backend_url')}")

    print("[2/4] Heartbeat (recording) ...")
    _post_json(f"{base}/api/agents/heartbeat", {"status": "recording", "version": "0.4.0"}, auth)

    print("[3/4] Upload recording (+ transcript) ...")
    wav = b"RIFF" + b"\x00" * 64  # tiny placeholder WAV
    body, boundary = _multipart(
        {
            "recording_id": "rec-" + uuid.uuid4().hex[:6],
            "duration_sec": "12",
            "source": "microphone",
            "transcript_text": args.transcript,
        },
        "audio",
        "recording.wav",
        wav,
    )
    up = _req(
        f"{base}/api/daemon/uploads",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", **auth},
        method="POST",
    )
    print(f"      upload_id={up['upload_id']} workspace_id={up['workspace_id']}")
    print(f"      proposal_created={up['proposal_created']} proposal_id={up.get('proposal_id')}")

    print("[4/4] Heartbeat (idle) ...")
    _post_json(f"{base}/api/agents/heartbeat", {"status": "idle", "version": "0.4.0"}, auth)

    print("\nDone. In the cockpit (Daemon) you should now see this device online and the upload;")
    print("the transcript created a task proposal visible in Задачи / Канбан.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
