// Зеркало grey_cardinal_contracts/transcripts.py

export interface TranscriptEvent {
  type: "transcript";
  meeting_id: string | null;
  speaker_id: string | null;
  speaker_name: string | null;
  text: string;
  ts: string;
  is_final: boolean;
  raw?: Record<string, unknown>;
}
