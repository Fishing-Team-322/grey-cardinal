// Зеркало grey_cardinal_contracts/tasks.py для frontend-dashboard.
// Держите в синхроне с Python-версией при изменении контрактов.

export type TaskStatus =
  | "proposed"
  | "confirmed"
  | "todo"
  | "in_progress"
  | "blocked"
  | "done"
  | "rejected"
  | "cancelled";

export type TaskPriority = "low" | "medium" | "high" | "critical";

export type TaskSource =
  | "telegram_chat"
  | "telegram_direct"
  | "meeting_transcript"
  | "manual";

export interface TaskDTO {
  id: string;
  public_id: string;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  assignee_text: string | null;
  deadline: string | null;
  source: TaskSource;
  board_provider: string | null;
  board_url: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface TaskListResponse {
  tasks: TaskDTO[];
}
