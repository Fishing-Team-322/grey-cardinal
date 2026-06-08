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
  bindTranscriptControls(content, meeting, liveLines);

  const update = async (payload) => {
    if (payload?.meeting_id !== meeting.id && payload?.meeting_public_id !== meeting.public_id) return;
    meeting = await api.meetings.get(meeting.id);
    render(content, meeting, liveLines);
    bindActions(content, meeting);
    bindTranscriptControls(content, meeting, liveLines);
  };
  const transcript = (payload) => {
    if (payload?.meeting_id !== meeting.id && payload?.meeting_public_id !== meeting.public_id) return;
    liveLines.push(payload);
    content.querySelector("#transcript-empty")?.remove();
    content.querySelector("#transcript-lines")?.insertAdjacentHTML("beforeend", lineHtml(payload));
    content.querySelector("#transcript-count").textContent = `${liveLines.length} реплик`;
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
    ${recordingAgentHtml(meeting.recording_agent)}
    <div class="card card-pad mt-20">
      <div class="card-head">
        <div><div class="card-title">Транскрипт созвона</div><div class="card-sub" id="transcript-count">${liveLines.length} реплик</div></div>
        <button class="btn btn-sm btn-ghost" id="download-transcript" type="button">Скачать TXT</button>
      </div>
      <div class="transcript-toolbar"><input class="input" id="transcript-search" type="search" placeholder="Поиск по транскрипту"></div>
      <div id="transcript-lines" class="col gap-10 mt-12">${liveLines.map(lineHtml).join("") || '<div class="dim" id="transcript-empty">Строки появятся после начала записи.</div>'}</div>
    </div>`;
}

function recordingAgentHtml(agent) {
  if (!agent) return "";
  const active = ["joining", "recording", "stop_requested"].includes(agent.status);
  return `<div class="card card-pad mt-20">
    <div class="card-head"><div><div class="card-title">Агент записи Телемоста</div>
      <div class="card-sub">Видимый участник · микрофон и камера выключены</div></div>
      <span class="pill ${agent.status === "failed" ? "warn" : active ? "info" : "ok"}">
        <span class="dot ${agent.status === "recording" ? "live" : ""}"></span>${escapeHtml(agent.status)}
      </span>
    </div>
    ${agent.error_message ? `<div class="alert alert-error mt-12">${escapeHtml(agent.error_message)}</div>` : ""}
  </div>`;
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
  return `<div class="code-msg transcript-line" data-transcript="${escapeHtml(`${line.speaker_name || line.speaker || "Участник"} ${line.text || ""}`.toLowerCase())}"><span class="accent-text">${escapeHtml(line.speaker_name || line.speaker || "Участник")}</span> ${escapeHtml(line.text || "")}</div>`;
}

function bindTranscriptControls(content, meeting, lines) {
  const search = content.querySelector("#transcript-search");
  search?.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    content.querySelectorAll(".transcript-line").forEach((line) => {
      line.hidden = query && !line.dataset.transcript.includes(query);
    });
  });
  content.querySelector("#download-transcript")?.addEventListener("click", () => {
    const body = lines.map((line) => `${line.speaker_name || line.speaker || "Участник"}: ${line.text || ""}`).join("\n");
    const blob = new Blob([`${meeting.title}\n${meeting.public_id}\n\n${body}`], { type: "text/plain;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${meeting.public_id}-transcript.txt`;
    link.click();
    URL.revokeObjectURL(link.href);
  });
}
