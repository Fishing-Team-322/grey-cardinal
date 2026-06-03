import type { DesktopProposal, DesktopTask } from "../api/brainClient";

export function TaskList({
  tasks,
  proposals,
  onConfirm,
  onReject
}: {
  tasks: DesktopTask[];
  proposals: DesktopProposal[];
  onConfirm: (proposalId: string) => void;
  onReject: (proposalId: string) => void;
}) {
  return (
    <section className="panel">
      {proposals.length > 0 && (
        <>
          <h2>Pending Proposals ({proposals.length})</h2>
          <ul className="task-list" style={{ marginBottom: "12px" }}>
            {proposals.map((proposal) => (
              <li key={proposal.proposal_id} style={{ display: "block", padding: "6px 0", borderBottom: "1px solid #eee" }}>
                <div>
                  <strong>{proposal.title}</strong>
                  {proposal.assignee_text && (
                    <span className="muted" style={{ marginLeft: "8px", fontSize: "0.85em" }}>
                      {proposal.assignee_text}
                    </span>
                  )}
                </div>
                <div className="muted" style={{ fontSize: "0.82em", marginBottom: "4px" }}>{proposal.raw_text}</div>
                <button onClick={() => onConfirm(proposal.proposal_id)} style={{ marginRight: "6px", fontSize: "0.82em" }}>
                  Confirm
                </button>
                <button onClick={() => onReject(proposal.proposal_id)} style={{ fontSize: "0.82em" }}>
                  Reject
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      <h2>My Tasks ({tasks.length})</h2>
      {tasks.length === 0 ? (
        <div className="muted">No confirmed tasks yet.</div>
      ) : (
        <ul className="task-list">
          {tasks.map((task) => (
            <li key={task.id}>
              <span>{task.public_id}</span>
              <strong>{task.title}</strong>
              <small>{task.status}</small>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
