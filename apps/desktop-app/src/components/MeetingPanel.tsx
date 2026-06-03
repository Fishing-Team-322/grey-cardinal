import type { MeetingParticipant } from "../api/brainClient";

export function MeetingPanel({
  meetingId,
  onMeetingId,
  onJoin,
  onLeave,
  joined,
  participant
}: {
  meetingId: string;
  onMeetingId: (value: string) => void;
  onJoin: () => void;
  onLeave: () => void;
  joined: boolean;
  participant: MeetingParticipant | null;
}) {
  return (
    <section className="panel">
      <h2>Meeting</h2>
      <label>
        Meeting ID
        <input value={meetingId} onChange={(event) => onMeetingId(event.target.value)} />
      </label>
      <div className="button-row">
        <button onClick={onJoin}>{joined ? "Rejoin" : "Join"}</button>
        <button onClick={onLeave} disabled={!joined}>
          Leave
        </button>
      </div>
      <div className="muted">
        {participant ? `participant ${participant.status}` : joined ? "joined" : "not joined"}
      </div>
    </section>
  );
}
