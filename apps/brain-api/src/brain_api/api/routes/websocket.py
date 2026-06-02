"""WebSocket endpoint для dashboard: GET /ws/events.

На P0 поток односторонний (brain-api -> dashboard). Входящие сообщения от клиента
игнорируются, но нужны, чтобы держать соединение и ловить разрыв.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from brain_api.container import Container

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/events")
async def events(websocket: WebSocket) -> None:
    container: Container = websocket.app.state.container
    manager = container.websocket_manager
    await manager.connect(websocket)
    try:
        # Приветственное событие, чтобы клиент сразу видел живой канал.
        await websocket.send_json({"event": "connected", "payload": {"service": "brain-api"}})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
