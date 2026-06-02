import type { DesktopTask } from "../api/brainClient";

export function TaskList({ tasks }: { tasks: DesktopTask[] }) {
  return (
    <section className="panel">
      <h2>My Tasks</h2>
      {tasks.length === 0 ? (
        <div className="muted">No tasks loaded.</div>
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
