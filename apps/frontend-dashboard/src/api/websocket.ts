// Websocket-клиент к brain-api (GET /ws/events).
//
// Канонические типы событий — в packages/contracts/typescript/src/events.ts.
// Здесь продублирован минимум, чтобы каркас собирался автономно (без сборки
// кросс-пакета на P0).

export type EventName =
  | "connected"
  | "task_proposed"
  | "task_created"
  | "task_rejected"
  | "task_status_changed"
  | "reminder_sent"
  | "transcript_line";

export interface WebsocketEvent {
  event: EventName;
  payload: Record<string, unknown>;
}

export type EventHandler = (event: WebsocketEvent) => void;

export function connectEvents(url: string, onEvent: EventHandler): () => void {
  let socket: WebSocket | null = null;
  let closedByClient = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    socket = new WebSocket(url);

    socket.onmessage = (raw) => {
      try {
        onEvent(JSON.parse(raw.data) as WebsocketEvent);
      } catch (err) {
        console.error("Не удалось распарсить событие", err);
      }
    };

    socket.onclose = () => {
      if (closedByClient) return;
      // Простой авто-reconnect через 3 секунды.
      reconnectTimer = setTimeout(open, 3000);
    };

    socket.onerror = () => socket?.close();
  };

  open();

  // Возвращаем функцию отписки.
  return () => {
    closedByClient = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
  };
}
