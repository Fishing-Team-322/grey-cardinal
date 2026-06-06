"""
Grey Cardinal Tray Agent — самодостаточный Windows трей-агент.

Сидит в системном трее и:
  • при активной встрече (или по кнопке «Записать») пишет микрофон,
  • отправляет аудио на сервер → ASR (faster-whisper) → извлечение задач,
  • показывает статус иконкой в трее.

Ничего внешнего (C++ exe) не требует — запись делается прямо здесь (sounddevice).

Привязка: при первом запуске агент сам получает pairing-код и регистрируется
(self-pair) в воркспейсе по умолчанию. Можно перепривязать из меню трея.

Config: %LOCALAPPDATA%\\GreyCardinal\\Agent\\tray_config.toml
Logs:   %LOCALAPPDATA%\\GreyCardinal\\Agent\\tray_agent.log
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import socket
import sys
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.5.0"
SAMPLE_RATE = 16000

# ── Optional deps (graceful degradation) ─────────────────────────────────────
try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    print("Нет зависимостей. Установите: pip install pystray pillow")
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    import numpy as np
    import sounddevice as sd
    _AUDIO_OK = True
except Exception:  # noqa: BLE001
    _AUDIO_OK = False


# ── Paths / config ────────────────────────────────────────────────────────────

def _base_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))).expanduser()
    p = base / "GreyCardinal" / "Agent"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _config_path() -> Path:
    return _base_dir() / "tray_config.toml"


def _log_path() -> Path:
    return _base_dir() / "tray_agent.log"


@dataclass
class Config:
    server_url: str = "https://fishingteam.su"
    agent_token: str = ""
    workspace_id: str = ""
    chunk_sec: int = 25
    poll_interval: int = 5
    auto_record: bool = True
    log_level: str = "INFO"

    @classmethod
    def load(cls) -> "Config":
        path = _config_path()
        cfg = cls()
        if path.exists():
            try:
                try:
                    import tomllib  # py3.11+
                except ImportError:
                    import tomli as tomllib  # type: ignore
                data = tomllib.loads(path.read_text("utf-8"))
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
            except Exception:  # noqa: BLE001
                pass
        else:
            cfg.save()
        return cfg

    def save(self) -> None:
        _config_path().write_text(
            "# Grey Cardinal Tray Agent\n"
            f'server_url    = "{self.server_url}"\n'
            f'agent_token   = "{self.agent_token}"\n'
            f'workspace_id  = "{self.workspace_id}"\n'
            f"chunk_sec     = {self.chunk_sec}\n"
            f"poll_interval = {self.poll_interval}\n"
            f"auto_record   = {str(self.auto_record).lower()}\n"
            f'log_level     = "{self.log_level}"\n',
            encoding="utf-8",
        )


# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(_log_path(), encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


log = logging.getLogger("tray")


# ── Icons ─────────────────────────────────────────────────────────────────────

def _make_icon(color: str, size: int = 64) -> "Image.Image":
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, size - 2, size - 2], fill=color, outline="#222", width=2)
    cx, cy = size // 2, size // 2
    mw, mh = size // 5, size // 3
    d.rounded_rectangle([cx - mw, cy - mh, cx + mw, cy + mh // 3], radius=mw, fill="white")
    d.arc([cx - mw - 2, cy - mh // 3, cx + mw + 2, cy + mh // 2], start=180, end=0, fill="white", width=2)
    d.line([cx, cy + mh // 2, cx, cy + mh // 2 + 4], fill="white", width=2)
    return img


ICON_IDLE = _make_icon("#555555")
ICON_REC = _make_icon("#22c55e")
ICON_BUSY = _make_icon("#f59e0b")
ICON_ERR = _make_icon("#ef4444")


# ── Backend client ────────────────────────────────────────────────────────────

class Backend:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def _url(self, path: str) -> str:
        return self.cfg.server_url.rstrip("/") + path

    def pair(self, code: str | None = None) -> tuple[str, str]:
        """Self-pair (code=None) или привязка по коду из кабинета."""
        if requests is None:
            raise RuntimeError("requests не установлен")
        if not code:
            pc = requests.post(self._url("/api/agents/pairing-code"), json={}, timeout=20)
            pc.raise_for_status()
            code = pc.json()["pairing_code"]
        reg = requests.post(
            self._url("/api/agents/register"),
            json={"pairing_code": code, "device_name": socket.gethostname(),
                  "os": "windows", "daemon_version": VERSION},
            timeout=20,
        )
        reg.raise_for_status()
        data = reg.json()
        return data["agent_token"], data.get("workspace_id", "")

    def heartbeat(self, status: str) -> None:
        if requests is None or not self.cfg.agent_token:
            return
        with contextlib.suppress(Exception):
            requests.post(self._url("/api/agents/heartbeat"),
                          json={"status": status}, headers={"X-Agent-Token": self.cfg.agent_token}, timeout=10)

    def session_active(self) -> tuple[bool, str | None]:
        if requests is None:
            return False, None
        try:
            r = requests.get(self._url("/api/session/current"), timeout=6)
            d = r.json()
            return bool(d.get("active")), d.get("meeting_id")
        except Exception:  # noqa: BLE001
            return False, None

    def upload(self, wav_bytes: bytes, duration: int) -> dict:
        if requests is None or not self.cfg.agent_token:
            raise RuntimeError("агент не привязан")
        files = {"audio": ("chunk.wav", wav_bytes, "audio/wav")}
        data = {"recording_id": uuid.uuid4().hex, "duration_sec": str(duration),
                "source": "microphone", "transcript_text": ""}
        r = requests.post(self._url("/api/daemon/uploads"), files=files, data=data,
                          headers={"X-Agent-Token": self.cfg.agent_token}, timeout=180)
        r.raise_for_status()
        return r.json()

    def last_history(self) -> dict | None:
        if requests is None:
            return None
        with contextlib.suppress(Exception):
            r = requests.get(self._url("/api/daemon/hearing-history"),
                             params={"workspace_id": self.cfg.workspace_id, "limit": 1}, timeout=10)
            items = r.json().get("items", [])
            return items[0] if items else None
        return None


# ── Recorder ──────────────────────────────────────────────────────────────────

def record_wav(seconds: int) -> bytes:
    if not _AUDIO_OK:
        raise RuntimeError("запись недоступна (нет sounddevice/numpy или микрофона)")
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(audio.tobytes())
    return buf.getvalue()


# ── Tray app ──────────────────────────────────────────────────────────────────

class TrayApp:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.be = Backend(cfg)
        self._stop = threading.Event()
        self._rec_lock = threading.Lock()
        self._status = "Инициализация…"
        self._icon: "pystray.Icon | None" = None

    # ── recording ──
    def _record_and_upload(self, meeting_id: str | None = None) -> None:
        if not self._rec_lock.acquire(blocking=False):
            log.info("Уже идёт запись — пропуск")
            return
        try:
            if not self.cfg.agent_token:
                self._set(ICON_ERR, "Не привязан — нажмите «Перепривязать»")
                return
            self._set(ICON_REC, f"Запись {self.cfg.chunk_sec}с…")
            self.be.heartbeat("recording")
            wav = record_wav(self.cfg.chunk_sec)
            self._set(ICON_BUSY, "Отправка на сервер…")
            res = self.be.upload(wav, self.cfg.chunk_sec)
            self.be.heartbeat("idle")
            if res.get("proposal_created"):
                self._set(ICON_IDLE, "Задача найдена ✓")
                log.info("Загружено, задача создана: %s", res.get("proposal_id"))
            else:
                self._set(ICON_IDLE, "Загружено (задач нет)")
                log.info("Загружено, задач не найдено")
        except Exception as e:  # noqa: BLE001
            log.error("Запись/загрузка: %s", e)
            self._set(ICON_ERR, f"Ошибка: {str(e)[:40]}")
        finally:
            self._rec_lock.release()
            self._refresh_menu()

    def _record_now(self, icon=None, item=None) -> None:
        threading.Thread(target=self._record_and_upload, daemon=True).start()

    def _repair(self, icon=None, item=None) -> None:
        def _do():
            try:
                self._set(ICON_BUSY, "Привязка…")
                token, ws = self.be.pair()
                self.cfg.agent_token, self.cfg.workspace_id = token, ws
                self.cfg.save()
                self._set(ICON_IDLE, "Привязано ✓")
                log.info("Привязано к workspace %s", ws)
            except Exception as e:  # noqa: BLE001
                self._set(ICON_ERR, f"Привязка не удалась: {str(e)[:30]}")
                log.error("Привязка: %s", e)
            self._refresh_menu()
        threading.Thread(target=_do, daemon=True).start()

    def _show_last(self, icon=None, item=None) -> None:
        h = self.be.last_history()
        if h:
            self._set(self._icon.icon if self._icon else ICON_IDLE,
                      f"Последнее: {(h.get('prepared_task') or h.get('transcript_text') or '—')[:40]}")
            log.info("Последняя реплика: %s | задача: %s", h.get("transcript_text"), h.get("prepared_task"))
        else:
            self._set(ICON_IDLE, "История пуста")

    # ── tray plumbing ──
    def _set(self, icon_img, tooltip: str) -> None:
        self._status = tooltip
        if self._icon:
            self._icon.icon = icon_img
            self._icon.title = f"Grey Cardinal — {tooltip}"

    def _refresh_menu(self) -> None:
        if self._icon:
            with contextlib.suppress(Exception):
                self._icon.update_menu()

    def _menu(self) -> "pystray.Menu":
        paired = "да" if self.cfg.agent_token else "нет"
        return pystray.Menu(
            pystray.MenuItem(lambda i: self._status, None, enabled=False),
            pystray.MenuItem(f"Привязан: {paired}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⏺ Записать сейчас (тест)", self._record_now,
                             enabled=lambda i: _AUDIO_OK),
            pystray.MenuItem("🔗 Перепривязать", self._repair),
            pystray.MenuItem("📜 Последняя реплика", self._show_last),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Настройки (config)", lambda i, it: os.startfile(str(_config_path()))),
            pystray.MenuItem("Логи", lambda i, it: os.startfile(str(_log_path()))),
            pystray.MenuItem("Выход", self._quit),
        )

    def _quit(self, icon=None, item=None) -> None:
        self._stop.set()
        if self._icon:
            self._icon.stop()

    # ── background loop ──
    def _loop(self) -> None:
        # авто-привязка при первом запуске
        if not self.cfg.agent_token:
            self._repair()
        while not self._stop.is_set():
            self.be.heartbeat("idle")
            if self.cfg.auto_record and self.cfg.agent_token:
                active, mid = self.be.session_active()
                if active and not self._rec_lock.locked():
                    log.info("Активная встреча %s — запись", mid)
                    self._record_and_upload(mid)
                elif not active and not self._rec_lock.locked():
                    self._set(ICON_IDLE, "Нет активной встречи")
            self._refresh_menu()
            self._stop.wait(self.cfg.poll_interval)

    def run(self) -> None:
        setup_logging(self.cfg.log_level)
        log.info("Grey Cardinal Tray Agent v%s | server=%s | audio=%s",
                 VERSION, self.cfg.server_url, _AUDIO_OK)
        threading.Thread(target=self._loop, daemon=True, name="loop").start()
        self._icon = pystray.Icon("grey-cardinal", icon=ICON_BUSY,
                                  title="Grey Cardinal — запуск…", menu=self._menu())
        self._icon.run()


if __name__ == "__main__":
    TrayApp(Config.load()).run()
