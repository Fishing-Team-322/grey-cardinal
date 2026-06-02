import type { GamificationState } from "../api/brainClient";

export function GamificationPanel({ state }: { state: GamificationState | null }) {
  return (
    <section className="panel">
      <h2>Activity</h2>
      <div className="xp">
        <span>{state?.points_total ?? 0} XP</span>
        <strong>Level {state?.level ?? 1}</strong>
      </div>
      <ul className="compact-list">
        {(state?.recent_events ?? []).slice(0, 3).map((event, index) => (
          <li key={`${event.kind}-${index}`}>
            +{event.points} {event.reason}
          </li>
        ))}
      </ul>
    </section>
  );
}
