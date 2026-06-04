"""Account / workspace / agent (daemon) identity store — demo-ready, no DB.

JSON-persisted, autonomous (same pattern as demo.store.BrainStore). Provides:
  - a default demo workspace with a human-friendly account number (GC-XXXXXX),
  - one-time, time-limited pairing codes,
  - agents (daemons) bound to a workspace via an agent_token,
  - heartbeats + upload records, all scoped to a workspace.

Security: agent tokens are stored only as a SHA-256 hash (the plaintext token is
returned once at registration and lives on the device). Pairing codes are
one-time and expire (default 15 minutes). No INTERNAL_API_TOKEN is involved.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PAIRING_TTL_MINUTES = 15
# An agent is "online" if its last heartbeat is within this window.
ONLINE_WINDOW_SECONDS = 90
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous chars


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_iso() -> str:
    return _iso(_now())


def _gen_account_number() -> str:
    return "GC-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))


def _gen_pairing_code() -> str:
    return "GC-" + "".join(secrets.choice("0123456789") for _ in range(6))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AgentsStore:
    """Workspaces, pairing codes, agents and daemon uploads (JSON-backed)."""

    def __init__(self, base_dir: Path, file_name: str = "agents.json") -> None:
        self.base_dir = Path(base_dir)
        self._path = self.base_dir / file_name
        self._lock = threading.RLock()
        self._workspaces: dict[str, dict[str, Any]] = {}
        self._pairing: dict[str, dict[str, Any]] = {}
        self._agents: dict[str, dict[str, Any]] = {}
        self._token_index: dict[str, str] = {}  # token_hash -> agent_id
        self._uploads: list[dict[str, Any]] = []
        self._load()

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return
        self._workspaces = data.get("workspaces", {})
        self._pairing = data.get("pairing", {})
        self._agents = data.get("agents", {})
        self._uploads = data.get("uploads", [])
        self._token_index = {
            a["agent_token_hash"]: aid
            for aid, a in self._agents.items()
            if a.get("agent_token_hash")
        }

    def _save(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "workspaces": self._workspaces,
                "pairing": self._pairing,
                "agents": self._agents,
                "uploads": self._uploads,
            },
            ensure_ascii=False,
            indent=2,
        )
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)

    # ------------------------------------------------------------------ #
    # Workspaces / profile
    # ------------------------------------------------------------------ #
    def default_workspace(self) -> dict[str, Any]:
        with self._lock:
            for ws in self._workspaces.values():
                if ws.get("is_default"):
                    return ws
            ws = {
                "workspace_id": "ws_" + uuid.uuid4().hex[:12],
                "account_id": "acc_" + uuid.uuid4().hex[:12],
                "account_number": _gen_account_number(),
                "display_name": "Demo Workspace",
                "is_default": True,
                "created_at": _now_iso(),
            }
            self._workspaces[ws["workspace_id"]] = ws
            self._save()
            return ws

    def get_workspace(self, workspace_id: str | None) -> dict[str, Any]:
        with self._lock:
            if workspace_id and workspace_id in self._workspaces:
                return self._workspaces[workspace_id]
            return self.default_workspace()

    def profile(self, workspace_id: str | None, base_url: str) -> dict[str, Any]:
        ws = self.get_workspace(workspace_id)
        base = base_url.rstrip("/")
        return {
            "account_id": ws["account_id"],
            "workspace_id": ws["workspace_id"],
            "account_number": ws["account_number"],
            "display_name": ws["display_name"],
            "daemon_setup_url": f"{base}/#/app?workspace={ws['workspace_id']}",
            "download_url": "/downloads/grey-cardinal-daemon-windows-x64.msi",
        }

    # ------------------------------------------------------------------ #
    # Pairing codes
    # ------------------------------------------------------------------ #
    def create_pairing_code(self, workspace_id: str | None) -> dict[str, Any]:
        with self._lock:
            ws = self.get_workspace(workspace_id)
            code = _gen_pairing_code()
            expires = _now() + timedelta(minutes=PAIRING_TTL_MINUTES)
            self._pairing[code] = {
                "pairing_code": code,
                "workspace_id": ws["workspace_id"],
                "expires_at": _iso(expires),
                "used": False,
                "created_at": _now_iso(),
            }
            self._save()
            return {
                "pairing_code": code,
                "workspace_id": ws["workspace_id"],
                "expires_at": _iso(expires),
                "expires_in_minutes": PAIRING_TTL_MINUTES,
                "download_url": "/downloads/grey-cardinal-daemon-windows-x64.msi",
            }

    def _consume_pairing_code(self, code: str) -> dict[str, Any]:
        entry = self._pairing.get(code)
        if entry is None:
            raise ValueError("invalid pairing code")
        if entry.get("used"):
            raise ValueError("pairing code already used")
        if (
            datetime.strptime(entry["expires_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            < _now()
        ):
            raise ValueError("pairing code expired")
        entry["used"] = True
        entry["used_at"] = _now_iso()
        return entry

    # ------------------------------------------------------------------ #
    # Agents
    # ------------------------------------------------------------------ #
    def register_agent(
        self, pairing_code: str, device_name: str, os_name: str, daemon_version: str
    ) -> dict[str, Any]:
        with self._lock:
            entry = self._consume_pairing_code(pairing_code)
            workspace_id = entry["workspace_id"]
            agent_id = "agent_" + uuid.uuid4().hex[:12]
            token = "gca_" + secrets.token_urlsafe(32)
            agent = {
                "agent_id": agent_id,
                "workspace_id": workspace_id,
                "agent_token_hash": _hash_token(token),
                "device_name": device_name or "Unknown device",
                "os": os_name or "windows",
                "version": daemon_version or "",
                "status": "idle",
                "recording_status": "idle",
                "created_at": _now_iso(),
                "last_seen_at": _now_iso(),
                "last_upload_at": "",
            }
            self._agents[agent_id] = agent
            self._token_index[agent["agent_token_hash"]] = agent_id
            self._save()
            return {
                "agent_id": agent_id,
                "workspace_id": workspace_id,
                "agent_token": token,
                "display_name": agent["device_name"],
            }

    def agent_by_token(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        with self._lock:
            agent_id = self._token_index.get(_hash_token(token))
            return self._agents.get(agent_id) if agent_id else None

    def _is_online(self, agent: dict[str, Any]) -> bool:
        last = agent.get("last_seen_at")
        if not last:
            return False
        try:
            seen = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except ValueError:
            return False
        return (_now() - seen).total_seconds() <= ONLINE_WINDOW_SECONDS

    def _agent_view(self, agent: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent_id": agent["agent_id"],
            "workspace_id": agent["workspace_id"],
            "device_name": agent["device_name"],
            "os": agent["os"],
            "version": agent["version"],
            "status": agent["status"],
            "recording_status": agent.get("recording_status", "idle"),
            "online": self._is_online(agent),
            "last_seen_at": agent.get("last_seen_at", ""),
            "last_upload_at": agent.get("last_upload_at", ""),
            "created_at": agent["created_at"],
        }

    def list_agents(self, workspace_id: str | None) -> list[dict[str, Any]]:
        with self._lock:
            ws = self.get_workspace(workspace_id)
            rows = [
                self._agent_view(a)
                for a in self._agents.values()
                if a["workspace_id"] == ws["workspace_id"]
            ]
            rows.sort(key=lambda r: r["created_at"], reverse=True)
            return rows

    def heartbeat(
        self,
        agent: dict[str, Any],
        status: str,
        version: str | None,
        device_name: str | None,
    ) -> dict[str, Any]:
        with self._lock:
            agent["status"] = status or agent.get("status", "idle")
            agent["recording_status"] = "recording" if status == "recording" else "idle"
            if version:
                agent["version"] = version
            if device_name:
                agent["device_name"] = device_name
            agent["last_seen_at"] = _now_iso()
            self._save()
            return self._agent_view(agent)

    def unpair(self, workspace_id: str | None, agent_id: str) -> bool:
        with self._lock:
            agent = self._agents.get(agent_id)
            ws = self.get_workspace(workspace_id)
            if agent is None or agent["workspace_id"] != ws["workspace_id"]:
                return False
            self._token_index.pop(agent.get("agent_token_hash", ""), None)
            self._agents.pop(agent_id, None)
            self._save()
            return True

    # ------------------------------------------------------------------ #
    # Uploads
    # ------------------------------------------------------------------ #
    def record_upload(self, agent: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            upload = {
                "upload_id": "upl_" + uuid.uuid4().hex[:12],
                "agent_id": agent["agent_id"],
                "workspace_id": agent["workspace_id"],
                "device_name": agent["device_name"],
                "recording_id": fields.get("recording_id", ""),
                "source": fields.get("source", "microphone"),
                "started_at": fields.get("started_at", ""),
                "stopped_at": fields.get("stopped_at", ""),
                "duration_sec": fields.get("duration_sec", 0),
                "filename": fields.get("filename", ""),
                "size_bytes": fields.get("size_bytes", 0),
                "transcript_text": fields.get("transcript_text", ""),
                "proposal_id": fields.get("proposal_id", ""),
                "created_at": _now_iso(),
            }
            self._uploads.append(upload)
            agent["last_upload_at"] = upload["created_at"]
            agent["status"] = "idle"
            agent["recording_status"] = "idle"
            self._save()
            return upload

    def list_uploads(self, workspace_id: str | None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            ws = self.get_workspace(workspace_id)
            rows = [u for u in self._uploads if u["workspace_id"] == ws["workspace_id"]]
            rows.sort(key=lambda u: u["created_at"], reverse=True)
            return rows[:limit]


_store: AgentsStore | None = None


def get_agents_store() -> AgentsStore:
    global _store
    if _store is None:
        base = Path(os.getenv("UPLOADS_DIR", "/tmp/gc-uploads")) / "agents"
        _store = AgentsStore(base)
    return _store


def set_agents_store(store: AgentsStore) -> None:
    """Override the store — used in tests."""
    global _store
    _store = store
