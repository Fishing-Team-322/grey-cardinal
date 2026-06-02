// Зеркало grey_cardinal_contracts/events.py

export type EventName =
  | "task_proposed"
  | "task_created"
  | "task_rejected"
  | "task_status_changed"
  | "reminder_sent"
  | "transcript_line";

export interface WebsocketEvent<T = Record<string, unknown>> {
  event: EventName;
  payload: T;
}
