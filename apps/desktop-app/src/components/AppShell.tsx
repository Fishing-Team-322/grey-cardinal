import type { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">Grey Cardinal</div>
        <div className="muted">Desktop microphone client</div>
      </aside>
      <section className="workspace">{children}</section>
    </main>
  );
}
