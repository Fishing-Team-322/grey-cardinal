"""
Grey Cardinal Tray Agent — Windows system tray app.

Sits quietly in the tray and automatically starts/stops microphone recording
based on the active team session in Grey Cardinal.

Flow:
  Someone starts a meeting in Telegram bot (/meeting_start)
      → agent detects active session
      → starts recording in loops until meeting ends
      → each chunk uploaded → ASR → task extraction

Config: config.toml (auto-created on first run)
Logs:   %LOCALAPPDATA%\GreyCardinal\Agent\tray_agent.log
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("Missing deps. Run: pip install pystray pillow")
    sys.exit(1)

# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class Config:
    server_url: str = "https://fishingteam.su"
    agent_exe: str = r"C:\Program Files\Grey Cardinal Agent\grey-cardinal-agent.exe"
    chunk_sec: int = 30        # seconds per recording chunk (agent restarts automatically)
    poll_interval: int = 5     # seconds between session polls
    capture_mode: str = "microphone"
    internal_token: str = ""   # not needed for public /api/session/current
    log_level: str = "INFO"

    @classmethod
    def load(cls) -> Config:
        cfg_path = _config_path()
        if not cfg_path.exists():
            cfg = cls()
            cfg.save()
            return cfg
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            try:
                import tomli as tomllib  # pip install tomli
            except ImportError:
                return cls()
        try:
            data = tomllib.loads(cfg_path.read_text("utf-8"))
            cfg = cls()
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
            return cfg
        except Exception:
            return cls()

    def save(self) -> None:
        path = _config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f'# Grey Cardinal Tray Agent config\n'
            f'server_url   = "{self.server_url}"\n'
            f'agent_exe    = "{self.agent_exe.replace(chr(92), chr(92)*2)}"\n'
            f'chunk_sec    = {self.chunk_sec}\n'
            f'poll_interval = {self.poll_interval}\n'
            f'capture_mode = "{self.capture_mode}"\n'
            f'internal_token = "{self.internal_token}"\n'
            f'log_level    = "{self.log_level}"\n',
            encoding="utf-8",
        )


def _config_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", "~")).expanduser()
    return base / "GreyCardinal" / "Agent" / "tray_config.toml"


def _log_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", "~")).expanduser()
    p = base / "GreyCardinal" / "Agent" / "tray_agent.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(_log_path(), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

log = logging.getLogger("tray")

# ── Icons (generated programmatically — no PNG files needed) ─────────────────

def _make_icon(color: str, size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Outer circle
    draw.ellipse([2, 2, size - 2, size - 2], fill=color, outline="#333333", width=2)
    # Microphone body
    cx, cy = size // 2, size // 2
    mic_w, mic_h = size // 5, size // 3
    draw.rounded_rectangle(
        [cx - mic_w, cy - mic_h, cx + mic_w, cy + mic_h // 3],
        radius=mic_w, fill="white",
    )
    # Mic stand
    draw.arc([cx - mic_w - 2, cy - mic_h // 3, cx + mic_w + 2, cy + mic_h // 2],
             start=180, end=0, fill="white", width=2)
    draw.line([cx, cy + mic_h // 2, cx, cy + mic_h // 2 + 4], fill="white", width=2)
    return img


ICON_IDLE      = _make_icon("#555555")   # grey = no meeting
ICON_ACTIVE    = _make_icon("#22c55e")   # green = recording
ICON_STARTING  = _make_icon("#f59e0b")   # amber = connecting
ICON_ERROR     = _make_icon("#ef4444")   # red = error


# ── Session polling ───────────────────────────────────────────────────────────

@dataclass
class SessionState:
    active: bool = False
    meeting_id: str | None = None
    transcript_count: int = 0
    error: str | None = None
    last_checked: datetime = field(default_factory=datetime.now)


def fetch_session(server_url: str, _token: str = "") -> SessionState:
    url = f"{server_url.rstrip('/')}/api/session/current"
    req = urllib.request.Request(url)
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        data: dict[str, Any] = json.loads(resp.read())
        return SessionState(
            active=bool(data.get("active")),
            meeting_id=data.get("meeting_id"),
            transcript_count=data.get("transcript_count", 0),
        )
    except urllib.error.URLError as e:
        return SessionState(error=str(e.reason)[:60])
    except Exception as e:
        return SessionState(error=str(e)[:60])


# ── Agent runner ──────────────────────────────────────────────────────────────

class AgentRunner:
    """Manages grey-cardinal-agent.exe subprocesses."""

    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start_chunk(self, meeting_id: str) -> bool:
        """Start one recording chunk. Returns False if exe not found."""
        exe = Path(self._cfg.agent_exe)
        if not exe.exists():
            # Try alongside this script
            local_exe = Path(__file__).parent / "grey-cardinal-agent.exe"
            if local_exe.exists():
                exe = local_exe
            else:
                log.error("Agent exe not found: %s", exe)
                return False

        with self._lock:
            if self._proc and self._proc.poll() is None:
                return True  # already running

            cmd = [
                str(exe),
                "--backend", self._cfg.server_url,
                "--meeting-id", meeting_id,
                "--duration-sec", str(self._cfg.chunk_sec),
                "--capture-mode", self._cfg.capture_mode,
            ]
            log.info(
                "Starting agent chunk: meeting=%s duration=%ds",
                meeting_id,
                self._cfg.chunk_sec,
            )
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        return True

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                log.info("Stopping agent process")
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                self._proc = None

    def wait_for_completion(self) -> None:
        with self._lock:
            proc = self._proc
        if proc:
            proc.wait()


# ── Tray application ──────────────────────────────────────────────────────────

class TrayApp:
    def __init__(self, cfg: Config) -> None:
        self._cfg = cfg
        self._session = SessionState()
        self._runner = AgentRunner(cfg)
        self._stop_event = threading.Event()
        self._status_text = "Инициализация..."
        self._icon: pystray.Icon | None = None

    # ── Menu ─────────────────────────────────────────────────────────────────

    def _make_menu(self) -> pystray.Menu:
        s = self._session
        if s.error:
            status = f"Ошибка: {s.error[:40]}"
        elif s.active:
            status = f"🔴 Идёт встреча: {s.meeting_id} ({s.transcript_count} реплик)"
        else:
            status = "⚪ Нет активной встречи"

        return pystray.Menu(
            pystray.MenuItem(status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Настройки (config.toml)",
                self._open_config,
            ),
            pystray.MenuItem("Логи", self._open_log),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", self._quit),
        )

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _open_config(self, icon, item) -> None:
        os.startfile(str(_config_path()))

    def _open_log(self, icon, item) -> None:
        os.startfile(str(_log_path()))

    def _quit(self, icon, item) -> None:
        log.info("Quitting tray agent")
        self._stop_event.set()
        self._runner.stop()
        icon.stop()

    # ── Poll loop ─────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        """Background thread: polls session, manages recording."""
        log.info("Poll loop started (server=%s)", self._cfg.server_url)

        while not self._stop_event.is_set():
            prev_active = self._session.active
            self._session = fetch_session(self._cfg.server_url, self._cfg.internal_token)

            meeting_id = self._session.meeting_id

            if self._session.error:
                self._update_icon(ICON_ERROR, "Ошибка подключения")
            elif self._session.active and meeting_id:
                # Session is active
                if not self._runner.is_running:
                    if not prev_active:
                        log.info("Meeting started: %s", meeting_id)
                    # Start a new recording chunk
                    ok = self._runner.start_chunk(meeting_id)
                    if not ok:
                        self._update_icon(ICON_ERROR, "Агент не найден!")
                    else:
                        self._update_icon(ICON_ACTIVE, f"Запись: {meeting_id}")
                else:
                    self._update_icon(ICON_ACTIVE, f"Запись: {meeting_id}")
            else:
                # No active session
                if prev_active:
                    log.info("Meeting ended, stopping recording")
                    self._runner.stop()
                if self._runner.is_running:
                    self._runner.stop()
                self._update_icon(ICON_IDLE, "Нет активной встречи")

            # Update menu
            if self._icon:
                with contextlib.suppress(Exception):
                    self._icon.update_menu()

            # If recording is done (chunk completed) but session still active → restart
            if self._session.active and not self._runner.is_running and meeting_id:
                log.debug("Chunk completed, waiting before next...")
                time.sleep(1)
                if self._session.active:
                    self._runner.start_chunk(meeting_id)

            self._stop_event.wait(timeout=self._cfg.poll_interval)

        log.info("Poll loop stopped")

    def _update_icon(self, icon_img: Image.Image, tooltip: str) -> None:
        if self._icon:
            self._icon.icon = icon_img
            self._icon.title = f"Grey Cardinal — {tooltip}"

    # ── Run ──────────────────────────────────────────────────────────────────

    def run(self) -> None:
        setup_logging(self._cfg.log_level)
        log.info("Grey Cardinal Tray Agent starting")
        log.info("Config: %s", _config_path())
        log.info("Server: %s", self._cfg.server_url)
        log.info("Agent exe: %s", self._cfg.agent_exe)

        poll_thread = threading.Thread(target=self._poll_loop, daemon=True, name="poll")
        poll_thread.start()

        self._icon = pystray.Icon(
            "grey-cardinal",
            icon=ICON_STARTING,
            title="Grey Cardinal — Подключение...",
            menu=pystray.Menu(
                pystray.MenuItem("Grey Cardinal Agent", None, enabled=False),
                pystray.MenuItem("Выход", self._quit),
            ),
        )
        self._icon.run()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cfg = Config.load()
    TrayApp(cfg).run()
