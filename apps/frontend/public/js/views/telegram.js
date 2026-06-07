import { api } from "../api.js";
import { currentTeam, errorMessage, escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

export default async function telegramView(root) {
  setTopbar("Telegram");
  const content = root.querySelector("#telegram-content");
  const team = currentTeam(window.gcCurrentUser);
  let timer = null;

  async function render() {
    clearInterval(timer);
    const [personal, teamStatus] = await Promise.all([
      api.telegram.status().catch(() => ({ linked: false })),
      team ? api.teams.telegramStatus(team.id).catch(() => ({ linked: false })) : { linked: false },
    ]);
    content.innerHTML = `<div class="grid g2">
      <div class="card card-pad"><div class="card-head"><div class="card-title">Личный аккаунт</div><span class="pill ${personal.linked ? "ok" : "warn"}"><span class="dot"></span>${personal.linked ? "привязан" : "не привязан"}</span></div>
        ${personal.linked ? `<div class="code-msg">@${escapeHtml(personal.telegram_username || personal.telegram_user_id)}</div><button class="btn btn-ghost mt-16" id="unlink-personal">Отвязать</button>` : '<p class="dim">Бот сможет присылать личные подтверждения и напоминания.</p><button class="btn btn-primary mt-16" id="link-personal">Привязать Telegram</button>'}
        <div id="personal-link" class="mt-16"></div>
      </div>
      <div class="card card-pad"><div class="card-head"><div class="card-title">Чат команды</div><span class="pill ${teamStatus.linked ? "ok" : "warn"}"><span class="dot"></span>${teamStatus.linked ? "подключён" : "не подключён"}</span></div>
        ${team ? `<p class="dim">${escapeHtml(team.name)}</p>${teamStatus.linked ? `<div class="code-msg mt-16">${escapeHtml(teamStatus.tg_chat_id)}</div>` : '<button class="btn btn-primary mt-16" id="bind-team">Получить код чата</button>'}<div id="team-code" class="mt-16"></div>` : '<div class="dim">Команда не выбрана.</div>'}
      </div>
    </div>`;
    content.querySelector("#link-personal")?.addEventListener("click", startPersonalLink);
    content.querySelector("#unlink-personal")?.addEventListener("click", async () => { await api.telegram.unlink(); await render(); });
    content.querySelector("#bind-team")?.addEventListener("click", async () => {
      const result = await api.teams.telegramBindCode(team.id);
      content.querySelector("#team-code").innerHTML = `<div class="note">Добавьте бота в группу и отправьте команду <span class="kbd">/bind ${escapeHtml(result.code)}</span>. Код действует до ${formatDate(result.expires_at)}.</div>`;
    });
  }

  async function startPersonalLink() {
    try {
      const result = await api.telegram.requestLink();
      content.querySelector("#personal-link").innerHTML = `<a class="btn btn-primary btn-block" href="${escapeHtml(result.deep_link)}" target="_blank" rel="noopener">Открыть Telegram</a><div class="code-msg mt-12">${escapeHtml(result.code)}</div><div class="faint mt-8">Ссылка действует до ${formatDate(result.expires_at)}</div>`;
      timer = setInterval(async () => {
        const status = await api.telegram.status();
        if (status.linked) {
          clearInterval(timer);
          toast("Telegram привязан");
          await render();
        }
      }, 1500);
    } catch (error) {
      content.querySelector("#personal-link").innerHTML = `<div class="alert alert-error">${escapeHtml(errorMessage(error))}</div>`;
    }
  }
  await render();
  return () => clearInterval(timer);
}
