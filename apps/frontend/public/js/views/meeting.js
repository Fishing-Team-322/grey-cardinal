import { api } from "../api.js";
import { wsOn } from "../ws.js";
import { errorMessage, escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

export default async function meetingView(root, params) {
  const content = root.querySelector("#meeting-content");
  let meeting;
  try {
    meeting = await api.meetings.get(params.id);
  } catch (error) {
    content.innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    return;
  }
  setTopbar(meeting.title);
  const liveLines = [...(meeting.transcript_lines || [])];
  render(content, meeting, liveLines);
  bindActions(content, meeting);

  const update = async (payload) => {
    if (payload?.meeting_id !== meeting.id && payload?.meeting_public_id !== meeting.public_id) return;
    meeting = await api.meetings.get(meeting.id);
    render(content, meeting, liveLines);
    bindActions(content, meeting);
  };
  const transcript = (payload) => {
    if (payload?.meeting_id !== meeting.id && payload?.meeting_public_id !== meeting.public_id) return;
    liveLines.push(payload);
    content.querySelector("#transcript-lines")?.insertAdjacentHTML("beforeend", lineHtml(payload));
  };
  const unsubs = [
    wsOn("meeting_armed", update),
    wsOn("meeting_recording_started", update),
    wsOn("meeting_finished", update),
    wsOn("transcript_line", transcript),
  ];
  return () => unsubs.forEach((unsubscribe) => unsubscribe());
}

function render(content, meeting, liveLines = []) {
  const isManager = window.gcCurrentUser.teams?.some((team) => team.id === meeting.team_id && team.role === "manager");
  content.innerHTML = `
    <div class="page-head flex between center wrap gap-16"><div><div class="eyebrow">${escapeHtml(meeting.public_id)}</div><div class="page-title mt-8">${escapeHtml(meeting.title)}</div><p class="page-desc">${formatDate(meeting.scheduled_at)} · ${meeting.duration_minutes} мин</p></div><span class="pill ${meeting.state === "finished" ? "ok" : "info"}"><span class="dot ${meeting.state === "recording" ? "live" : ""}"></span>${escapeHtml(meeting.state)}</span></div>
    <div class="grid g2">
      <div class="card card-pad"><div class="card-head"><div class="card-title">Участие</div></div>
        <div class="flex gap-8 wrap"><button class="btn btn-sm btn-ghost rsvp" data-status="yes">Буду</button><button class="btn btn-sm btn-ghost rsvp" data-status="maybe">Возможно</button><button class="btn btn-sm btn-ghost rsvp" data-status="no">Не буду</button></div>
        ${isManager && meeting.state === "proposed" ? '<button class="btn btn-primary mt-16" id="confirm-meeting">Подтвердить встречу</button>' : ""}
        ${isManager && !["cancelled", "finished"].includes(meeting.state) ? '<button class="btn btn-ghost mt-16" id="cancel-meeting">Отменить</button>' : ""}
      </div>
      <div class="card card-pad"><div class="card-head"><div class="card-title">Итоги</div></div>
        ${meeting.summary ? `<p>${escapeHtml(meeting.summary)}</p>` : '<div class="dim">Саммари появится после завершения обработки.</div>'}
        ${(meeting.extracted_tasks || []).map((task) => `<div class="integration-row"><span><b>${escapeHtml(task.title)}</b><span class="meta">${escapeHtml(task.public_id)}</span></span><span class="pill info">${escapeHtml(task.status)}</span></div>`).join("")}
      </div>
    </div>
    <div class="card card-pad mt-20"><div class="card-head"><div class="card-title">Live-транскрипт</div></div><div id="transcript-lines" class="col gap-10">${liveLines.map(lineHtml).join("") || '<div class="dim">Строки появятся после начала записи.</div>'}</div></div>`;
}

function bindActions(content, meeting) {
  content.querySelectorAll(".rsvp").forEach((button) => {
    button.onclick = async () => {
      await api.meetings.rsvp(meeting.id, button.dataset.status);
      toast("Ответ сохранён");
    };
  });
  content.querySelector("#confirm-meeting")?.addEventListener("click", async () => {
    await api.meetings.confirm(meeting.id);
    location.reload();
  });
  content.querySelector("#cancel-meeting")?.addEventListener("click", async () => {
    await api.meetings.cancel(meeting.id);
    location.reload();
  });
}

function lineHtml(line) {
  return `<div class="code-msg"><span class="accent-text">${escapeHtml(line.speaker_name || line.speaker || "Участник")}</span> ${escapeHtml(line.text || "")}</div>`;
}
