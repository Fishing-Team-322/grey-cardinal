"""
Grey Cardinal Tray Agent — самодостаточный Windows трей-агент.

Сидит в системном трее и:
  • при активной встрече (или по кнопке «Записать») пишет микрофон,
  • отправляет аудио на сервер → ASR (faster-whisper) → извлечение задач,
  • показывает статус иконкой в трее.

Ничего внешнего (C++ exe) не требует — запись делается прямо здесь (sounddevice).

Привязка: пользователь получает pairing-код на сайте и вводит его через меню
трея. Агент сохраняет выданный токен и поддерживает online-статус heartbeat'ами.

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
import wave
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.6.2"
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
    import numpy as _numpy  # noqa: F401
    import sounddevice as sd
    _AUDIO_OK = True
except Exception:  # noqa: BLE001
    _AUDIO_OK = False

try:
    import soundcard as sc
    _LOOPBACK_OK = sys.platform == "win32"
except Exception:  # noqa: BLE001
    sc = None  # type: ignore
    _LOOPBACK_OK = False


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
    capture_mode: str = "mixed"
    log_level: str = "INFO"

    @classmethod
    def load(cls) -> Config:
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
            f'capture_mode  = "{self.capture_mode}"\n'
            f'log_level     = "{self.log_level}"\n',
            encoding="utf-8",
        )


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


# ── Icons ─────────────────────────────────────────────────────────────────────

def _make_icon(color: str, size: int = 64) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, size - 2, size - 2], fill=color, outline="#222", width=2)
    cx, cy = size // 2, size // 2
    mw, mh = size // 5, size // 3
    d.rounded_rectangle([cx - mw, cy - mh, cx + mw, cy + mh // 3], radius=mw, fill="white")
    d.arc(
        [cx - mw - 2, cy - mh // 3, cx + mw + 2, cy + mh // 2],
        start=180,
        end=0,
        fill="white",
        width=2,
    )
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

    def daemon_state(self) -> tuple[bool, str | None]:
        """Tenant-scoped: запись только когда у команды реально идёт/скоро созвон."""
        if requests is None or not self.cfg.agent_token:
            return False, None
        try:
            r = requests.get(self._url("/api/daemon/state"),
                             headers={"X-Agent-Token": self.cfg.agent_token}, timeout=6)
            d = r.json()
            return d.get("state") == "recording", d.get("meeting_public_id")
        except Exception:  # noqa: BLE001
            return False, None

    def pair(self, pairing_code: str) -> dict:
        if requests is None:
            raise RuntimeError("HTTP-клиент недоступен")
        r = requests.post(
            self._url("/api/agents/register"),
            json={
                "pairing_code": pairing_code.strip().upper(),
                "device_name": socket.gethostname() or "PC Agent",
                "platform": "windows" if sys.platform == "win32" else sys.platform,
                "daemon_version": VERSION,
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def heartbeat(self, status: str) -> None:
        if requests is None or not self.cfg.agent_token:
            return
        r = requests.post(
            self._url("/api/agents/heartbeat"),
            json={
                "status": status,
                "version": VERSION,
                "device_name": socket.gethostname() or "PC Agent",
            },
            headers={"X-Agent-Token": self.cfg.agent_token},
            timeout=8,
        )
        r.raise_for_status()

    def upload(self, wav_bytes: bytes, duration: int) -> dict:
        """Аудио -> ASR -> v2-задача команды (proposal уходит в Telegram-чат команды)."""
        if requests is None or not self.cfg.agent_token:
            raise RuntimeError("нет токена агента")
        files = {"audio": ("chunk.wav", wav_bytes, "audio/wav")}
        data = {"duration_sec": str(duration), "transcript_text": ""}
        r = requests.post(self._url("/api/daemon/v2/uploads"), files=files, data=data,
                          headers={"X-Agent-Token": self.cfg.agent_token}, timeout=180)
        r.raise_for_status()
        return r.json()


# ── Recorder ──────────────────────────────────────────────────────────────────

def record_wav(seconds: int, capture_mode: str = "mixed") -> bytes:
    if not _AUDIO_OK:
        raise RuntimeError("запись недоступна (нет sounddevice/numpy или микрофона)")
    frames = int(seconds * SAMPLE_RATE)
    microphone = None
    if capture_mode == "mixed":
        try:
            microphone = sd.rec(frames, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        except Exception as exc:  # noqa: BLE001
            log.warning("Микрофон недоступен, продолжаю только с системным звуком: %s", exc)

    loopback = None
    if capture_mode in {"mixed", "system_loopback"} and _LOOPBACK_OK and sc is not None:
        try:
            speaker = sc.default_speaker()
            source = sc.get_microphone(speaker.id, include_loopback=True)
            with source.recorder(samplerate=SAMPLE_RATE, channels=1) as recorder:
                samples = recorder.record(numframes=frames)
            loopback = (_numpy.clip(samples, -1.0, 1.0) * 32767).astype("int16")
        except Exception as exc:  # noqa: BLE001
            log.warning("System loopback недоступен, переключаюсь на микрофон: %s", exc)

    if microphone is not None:
        sd.wait()
    if loopback is not None and microphone is not None:
        audio = _numpy.clip(
            loopback.astype("int32") + microphone.astype("int32"), -32768, 32767
        ).astype("int16")
    elif loopback is not None:
        audio = loopback
    elif microphone is not None:
        audio = microphone
    else:
        audio = sd.rec(frames, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
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
        self._icon: pystray.Icon | None = None

    # ── recording ──
    def _record_and_upload(self, meeting_id: str | None = None) -> None:
        if not self._rec_lock.acquire(blocking=False):
            log.info("Уже идёт запись — пропуск")
            return
        try:
            if not self.cfg.agent_token:
                self._set(ICON_ERR, "Нет токена — вставьте в config")
                return
            self._set(ICON_REC, f"Запись {self.cfg.chunk_sec}с…")
            wav = record_wav(self.cfg.chunk_sec, self.cfg.capture_mode)
            self._set(ICON_BUSY, "Распознавание на сервере…")
            res = self.be.upload(wav, self.cfg.chunk_sec)
            transcript = (res.get("transcript") or "").strip()
            if res.get("proposal_created"):
                self._set(ICON_IDLE, f"Задача: {(res.get('title') or '')[:28]} ✓")
                log.info("Распознано: %s | задача в чат команды: %s", transcript, res.get("title"))
            elif transcript:
                self._set(ICON_IDLE, "Распознано, задач нет")
                log.info("Распознано: %s | задач не найдено", transcript)
            else:
                self._set(ICON_IDLE, "Тишина / не распознано")
        except Exception as e:  # noqa: BLE001
            log.error("Запись/загрузка: %s", e)
            self._set(ICON_ERR, f"Ошибка: {str(e)[:40]}")
        finally:
            self._rec_lock.release()
            self._refresh_menu()

    def _record_now(self, icon=None, item=None) -> None:
        threading.Thread(target=self._record_and_upload, daemon=True).start()

    def _reload_token(self, icon=None, item=None) -> None:
        self.cfg.agent_token = Config.load().agent_token
        if self.cfg.agent_token:
            self._set(ICON_IDLE, "Токен загружен ✓")
            log.info("Токен агента загружен из config")
        else:
            self._set(ICON_ERR, "Токен пуст — вставьте в config")
        self._refresh_menu()

    def _pair(self, icon=None, item=None) -> None:
        root = None
        try:
            import tkinter as tk
            from tkinter import messagebox, simpledialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            code = simpledialog.askstring(
                "Grey Cardinal",
                "Вставьте код привязки с сайта (GC-XXXXXX):",
                parent=root,
            )
            if not code:
                return
            result = self.be.pair(code)
            self.cfg.agent_token = result["agent_token"]
            self.cfg.save()
            self.be.heartbeat("idle")
            self._set(ICON_IDLE, "Агент привязан и онлайн")
            messagebox.showinfo(
                "Grey Cardinal",
                "Агент успешно привязан. Он будет работать в системном трее.",
                parent=root,
            )
            log.info("Агент привязан: agent_id=%s", result.get("agent_id"))
        except Exception as e:  # noqa: BLE001
            log.error("Привязка агента: %s", e)
            self._set(ICON_ERR, f"Ошибка привязки: {str(e)[:32]}")
            with contextlib.suppress(Exception):
                messagebox.showerror("Grey Cardinal", f"Не удалось привязать агент:\n{e}")
        finally:
            if root is not None:
                with contextlib.suppress(Exception):
                    root.destroy()
            self._refresh_menu()

    def _open_config(self, icon=None, item=None) -> None:
        with contextlib.suppress(Exception):
            os.startfile(str(_config_path()))

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

    def _menu(self) -> pystray.Menu:
        paired = "да" if self.cfg.agent_token else "нет"
        return pystray.Menu(
            pystray.MenuItem(lambda i: self._status, None, enabled=False),
            pystray.MenuItem(f"Привязан: {paired}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Привязать по коду", self._pair),
            pystray.MenuItem("⏺ Записать сейчас (тест)", self._record_now,
                             enabled=lambda i: _AUDIO_OK),
            pystray.MenuItem("Настройки", self._open_config),
            pystray.MenuItem("Перечитать настройки", self._reload_token),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Логи", lambda i, it: os.startfile(str(_log_path()))),
            pystray.MenuItem("Выход", self._quit),
        )

    def _quit(self, icon=None, item=None) -> None:
        self._stop.set()
        if self._icon:
            self._icon.stop()

    # ── background loop ──
    def _loop(self) -> None:
        while not self._stop.is_set():
            # подхватываем токен, если его вставили в config «на лету»
            if not self.cfg.agent_token:
                self.cfg.agent_token = Config.load().agent_token
            if not self.cfg.agent_token:
                self._set(ICON_ERR, "Не привязан — откройте меню трея")
            else:
                try:
                    self.be.heartbeat("recording" if self._rec_lock.locked() else "idle")
                except Exception as e:  # noqa: BLE001
                    log.warning("Heartbeat: %s", e)
            if self.cfg.agent_token and self.cfg.auto_record:
                active, mid = self.be.daemon_state()
                if active and not self._rec_lock.locked():
                    log.info("Идёт созвон %s — запись", mid)
                    self._record_and_upload(mid)
                elif not active and not self._rec_lock.locked():
                    self._set(ICON_IDLE, "Нет активного созвона")
            self._refresh_menu()
            self._stop.wait(self.cfg.poll_interval)

    def run(self) -> None:
        setup_logging(self.cfg.log_level)
        log.info(
            "Grey Cardinal Tray Agent v%s | server=%s | audio=%s | capture=%s",
            VERSION,
            self.cfg.server_url,
            _AUDIO_OK,
            self.cfg.capture_mode,
        )
        threading.Thread(target=self._loop, daemon=True, name="loop").start()
        self._icon = pystray.Icon("grey-cardinal", icon=ICON_BUSY,
                                  title="Grey Cardinal — запуск…", menu=self._menu())
        self._icon.run()


if __name__ == "__main__":
    TrayApp(Config.load()).run()
