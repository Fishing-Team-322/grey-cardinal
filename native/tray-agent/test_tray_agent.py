from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path


def _load_agent():
    path = Path(__file__).with_name("tray_agent.py")
    spec = importlib.util.spec_from_file_location("grey_cardinal_tray_agent", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_manual_recording_continues_until_stop(monkeypatch):
    agent = _load_agent()
    config = agent.Config(agent_token="token", chunk_sec=25, capture_mode="mixed")
    app = agent.TrayApp(config)
    recorded = []
    uploaded = []

    def fake_record(seconds, capture_mode, stop_event):
        recorded.append((seconds, capture_mode))
        if len(recorded) == 3:
            stop_event.set()
        return b"wav", 25.0

    def fake_upload(wav, duration):
        uploaded.append((wav, duration))
        return {"transcript": "", "proposal_created": False}

    monkeypatch.setattr(agent, "record_wav", fake_record)
    monkeypatch.setattr(app.be, "upload", fake_upload)

    app._record_and_upload()

    assert len(recorded) == 3
    assert uploaded == [(b"wav", 25), (b"wav", 25), (b"wav", 25)]
    assert not app._rec_lock.locked()
    assert not app._record_stop.is_set()


def test_stop_recording_interrupts_active_session(monkeypatch):
    agent = _load_agent()
    config = agent.Config(agent_token="token", chunk_sec=25)
    app = agent.TrayApp(config)
    entered = threading.Event()

    def fake_record(seconds, capture_mode, stop_event):
        entered.set()
        stop_event.wait(2)
        raise RuntimeError("stopped before audio")

    monkeypatch.setattr(agent, "record_wav", fake_record)
    worker = threading.Thread(target=app._record_and_upload)
    worker.start()
    assert entered.wait(1)

    app._stop_recording()
    worker.join(2)

    assert not worker.is_alive()
    assert not app._rec_lock.locked()
