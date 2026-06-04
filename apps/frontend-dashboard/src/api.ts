/**
 * API client for Grey Cardinal backend.
 *
 * Base URL is read from VITE_API_BASE_URL env var. When unset (production
 * behind the reverse proxy) it defaults to the empty string, so all requests
 * are same-origin (e.g. `/api/health`) and routed to brain-api by Caddy. This
 * avoids CORS and mixed-content issues. For local `vite dev` against a backend
 * on another host, set VITE_API_BASE_URL=http://localhost:8000.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

// ---------------------------------------------------------------------------
// Response types
// ---------------------------------------------------------------------------

export interface HealthResponse {
  ok: boolean;
  service: string;
  status: string;
}

export interface MeetingSummary {
  meeting_id: string;
  status: MeetingStatus;
  source: string;
  created_at: string;
  audio_count: number;
  tasks_count: number;
}

export interface AudioRecord {
  audio_id: string;
  filename: string;
  status: string;
  created_at: string;
  started_at?: string;
  ended_at?: string;
}

export interface MeetingDetail {
  meeting_id: string;
  status: MeetingStatus;
  source: string;
  created_at: string;
  audios: AudioRecord[];
  tasks: Task[];
}

export interface Task {
  task_id: string;
  title: string;
  assignee?: string;
  deadline?: string;
  status: string;
}

export type MeetingStatus =
  | "created"
  | "recording"
  | "uploaded"
  | "processing"
  | "processed"
  | "error";

export type BotSessionStatus =
  | "created"
  | "joining"
  | "joined"
  | "recording"
  | "uploading"
  | "uploaded"
  | "left"
  | "error";

export interface TelemostJoinResponse {
  ok: boolean;
  meeting_id: string;
  bot_session_id: string;
  status: BotSessionStatus;
  message: string;
}

export interface TelemostStatusResponse {
  ok: boolean;
  bot_session_id: string;
  meeting_id: string;
  status: BotSessionStatus;
}

export interface TelemostLeaveResponse {
  ok: boolean;
  bot_session_id: string;
  meeting_id: string;
  status: BotSessionStatus;
  message: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/** GET /api/health */
export async function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/api/health");
}

/** GET /api/meetings */
export async function getMeetings(): Promise<MeetingSummary[]> {
  const data = await apiFetch<{ ok: boolean; meetings: MeetingSummary[] }>(
    "/api/meetings"
  );
  return data.meetings;
}

/** GET /api/meetings/{meetingId} */
export async function getMeeting(meetingId: string): Promise<MeetingDetail> {
  const data = await apiFetch<{ ok: boolean; meeting: MeetingDetail }>(
    `/api/meetings/${meetingId}`
  );
  return data.meeting;
}

/** GET /api/meetings/{meetingId}/status */
export async function getMeetingStatus(
  meetingId: string
): Promise<{ meeting_id: string; status: MeetingStatus }> {
  const data = await apiFetch<{
    ok: boolean;
    meeting_id: string;
    status: MeetingStatus;
  }>(`/api/meetings/${meetingId}/status`);
  return { meeting_id: data.meeting_id, status: data.status };
}

/** GET /api/meetings/{meetingId}/tasks */
export async function getMeetingTasks(meetingId: string): Promise<Task[]> {
  const data = await apiFetch<{ ok: boolean; meeting_id: string; tasks: Task[] }>(
    `/api/meetings/${meetingId}/tasks`
  );
  return data.tasks;
}

/** POST /api/telemost/join */
export async function joinTelemost(
  meetingUrl: string,
  meetingId?: string
): Promise<TelemostJoinResponse> {
  return apiFetch<TelemostJoinResponse>("/api/telemost/join", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ meeting_url: meetingUrl, meeting_id: meetingId ?? "" }),
  });
}

/** POST /api/telemost/{botSessionId}/leave */
export async function leaveTelemost(
  botSessionId: string
): Promise<TelemostLeaveResponse> {
  return apiFetch<TelemostLeaveResponse>(`/api/telemost/${botSessionId}/leave`, {
    method: "POST",
  });
}

/** GET /api/telemost/{botSessionId}/status */
export async function getTelemostStatus(
  botSessionId: string
): Promise<TelemostStatusResponse> {
  return apiFetch<TelemostStatusResponse>(`/api/telemost/${botSessionId}/status`);
}
