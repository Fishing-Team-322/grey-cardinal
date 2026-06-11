import { api, ApiError } from "../api.js";
import { gcPet, PET_TYPES } from "../pet-avatars.js?v=20260611-1";
import { currentTeam, errorMessage, escapeHtml, setTopbar, toast } from "../view-utils.js";

const num = (value) => Number(value || 0).toLocaleString("ru-RU");

const METRIC_META = {
  productivity: { icon: "M13 2 3 14h7l-1 8 10-12h-7z", col: "#a78bfa" },
  harmony: { icon: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z", col: "#22d3ee" },
  communication: { icon: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z", col: "#4493F8" },
  wellbeing: { icon: "M12 21s-7-4.5-7-10a4 4 0 0 1 7-2 4 4 0 0 1 7 2c0 5.5-7 10-7 10z", col: "#2dd4bf" },
  stability: { icon: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z", col: "#818cf8" },
  tension: { icon: "M13 2 3 14h7l-1 8 10-12h-7z", col: "#3FB660" },
};

const INV_ICONS = {
  hat: '<path d="M12 3 3 9l9 4 9-4zM7 11v5c0 1 2 2 5 2s5-1 5-2v-5"/>',
  glasses: '<circle cx="6" cy="13" r="3.5"/><circle cx="18" cy="13" r="3.5"/><path d="M9.5 13h5M2.5 11l2-2M21.5 11l-2-2"/>',
  scarf: '<path d="M7 4h10v6a5 5 0 0 1-10 0zM10 14v6M14 14v4"/>',
  armor: '<path d="M12 2l8 3v6c0 5-3.5 8-8 11-4.5-3-8-6-8-11V5z"/>',
  bg: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="8" cy="8" r="1.5"/>',
  aura: '<circle cx="12" cy="12" r="5"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
  emotion: '<circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/>',
  badge: '<circle cx="12" cy="9" r="6"/><path d="M9 14l-2 7 5-3 5 3-2-7"/>',
  effect: '<path d="M12 2l2.4 5 5.6.8-4 4 1 5.6L12 20l-5 2.4 1-5.6-4-4 5.6-.8z"/>',
};
const LOCK_ICO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';

function spark(points, col) {
  const pts = points && points.length ? points : [0, 0];
  const w = 120, h = 30, max = Math.max(...pts), min = Math.min(...pts);
  const xs = (i) => i * (w / (pts.length - 1 || 1));
  const ys = (v) => h - 2 - ((v - min) / (max - min || 1)) * (h - 4);
  const d = pts.map((v, i) => `${i ? "L" : "M"}${xs(i).toFixed(1)} ${ys(v).toFixed(1)}`).join(" ");
  const area = `${d} L${w} ${h} L0 ${h} Z`;
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="30" preserveAspectRatio="none">
    <path d="${area}" fill="${col}" opacity="0.12"/>
    <path d="${d}" fill="none" stroke="${col}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

function canManage(user, teamId) {
  if (user.companies?.some((c) => c.role === "director")) return true;
  return user.teams?.some((t) => String(t.id) === String(teamId) && t.role === "manager");
}

export default async function petView(root, params) {
  const user = window.gcCurrentUser;
  const teamId = params.teamId || currentTeam(user)?.id;
  const manage = canManage(user, teamId);
  setTopbar("Командный питомец");
  const host = root.querySelector("#pet-root");
  if (!teamId) {
    host.innerHTML = '<div class="pet-msg">Не удалось определить команду.</div>';
    return;
  }

  async function load() {
    host.innerHTML = '<div class="view-loading">Загрузка питомца…</div>';
    try {
      const data = await api.teamPet.get(teamId);
      renderLoaded(data);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        renderCreate();
      } else if (error instanceof ApiError && error.status === 403) {
        host.innerHTML = '<div class="pet-msg">Недостаточно прав для просмотра питомца этой команды.</div>';
      } else {
        renderError(error);
      }
    }
  }

  function renderError(error) {
    host.innerHTML = `<div class="pet-msg">
      <span style="color:var(--err)"><svg viewBox="0 0 24 24" width="30" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg></span>
      <div>${escapeHtml(errorMessage(error))}</div>
      <button class="btn btn-ghost btn-sm" id="pet-retry">Повторить</button></div>`;
    host.querySelector("#pet-retry").onclick = load;
  }

  // ---------------- CREATE STATE ----------------
  function renderCreate() {
    const defaults = { fox: "Фоксик", capybara: "Капи", dragon: "Драго", owl: "Совик" };
    let sel = "fox";
    host.innerHTML = `
      <div class="create-wrap">
        <div class="create-head">
          <span class="badge"><span class="dot" style="background:var(--pv2)"></span>Новый питомец команды</span>
          <h1>Создайте <span>командного питомца</span></h1>
          <p>Один общий маскот на команду. Он набирает опыт от закрытых задач, поддержки, статусов и слаженности — и меняет настроение, уровень и внешний вид.</p>
        </div>
        <div class="pick-grid" id="pickGrid"></div>
        <div class="form-card">
          <div class="form-grid">
            <div class="preview-stage"><div class="preview-aura" id="prevAura"></div><div class="preview-pet" id="prevPet"></div></div>
            <div>
              <div class="field"><label>Имя питомца</label>
                <input class="name-input" id="petName" value="${defaults[sel]}" maxlength="40" placeholder="Придумайте имя"></div>
              <div class="desc-line" id="petDesc"></div>
              <div class="flex gap-10 mt-24">
                <button class="btn btn-lg create-btn grow" id="createBtn"${manage ? "" : " disabled title='Только руководитель/директор'"}>Создать питомца</button>
              </div>
              ${manage ? "" : '<div class="faint mt-12" style="font-size:12px">Создать питомца может руководитель или директор команды.</div>'}
            </div>
          </div>
        </div>
      </div>`;
    const grid = host.querySelector("#pickGrid");
    grid.innerHTML = PET_TYPES.map((p) => `
      <div class="pick ${p.id === sel ? "sel" : ""}" data-id="${p.id}">
        <span class="sel-check"><svg viewBox="0 0 24 24" width="14" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 12l5 5L20 6"/></svg></span>
        <div class="glowbg" style="background:radial-gradient(circle, ${p.accent}, transparent 65%)"></div>
        <div style="position:relative">${gcPet(p.id, 92)}</div>
        <div class="sname">${escapeHtml(p.name)}</div>
        <div class="strait">${escapeHtml(p.trait)}</div>
      </div>`).join("");
    const render = () => {
      const p = PET_TYPES.find((x) => x.id === sel);
      host.querySelector("#prevPet").innerHTML = gcPet(sel, 200);
      host.querySelector("#petDesc").textContent = p.desc;
      host.querySelector("#prevAura").style.background = `radial-gradient(circle, ${p.accent}44, transparent 62%)`;
    };
    grid.querySelectorAll(".pick").forEach((el) => el.addEventListener("click", () => {
      grid.querySelectorAll(".pick").forEach((x) => x.classList.remove("sel"));
      el.classList.add("sel");
      sel = el.dataset.id;
      host.querySelector("#petName").value = defaults[sel];
      render();
    }));
    render();
    const btn = host.querySelector("#createBtn");
    if (manage) {
      btn.onclick = async () => {
        const name = host.querySelector("#petName").value.trim() || defaults[sel];
        btn.setAttribute("disabled", "");
        try {
          await api.teamPet.create(teamId, { name, species: sel });
          toast("Питомец создан!", "ok");
          await load();
        } catch (error) {
          btn.removeAttribute("disabled");
          toast(errorMessage(error), "err");
        }
      };
    }
  }

  // ---------------- LOADED STATE ----------------
  function renderLoaded(data) {
    const pet = data.pet || {};
    const appearance = data.appearance || {};
    const speciesName = pet.species_name || pet.species;
    const xpFloor = pet.xp_floor ?? 0;
    const xpNext = pet.xp_next ?? (pet.xp || 0);
    const xpPct = Math.max(0, Math.min(100, Math.round(((pet.xp - xpFloor) / ((xpNext - xpFloor) || 1)) * 100)));

    host.innerHTML = `
      <div class="ph">
        <div>
          <h1>Командный питомец</h1>
          <p class="sub">Питомец растёт вместе с командой: от задач, общения, поддержки и слаженности. Это общий маскот, а не оценка людей.</p>
        </div>
        <div class="ph-actions">
          <button class="btn btn-ghost" id="btnCustom"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2l2.4 5 5.6.8-4 4 1 5.6L12 20l-5 2.4 1-5.6-4-4 5.6-.8z"/></svg> Кастомизация</button>
          <button class="btn btn-ghost" id="btnPrivacy"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg> Приватность</button>
          <button class="btn btn-primary" id="btnBattle"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 9a6 6 0 0 0 12 0V3H6zM6 5H3v2a3 3 0 0 0 3 3M18 5h3v2a3 3 0 0 1-3 3M9 21h6M12 17v4"/></svg> Месячный батл</button>
        </div>
      </div>

      <div class="hero-grid">
        <div class="pet-card">
          <div class="pc-top">
            <div>
              <div class="pet-name">${escapeHtml(pet.name)}${manage ? ' <button class="x-btn" id="btnRename" title="Переименовать" style="width:26px;height:26px;display:inline-grid;vertical-align:middle"><svg viewBox="0 0 24 24" width="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg></button>' : ""}</div>
              <div class="pet-species">${escapeHtml(speciesName)}</div>
            </div>
            <span class="lvl-badge">LVL <span class="mono">${pet.level}</span></span>
          </div>
          <div class="pet-stage"><div class="pet-aura"></div><div class="pet-ground"></div><div class="pet-float" id="heroPet">${gcPet(pet.species, 270)}</div></div>
          <div class="pc-foot">
            <span class="mood-chip mood-focus"><svg viewBox="0 0 24 24" width="16" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M9 10h.01M15 10h.01M8 15h8"/></svg> Настроение: ${escapeHtml(pet.mood_label || "—")}</span>
            <span class="pill acc" id="auraChip"><span class="dot live"></span>${pet.emoji || "🐾"} ${escapeHtml(pet.phrase || "")}</span>
          </div>
        </div>
        <div class="hero-side">
          <div class="hstat">
            <div class="xp-row"><span class="lab"><svg viewBox="0 0 24 24" width="13" fill="none" stroke="var(--pv2)" stroke-width="2"><path d="M13 2 3 14h7l-1 8 10-12h-7z"/></svg>Опыт питомца</span>
              <span class="mono dim" style="font-size:13px">${num(pet.xp)} / ${num(xpNext)} XP</span></div>
            <div class="big mono">Уровень ${pet.level}</div>
            <div class="pet-bar glow"><i style="width:${xpPct}%"></i></div>
          </div>
          <div class="grid g2" style="gap:16px">
            <div class="hstat"><span class="lab"><svg viewBox="0 0 24 24" width="13" fill="none" stroke="#f472b6" stroke-width="2"><path d="M13 2 3 14h7l-1 8 10-12h-7z"/></svg>Сила команды</span>
              <div class="big mono">${num(pet.power_score)}</div>
              <div class="pet-bar power"><i style="width:${Math.min(100, Math.round((pet.power_score || 0) / 100))}%"></i></div></div>
            <div class="hstat"><span class="lab"><svg viewBox="0 0 24 24" width="13" fill="none" stroke="var(--rc-legendary)" stroke-width="2"><path d="M6 9a6 6 0 0 0 12 0V3H6z"/></svg>Рейтинг месяца</span>
              <div class="big mono">${pet.rank ? "#" + pet.rank : "—"}</div>
              <div class="flex gap-6 mt-12 wrap">${pet.rank && pet.rank <= 3 ? '<span class="pill" style="padding:3px 9px"><span class="dot" style="background:var(--rc-legendary)"></span>топ-3</span>' : ""}</div></div>
          </div>
        </div>
      </div>

      <div class="sh"><h2><span class="si"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 3v18M3 12h18"/></svg></span>Виды питомцев</h2><span class="card-sub">вид зависит от характера работы команды</span></div>
      <div class="species-grid" id="speciesGrid"></div>

      <div class="sh"><h2><span class="si"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 3v18h18M7 14l3-4 4 3 5-7"/></svg></span>Метрики команды</h2><span class="card-sub">агрегированные сигналы</span></div>
      <div class="metrics-grid" id="metricsGrid"></div>

      <div class="grid mt-24" style="grid-template-columns:1.25fr 1fr; align-items:start; gap:16px">
        <div class="card card-pad">
          <div class="card-head"><div class="card-title">Почему питомец изменился?</div><span class="card-sub">последние события</span></div>
          <div id="feed"><div class="view-loading">Загрузка…</div></div>
          <div class="flex between center mt-16"><span class="faint" style="font-size:12px">События формируются из задач, статусов и активности — без оценки отдельных людей.</span></div>
        </div>
        <div class="card card-pad">
          <div class="card-head"><div class="card-title">Wellbeing команды</div><span class="card-sub" id="wbStatus"></span></div>
          <div id="wellbeing"><div class="view-loading">Загрузка…</div></div>
        </div>
      </div>

      <div class="sh" id="inventory"><h2><span class="si"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 7h18v13H3zM3 7l2-3h14l2 3M12 7v13"/></svg></span>Кастомизация питомца</h2><span class="card-sub" id="invCount"></span></div>
      <div class="inv-tabs" id="invTabs"></div>
      <div class="inv-grid" id="invGrid"></div>

      <div class="sh" id="battle"><h2><span class="si"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 9a6 6 0 0 0 12 0V3H6zM6 5H3v2a3 3 0 0 0 3 3M18 5h3v2a3 3 0 0 1-3 3M9 21h6M12 17v4"/></svg></span>Месячный батл команд</h2><span class="card-sub">дружеское соревнование питомцев</span></div>
      <div id="battleBanner"></div>
      <div id="battleList"><div class="view-loading">Загрузка…</div></div>

      ${privacyModalHtml(data.privacy || {})}`;

    // species showcase
    host.querySelector("#speciesGrid").innerHTML = PET_TYPES.map((p) => `
      <div class="species ${p.id === pet.species ? "active" : ""}">
        ${p.id === pet.species ? '<span class="active-tag pill acc" style="padding:2px 8px"><span class="dot live"></span>активен</span>' : ""}
        <div class="glowbg" style="background:radial-gradient(circle, ${p.accent}, transparent 65%)"></div>
        <div style="position:relative">${gcPet(p.id, 104)}</div>
        <div class="sname">${escapeHtml(p.name)}</div>
        <div class="strait">${escapeHtml(p.trait)}</div>
        <div class="sdesc">${escapeHtml(p.desc)}</div>
      </div>`).join("");

    renderMetrics(data.metrics || []);

    // buttons
    host.querySelector("#btnCustom").onclick = () => host.querySelector("#inventory").scrollIntoView({ behavior: "smooth" });
    host.querySelector("#btnBattle").onclick = () => host.querySelector("#battle").scrollIntoView({ behavior: "smooth" });
    bindPrivacyModal(data.privacy || {});
    if (manage && host.querySelector("#btnRename")) {
      host.querySelector("#btnRename").onclick = async () => {
        const name = prompt("Новое имя питомца", pet.name);
        if (!name || !name.trim()) return;
        try {
          await api.teamPet.rename(teamId, name.trim());
          toast("Имя обновлено", "ok");
          await load();
        } catch (error) { toast(errorMessage(error), "err"); }
      };
    }

    loadFeed();
    loadInventory();
    loadWellbeing();
    loadBattle();
  }

  function renderMetrics(metrics) {
    host.querySelector("#metricsGrid").innerHTML = metrics.map((mtr) => {
      const meta = METRIC_META[mtr.key] || { icon: METRIC_META.productivity.icon, col: "#a78bfa" };
      const col = mtr.key === "tension" ? (mtr.status === "good" ? "#3FB660" : mtr.status === "warn" ? "#D9A441" : "#E5484D") : meta.col;
      const trendColor = mtr.status === "good" ? "var(--ok)" : mtr.status === "warn" ? "var(--warn)" : "var(--text-faint)";
      return `<div class="metric">
        <div class="mt"><div class="mname"><span class="ic" style="background:${col}22;color:${col}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="${meta.icon}"/></svg></span>${escapeHtml(mtr.label)}</div>
          <span class="mtrend" style="color:${trendColor}">${escapeHtml(mtr.trend || "")}</span></div>
        <div class="pct" style="${mtr.key === "tension" ? "font-size:20px;color:" + col : ""}">${escapeHtml(mtr.display)}</div>
        <div class="spark">${spark(mtr.sparkline, col)}</div>
        <div class="exp">${escapeHtml(mtr.explanation || "")}</div></div>`;
    }).join("");
  }

  async function loadFeed() {
    try {
      const data = await api.teamPet.events(teamId, { limit: 20 });
      const items = data.items || [];
      host.querySelector("#feed").innerHTML = items.length
        ? items.map((f) => `<div class="feed-item">
            <span class="feed-badge ${f.positive ? "fb-pos" : "fb-neg"}">${escapeHtml(f.delta)}</span>
            <div><div class="ftxt">${escapeHtml(f.title)}</div><div class="fmeta">${escapeHtml(relTime(f.created_at))}${f.meta ? " · " + escapeHtml(f.meta) : ""}</div></div></div>`).join("")
        : '<div class="dim" style="padding:16px 0">Событий пока нет — питомец только начинает свой путь.</div>';
    } catch (error) {
      host.querySelector("#feed").innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    }
  }

  let invData = null;
  let curCat = "hat";
  async function loadInventory() {
    try {
      invData = await api.teamPet.inventory(teamId);
      const cats = invData.categories || [];
      host.querySelector("#invCount").innerHTML = `<span class="mono">${invData.owned_count}</span> из <span class="mono">${invData.total_count}</span> предметов открыто`;
      host.querySelector("#invTabs").innerHTML = cats.map((c, i) => `<button class="inv-tab ${i === 0 ? "active" : ""}" data-cat="${c.id}">${escapeHtml(c.label)}</button>`).join("");
      host.querySelectorAll("#invTabs .inv-tab").forEach((t) => t.addEventListener("click", () => {
        host.querySelectorAll("#invTabs .inv-tab").forEach((x) => x.classList.remove("active"));
        t.classList.add("active");
        renderInv(t.dataset.cat);
      }));
      // aura chip name
      const aura = (invData.items || []).find((it) => it.category === "aura" && it.status === "equipped");
      if (aura) host.querySelector("#auraChip").innerHTML = `<span class="dot live"></span>Аура: ${escapeHtml(aura.name)}`;
      curCat = cats[0]?.id || "hat";
      renderInv(curCat);
    } catch (error) {
      host.querySelector("#invGrid").innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    }
  }

  function renderInv(cat) {
    curCat = cat;
    const items = (invData.items || []).filter((x) => x.category === cat);
    host.querySelector("#invGrid").innerHTML = items.map((it) => {
      const locked = it.status === "locked";
      const equipped = it.status === "equipped";
      return `<div class="inv-item r-${it.rarity} ${locked ? "locked" : "owned"} ${equipped ? "equipped" : ""}">
        ${equipped ? '<span class="equipped-tag">НАДЕТО</span>' : ""}
        <div class="inv-tile"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">${locked ? "" : (INV_ICONS[it.category] || "")}</svg>${locked ? `<span style="position:absolute;color:var(--text-faint)">${LOCK_ICO}</span>` : ""}</div>
        <div class="inv-name">${escapeHtml(it.name)}</div>
        <div class="rar">${escapeHtml(it.rarity)}</div>
        ${locked
          ? `<div class="lock-cond">${LOCK_ICO}<span>${escapeHtml(it.unlock_condition || "Заблокировано")}</span></div>`
          : `<div class="act">${equipped
              ? '<button class="btn btn-sm btn-ghost btn-block" disabled style="opacity:.6">Надето</button>'
              : (manage ? `<button class="btn btn-sm btn-primary btn-block" data-equip="${escapeHtml(it.item_id)}">Надеть</button>` : '<button class="btn btn-sm btn-ghost btn-block" disabled style="opacity:.6">В наличии</button>')}</div>`}
      </div>`;
    }).join("");
    host.querySelectorAll("#invGrid [data-equip]").forEach((b) => b.addEventListener("click", async () => {
      b.setAttribute("disabled", "");
      try {
        const res = await api.teamPet.equip(teamId, b.getAttribute("data-equip"));
        invData = res.inventory;
        if (res.pet?.appearance) updateHeroAppearance(res.pet);
        toast("Предмет надет", "ok");
        renderInv(curCat);
      } catch (error) {
        b.removeAttribute("disabled");
        toast(errorMessage(error), "err");
      }
    }));
  }

  function updateHeroAppearance(petPayload) {
    const aura = (invData.items || []).find((it) => it.category === "aura" && it.status === "equipped");
    if (aura) host.querySelector("#auraChip").innerHTML = `<span class="dot live"></span>Аура: ${escapeHtml(aura.name)}`;
  }

  async function loadWellbeing() {
    try {
      const data = await api.teamPet.wellbeing(teamId);
      const cards = data.cards || [];
      const enabled = data.analysis_enabled !== false;
      host.querySelector("#wbStatus").innerHTML = enabled
        ? '<span class="pill ok" style="padding:2px 8px"><span class="dot"></span>анализ включён</span>'
        : '<span class="pill idle" style="padding:2px 8px"><span class="dot"></span>анализ выключен</span>';
      host.querySelector("#wellbeing").innerHTML = cards.map((w) => `
        <div class="wb-item">
          <div class="wb-head"><span class="wb-name">${escapeHtml(w.label)}</span><span class="pill ${w.status_color === "ok" ? "ok" : w.status_color === "warn" ? "warn" : "err"}" style="padding:2px 8px"><span class="dot"></span>${escapeHtml(w.status)}</span></div>
          <div class="pet-bar" style="margin-top:9px;height:6px"><i style="width:${Math.min(100, w.value)}%"></i></div>
          <div class="wb-exp">${escapeHtml(w.explanation || "")}</div></div>`).join("")
        || '<div class="dim">Нет данных.</div>';
    } catch (error) {
      host.querySelector("#wellbeing").innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    }
  }

  async function loadBattle() {
    try {
      const data = await api.teamPet.battleLeaderboard(teamId);
      const battle = data.battle || {};
      const items = data.items || [];
      host.querySelector("#battleBanner").innerHTML = `
        <div class="battle-banner">
          <div class="flex center gap-20 wrap">
            <div><div class="eyebrow" style="color:var(--rc-legendary)">до конца батла</div><div class="mono" style="font-size:26px;font-weight:800;margin-top:2px">${battle.days_left ?? 0} дней</div></div>
            <div class="reward"><span class="rw-ic"><svg viewBox="0 0 24 24" width="22" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2l2.4 5 5.6.8-4 4 1 5.6L12 20l-5 2.4 1-5.6-4-4 5.6-.8z"/></svg></span>
              <div><div class="faint" style="font-size:12px">награда месяца</div><b style="font-size:15px;color:#f7c878">${escapeHtml(battle.reward_label || "—")}</b></div></div>
          </div>
          <span class="tag" style="border-color:rgba(245,182,66,0.3);color:#f7c878">сезон ${escapeHtml(battle.period || "")}</span>
        </div>`;
      host.querySelector("#battleList").innerHTML = items.length
        ? items.map((b) => `<div class="battle-row ${b.is_current_team ? "me" : ""}">
            <div class="br-rank ${b.rank <= 3 ? "top" : ""}">${b.rank === 1 ? "🥇" : b.rank === 2 ? "🥈" : b.rank === 3 ? "🥉" : b.rank}</div>
            <div class="flex center gap-12"><div class="br-pet">${gcPet(b.pet.species, 42)}</div>
              <div class="br-team"><b>${escapeHtml(b.team_name)}${b.is_current_team ? ' <span class="tag" style="padding:1px 6px;font-size:10px">вы</span>' : ""}</b><div class="sp">${escapeHtml(b.pet.species_name)}</div></div></div>
            <div class="br-power">${num(b.power_score)}<span class="faint" style="font-size:11px;font-weight:400"> power</span></div>
            <div class="br-streak pill ok" style="padding:2px 8px"><span class="dot"></span>${escapeHtml(b.streak)}</div>
            <div class="br-reward tag" style="${b.reward === "—" ? "opacity:.4" : "border-color:rgba(245,182,66,0.3);color:#f7c878"}">${escapeHtml(b.reward)}</div></div>`).join("")
        : '<div class="dim" style="padding:16px 0">Пока ни одна команда не присоединилась к батлу.</div>';
    } catch (error) {
      host.querySelector("#battleList").innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    }
  }

  // ---------------- PRIVACY MODAL ----------------
  function privacyModalHtml(p) {
    const tog = (field, on) => `<span class="toggle ${on ? "on" : ""}" data-priv="${field}"></span>`;
    return `<div class="modal-ov" id="privModal">
      <div class="modal">
        <div class="modal-head">
          <div><div class="card-title" style="font-size:18px">Настройки приватности</div>
            <p class="dim" style="font-size:13px;margin-top:6px">Команда сама решает, что анализировать. Созвоны, камера и эмоции — строго по согласию и выключены по умолчанию.</p></div>
          <button class="x-btn" id="privClose"><svg viewBox="0 0 24 24" width="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
        </div>
        <div class="modal-body">
          <div class="priv-row"><div class="pinfo"><div class="pn">Анализировать задачи и дедлайны</div><div class="pd">Основа роста питомца — продуктивность и слаженность</div></div>${tog("analyze_tasks", p.analyze_tasks)}</div>
          <div class="priv-row"><div class="pinfo"><div class="pn">Анализировать сообщения чата</div><div class="pd">Только тон и активность, без чтения личного</div></div>${tog("analyze_chat", p.analyze_chat)}</div>
          <div class="priv-row"><div class="pinfo"><div class="pn">Анализировать созвоны</div><div class="pd"><span style="color:var(--warn)">opt-in</span> · выключено по умолчанию</div></div>${tog("analyze_calls", p.analyze_calls)}</div>
          <div class="priv-row"><div class="pinfo"><div class="pn">Анализировать камеру на созвонах</div><div class="pd"><span style="color:var(--warn)">opt-in</span> · выключено по умолчанию</div></div>${tog("analyze_camera", p.analyze_camera)}</div>
          <div class="priv-row"><div class="pinfo"><div class="pn">Показывать только командные агрегаты</div><div class="pd">Никаких индивидуальных профилей на общем экране</div></div>${tog("team_aggregates_only", p.team_aggregates_only)}</div>
          <div class="priv-row"><div class="pinfo"><div class="pn">Индивидуальные wellbeing-сигналы менеджеру</div><div class="pd"><span class="faint">optional</span> · по решению команды</div></div>${tog("manager_individual_signals", p.manager_individual_signals)}</div>
          <div class="priv-row"><div class="pinfo"><div class="pn">Срок хранения wellbeing-сигналов</div></div><span class="seg-mini" data-seg="retention_days"><b class="${p.retention_days === 30 ? "on" : ""}" data-val="30">30 дней</b><b class="${p.retention_days === 90 ? "on" : ""}" data-val="90">90 дней</b></span></div>
          <div class="priv-row"><div class="pinfo"><div class="pn">Кто видит аналитику</div></div><span class="seg-mini" data-seg="visible_to"><b class="${p.visible_to === "managers" ? "on" : ""}" data-val="managers">Менеджеры</b><b class="${p.visible_to === "team" ? "on" : ""}" data-val="team">Команда</b><b class="${p.visible_to === "admins" ? "on" : ""}" data-val="admins">Админы</b></span></div>
          <div class="priv-note"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg><span>Это инструмент заботы о команде, а не слежки. Никаких «плохих сотрудников» и публичного сравнения людей.</span></div>
          ${manage ? '<div class="flex gap-8 mt-16"><button class="btn btn-primary grow" id="privSave">Сохранить</button><button class="btn btn-ghost" id="privCancel">Отмена</button></div>' : '<div class="faint mt-16" style="font-size:12px">Изменять настройки может руководитель или директор.</div>'}
        </div>
      </div>
    </div>`;
  }

  function bindPrivacyModal(privacy) {
    const modal = host.querySelector("#privModal");
    const open = () => modal.classList.add("open");
    const close = () => modal.classList.remove("open");
    host.querySelector("#btnPrivacy").onclick = open;
    host.querySelector("#privClose").onclick = close;
    modal.addEventListener("click", (e) => { if (e.target.id === "privModal") close(); });
    if (manage) {
      modal.querySelectorAll("[data-priv]").forEach((t) => t.addEventListener("click", () => t.classList.toggle("on")));
      modal.querySelectorAll("[data-seg]").forEach((g) => g.querySelectorAll("b").forEach((b) => b.addEventListener("click", () => {
        g.querySelectorAll("b").forEach((x) => x.classList.remove("on"));
        b.classList.add("on");
      })));
      const save = host.querySelector("#privSave");
      if (save) {
        save.onclick = async () => {
          const body = {};
          modal.querySelectorAll("[data-priv]").forEach((t) => { body[t.dataset.priv] = t.classList.contains("on"); });
          modal.querySelectorAll("[data-seg]").forEach((g) => {
            const active = g.querySelector("b.on");
            if (active) body[g.dataset.seg] = g.dataset.seg === "retention_days" ? Number(active.dataset.val) : active.dataset.val;
          });
          save.setAttribute("disabled", "");
          try {
            await api.teamPet.privacySave(teamId, body);
            toast("Настройки сохранены", "ok");
            close();
            await load();
          } catch (error) {
            save.removeAttribute("disabled");
            toast(errorMessage(error), "err");
          }
        };
        host.querySelector("#privCancel").onclick = close;
      }
    }
  }

  await load();
}

function relTime(iso) {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 90) return "только что";
  if (diff < 3600) return `${Math.round(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.round(diff / 3600)} ч назад`;
  const days = Math.round(diff / 86400);
  if (days === 1) return "вчера";
  return `${days} дн назад`;
}
