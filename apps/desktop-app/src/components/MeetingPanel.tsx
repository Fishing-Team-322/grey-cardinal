export function MeetingPanel({
  meetingId,
  onMeetingId,
  onJoin,
  joined
}: {
  meetingId: string;
  onMeetingId: (value: string) => void;
  onJoin: () => void;
  joined: boolean;
}) {
  return (
    <section className="panel">
      <h2>Meeting</h2>
      <label>
        Meeting ID
        <input value={meetingId} onChange={(event) => onMeetingId(event.target.value)} />
      </label>
      <button onClick={onJoin}>{joined ? "Rejoin" : "Join"}</button>
    </section>
  );
}
