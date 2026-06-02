from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from grey_cardinal_contracts import (
    CaptureMode,
    DesktopClientIdentity,
    DesktopGamificationStateResponse,
    RegisterDeviceRequest,
    RegisterDeviceResponse,
    SpeakerIdentitySource,
    TranscriptEvent,
    TranscriptSourceKind,
    TranscriptSpeaker,
)


def test_desktop_client_identity_validation() -> None:
    identity = DesktopClientIdentity(
        user_id="user_petya",
        device_id="device_petya_laptop",
        client_session_id="session_abc",
        workspace_id="workspace_1",
        display_name="Петя",
        platform="windows",
        app_version="0.1.0",
    )

    assert identity.platform == "windows"
    assert identity.display_name == "Петя"


def test_transcript_event_v2_requires_authenticated_speaker_for_desktop_app() -> None:
    event = TranscriptEvent(
        meeting_id="MTG-1",
        workspace_id="workspace_1",
        source={
            "kind": "desktop_app",
            "user_id": "user_petya",
            "device_id": "device_petya_laptop",
            "client_session_id": "session_abc",
            "microphone_id": "default_input",
            "capture_mode": "microphone",
            "platform": "windows",
            "app_version": "0.1.0",
        },
        speaker=TranscriptSpeaker(
            resolved_user_id="user_petya",
            resolved_name="Петя",
            identity_source=SpeakerIdentitySource.authenticated_client,
            identity_confidence=1.0,
        ),
        text="Я подготовлю оплату до завтра 18:00",
        ts=datetime.now(UTC),
        audio={"source": "microphone", "duration_ms": 3200},
        asr={"provider": "mock", "confidence": 0.91},
    )

    assert event.source.kind == TranscriptSourceKind.desktop_app
    assert event.source.capture_mode == CaptureMode.microphone
    assert event.speaker.identity_confidence == 1.0


def test_transcript_event_v2_rejects_voice_guess_as_desktop_identity() -> None:
    with pytest.raises(ValidationError):
        TranscriptEvent(
            meeting_id="MTG-1",
            source={
                "kind": "desktop_app",
                "user_id": "user_petya",
                "device_id": "device_petya_laptop",
                "client_session_id": "session_abc",
            },
            speaker={
                "resolved_user_id": "user_petya",
                "resolved_name": "Петя",
                "identity_source": "unknown",
                "identity_confidence": 0.5,
            },
            text="Петя говорит",
            ts=datetime.now(UTC),
        )


def test_register_device_contracts() -> None:
    request = RegisterDeviceRequest(
        display_name="Петя",
        telegram_username="petya",
        device_name="Petya Laptop",
        platform="windows",
    )
    response = RegisterDeviceResponse(
        user_id="user-id",
        device_id="device-id",
        client_session_id="session-id",
        display_name=request.display_name,
    )

    assert response.display_name == "Петя"


def test_gamification_response_contract() -> None:
    response = DesktopGamificationStateResponse(
        user_id="user-id",
        points_total=120,
        level=2,
        recent_events=[
            {"kind": "task_completed", "points": 20, "reason": "Закрыл задачу GC-1"}
        ],
    )

    assert response.level == 2
    assert response.recent_events[0].points == 20
