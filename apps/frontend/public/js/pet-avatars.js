/* GREY CARDINAL — Team Pet avatars
   Reusable stylized creatures. gcPet(type, size) -> SVG markup.
   Types: fox (strategist), capybara (harmony), dragon (energy), owl (focus)
   Geometric chibi style, soft aura, premium-not-childish. */
(function () {

  const fox = (s) => `<svg viewBox="0 0 220 220" width="${s}" height="${s}" class="pet-svg" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="fxAura" cx="50%" cy="44%" r="54%">
      <stop offset="0%" stop-color="#a78bfa" stop-opacity=".55"/>
      <stop offset="55%" stop-color="#7c5cf0" stop-opacity=".16"/>
      <stop offset="100%" stop-color="#7c5cf0" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="fxBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#FBBF24"/><stop offset="100%" stop-color="#F97316"/></linearGradient>
    <linearGradient id="fxEar" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#F59E0B"/><stop offset="100%" stop-color="#EA580C"/></linearGradient>
  </defs>
  <ellipse cx="110" cy="100" rx="96" ry="96" fill="url(#fxAura)"/>
  <ellipse cx="110" cy="198" rx="48" ry="8" fill="#000" opacity=".28"/>
  <path d="M148 150 C188 152 198 110 184 84 C192 122 166 140 140 138 Z" fill="url(#fxBody)"/>
  <path d="M176 96 C188 114 182 134 166 140 C180 128 178 110 176 96 Z" fill="#FDE9C8"/>
  <path d="M74 156 C74 130 90 118 110 118 C130 118 146 130 146 156 C146 178 130 188 110 188 C90 188 74 178 74 156 Z" fill="url(#fxBody)"/>
  <path d="M91 152 C91 140 99 134 110 134 C121 134 129 140 129 154 C129 170 121 178 110 178 C99 178 91 168 91 152 Z" fill="#FDE9C8"/>
  <path d="M70 80 L56 28 L102 58 Z" fill="url(#fxEar)"/>
  <path d="M150 80 L164 28 L118 58 Z" fill="url(#fxEar)"/>
  <path d="M75 72 L70 46 L92 60 Z" fill="#7C2D12" opacity=".45"/>
  <path d="M145 72 L150 46 L128 60 Z" fill="#7C2D12" opacity=".45"/>
  <path d="M60 86 C60 58 84 46 110 46 C136 46 160 58 160 86 C160 114 138 130 110 130 C82 130 60 114 60 86 Z" fill="url(#fxBody)"/>
  <path d="M82 96 C82 91 92 89 110 89 C128 89 138 91 138 96 C138 113 125 126 110 126 C95 126 82 113 82 96 Z" fill="#FFF7ED"/>
  <ellipse cx="92" cy="88" rx="6.4" ry="8" fill="#26303F"/>
  <ellipse cx="128" cy="88" rx="6.4" ry="8" fill="#26303F"/>
  <circle cx="94.4" cy="84.6" r="2" fill="#fff"/>
  <circle cx="130.4" cy="84.6" r="2" fill="#fff"/>
  <path d="M104 104 L116 104 L110 112 Z" fill="#26303F"/>
  <ellipse cx="79" cy="105" rx="6" ry="3.6" fill="#FB7185" opacity=".5"/>
  <ellipse cx="141" cy="105" rx="6" ry="3.6" fill="#FB7185" opacity=".5"/>
  <g class="pet-orbit" style="transform-origin:166px 44px">
    <rect x="158" y="36" width="16" height="16" rx="3.5" transform="rotate(45 166 44)" fill="#a78bfa" stroke="#c4b5fd" stroke-width="2"/>
  </g>
</svg>`;

  const capybara = (s) => `<svg viewBox="0 0 220 220" width="${s}" height="${s}" class="pet-svg" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="cpAura" cx="50%" cy="46%" r="54%">
      <stop offset="0%" stop-color="#34d399" stop-opacity=".5"/>
      <stop offset="55%" stop-color="#10b981" stop-opacity=".14"/>
      <stop offset="100%" stop-color="#10b981" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="cpBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#C9A06A"/><stop offset="100%" stop-color="#9A7344"/></linearGradient>
  </defs>
  <ellipse cx="110" cy="104" rx="96" ry="96" fill="url(#cpAura)"/>
  <ellipse cx="110" cy="198" rx="52" ry="8" fill="#000" opacity=".28"/>
  <path d="M66 150 C66 132 82 124 110 124 C138 124 154 132 154 150 C154 176 134 188 110 188 C86 188 66 176 66 150 Z" fill="url(#cpBody)"/>
  <ellipse cx="80" cy="74" rx="11" ry="10" fill="#8A6638"/>
  <ellipse cx="140" cy="74" rx="11" ry="10" fill="#8A6638"/>
  <path d="M62 96 C62 68 84 56 110 56 C136 56 158 68 158 96 C158 124 138 140 110 140 C82 140 62 124 62 96 Z" fill="url(#cpBody)"/>
  <ellipse cx="110" cy="118" rx="34" ry="24" fill="#B8915E"/>
  <ellipse cx="95" cy="120" rx="4" ry="5" fill="#3A2A18"/>
  <ellipse cx="125" cy="120" rx="4" ry="5" fill="#3A2A18"/>
  <ellipse cx="92" cy="92" rx="6" ry="7.5" fill="#26303F"/>
  <ellipse cx="128" cy="92" rx="6" ry="7.5" fill="#26303F"/>
  <circle cx="94" cy="89" r="1.8" fill="#fff"/>
  <circle cx="130" cy="89" r="1.8" fill="#fff"/>
  <ellipse cx="78" cy="108" rx="6" ry="3.6" fill="#F59E0B" opacity=".35"/>
  <ellipse cx="142" cy="108" rx="6" ry="3.6" fill="#F59E0B" opacity=".35"/>
  <g class="pet-orbit" style="transform-origin:110px 50px">
    <circle cx="118" cy="52" r="11" fill="#FB923C"/>
    <path d="M118 41 C123 36 130 38 128 45 C124 44 121 45 118 48 Z" fill="#34d399"/>
  </g>
</svg>`;

  const dragon = (s) => `<svg viewBox="0 0 220 220" width="${s}" height="${s}" class="pet-svg" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="drAura" cx="50%" cy="44%" r="56%">
      <stop offset="0%" stop-color="#fb7185" stop-opacity=".55"/>
      <stop offset="50%" stop-color="#f43f5e" stop-opacity=".18"/>
      <stop offset="100%" stop-color="#f43f5e" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="drBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#F472B6"/><stop offset="100%" stop-color="#DB2777"/></linearGradient>
    <linearGradient id="drWing" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#C084FC"/><stop offset="100%" stop-color="#7C3AED"/></linearGradient>
  </defs>
  <ellipse cx="110" cy="100" rx="98" ry="98" fill="url(#drAura)"/>
  <ellipse cx="110" cy="198" rx="46" ry="8" fill="#000" opacity=".28"/>
  <path d="M58 132 C30 120 26 156 46 168 C40 150 52 142 70 148 Z" fill="url(#drWing)"/>
  <path d="M162 132 C190 120 194 156 174 168 C180 150 168 142 150 148 Z" fill="url(#drWing)"/>
  <path d="M78 156 C78 132 92 120 110 120 C128 120 142 132 142 156 C142 178 128 188 110 188 C92 188 78 178 78 156 Z" fill="url(#drBody)"/>
  <path d="M96 150 q14 -10 28 0 q-2 12 -14 12 q-12 0 -14 -12 Z" fill="#FBCFE8"/>
  <path d="M88 48 L80 22 L102 44 Z" fill="#F9A8D4"/>
  <path d="M132 48 L140 22 L118 44 Z" fill="#F9A8D4"/>
  <path d="M64 84 C64 58 86 46 110 46 C134 46 156 58 156 84 C156 110 136 126 110 126 C84 126 64 110 64 84 Z" fill="url(#drBody)"/>
  <path d="M110 60 q-4 8 0 14 q4 -6 0 -14 Z" fill="#FBCFE8"/>
  <ellipse cx="93" cy="86" rx="7" ry="8.5" fill="#26303F"/>
  <ellipse cx="127" cy="86" rx="7" ry="8.5" fill="#26303F"/>
  <circle cx="95.4" cy="82.6" r="2.2" fill="#fff"/>
  <circle cx="129.4" cy="82.6" r="2.2" fill="#fff"/>
  <ellipse cx="103" cy="108" rx="2.4" ry="2" fill="#831843"/>
  <ellipse cx="117" cy="108" rx="2.4" ry="2" fill="#831843"/>
  <g class="pet-flame" style="transform-origin:110px 124px">
    <path d="M110 118 C116 124 116 134 110 140 C104 134 104 124 110 118 Z" fill="#FB923C"/>
    <path d="M110 124 C113 127 113 133 110 137 C107 133 107 127 110 124 Z" fill="#FDE68A"/>
  </g>
</svg>`;

  const owl = (s) => `<svg viewBox="0 0 220 220" width="${s}" height="${s}" class="pet-svg" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <radialGradient id="owAura" cx="50%" cy="44%" r="54%">
      <stop offset="0%" stop-color="#38bdf8" stop-opacity=".5"/>
      <stop offset="52%" stop-color="#6366f1" stop-opacity=".16"/>
      <stop offset="100%" stop-color="#6366f1" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="owBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#818CF8"/><stop offset="100%" stop-color="#4F46E5"/></linearGradient>
  </defs>
  <ellipse cx="110" cy="100" rx="96" ry="96" fill="url(#owAura)"/>
  <ellipse cx="110" cy="198" rx="46" ry="8" fill="#000" opacity=".28"/>
  <path d="M70 58 L62 30 L92 52 Z" fill="url(#owBody)"/>
  <path d="M150 58 L158 30 L128 52 Z" fill="url(#owBody)"/>
  <path d="M64 100 C64 64 84 46 110 46 C136 46 156 64 156 100 C156 142 136 184 110 184 C84 184 64 142 64 100 Z" fill="url(#owBody)"/>
  <path d="M86 150 C86 134 96 126 110 126 C124 126 134 134 134 150 C134 168 124 178 110 178 C96 178 86 168 86 150 Z" fill="#C7D2FE" opacity=".55"/>
  <circle cx="92" cy="92" r="24" fill="#EEF2FF"/>
  <circle cx="128" cy="92" r="24" fill="#EEF2FF"/>
  <circle cx="92" cy="92" r="11" fill="#26303F"/>
  <circle cx="128" cy="92" r="11" fill="#26303F"/>
  <circle cx="95" cy="88" r="3.4" fill="#fff"/>
  <circle cx="131" cy="88" r="3.4" fill="#fff"/>
  <circle cx="92" cy="92" r="24" fill="none" stroke="#38bdf8" stroke-width="2.5" opacity=".8"/>
  <circle cx="128" cy="92" r="24" fill="none" stroke="#38bdf8" stroke-width="2.5" opacity=".8"/>
  <line x1="116" y1="92" x2="104" y2="92" stroke="#38bdf8" stroke-width="2.5" opacity=".8"/>
  <path d="M104 104 L116 104 L110 114 Z" fill="#FBBF24"/>
  <path d="M86 168 q10 10 20 0 M114 168 q10 10 20 0" stroke="#4F46E5" stroke-width="3" stroke-linecap="round"/>
</svg>`;

  const map = { fox, capybara, dragon, owl };
  window.gcPet = (type, size) => (map[type] || fox)(size || 160);

  /* ──────────────────────────────────────────────────────────────────────
     APPEARANCE LAYER — реально надетые предметы поверх питомца.
     gcPetScene(type, size, appearance) -> markup питомца со всей косметикой.
     appearance = { accessories:{hat,glasses,scarf,armor,badge,effect},
                    aura, background, emotion, skin }
     Всё рисуется в системе координат 220×220 (как базовый питомец).
  ────────────────────────────────────────────────────────────────────── */

  const RARITY_COL = { common: "#cbd5e1", rare: "#38bdf8", epic: "#a78bfa", legendary: "#f5b642" };
  const ITEM_RARITY = {
    focus_beanie: "common", sprint_crown: "epic", strategist_top_hat: "rare", champion_helmet: "legendary",
    analyst_glasses: "common", vr_visor: "rare", neon_lenses: "epic", seer_eyes: "legendary",
    team_scarf: "common", cape_scarf: "rare", harmony_silk: "epic", aurora_cape: "legendary",
    light_armor: "common", sprinter_plate: "rare", no_overdue_armor: "epic", leader_aegis: "legendary",
    calm_aura: "common", focus_flow: "rare", warm_support: "epic", rainbow_aura: "legendary",
    focused: "common", joyful: "common", battle_ready: "rare", zen: "epic",
    first_blocker: "common", team_player: "rare", deadline_master: "epic", season_legend: "legendary",
    xp_sparks: "rare", comet_trail: "epic", star_vortex: "legendary", hologram: "epic",
  };
  // Якоря лица/тела по видам (координаты 220×220). hatY = линия лба (низ убора).
  const ANCHOR = {
    fox: { hatY: 58, eyeY: 88, neckY: 128, chestY: 150 },
    capybara: { hatY: 62, eyeY: 92, neckY: 138, chestY: 150 },
    dragon: { hatY: 56, eyeY: 86, neckY: 126, chestY: 150 },
    owl: { hatY: 58, eyeY: 92, neckY: 132, chestY: 150 },
  };
  const rar = (id) => RARITY_COL[ITEM_RARITY[id] || "common"];
  const darken = (hex, k = 0.55) => {
    const n = parseInt(hex.slice(1), 16);
    const r = Math.round(((n >> 16) & 255) * k), g = Math.round(((n >> 8) & 255) * k), b = Math.round((n & 255) * k);
    return `rgb(${r},${g},${b})`;
  };

  // ---- HATS (centered cx=110, brim baseline = by) ----
  const HATS = {
    focus_beanie(by, c) {
      const d = darken(c, 0.7);
      return `<g class="acc-bob"><path d="M80 ${by} C80 ${by - 30} 94 ${by - 36} 110 ${by - 36} C126 ${by - 36} 140 ${by - 30} 140 ${by} Z" fill="${c}"/>
        <rect x="76" y="${by - 7}" width="68" height="13" rx="6.5" fill="${d}"/>
        <circle cx="110" cy="${by - 39}" r="6" fill="${d}"/></g>`;
    },
    strategist_top_hat(by, c) {
      const base = "#1f2430";
      return `<g class="acc-bob"><ellipse cx="110" cy="${by}" rx="42" ry="8" fill="#11151c"/>
        <rect x="84" y="${by - 36}" width="52" height="36" rx="4" fill="${base}"/>
        <rect x="84" y="${by - 12}" width="52" height="10" fill="${c}"/>
        <ellipse cx="110" cy="${by - 36}" rx="26" ry="6" fill="#2b3240"/></g>`;
    },
    sprint_crown(by, c) {
      return `<g class="acc-bob"><path d="M82 ${by} L86 ${by - 24} L98 ${by - 10} L110 ${by - 28} L122 ${by - 10} L134 ${by - 24} L138 ${by} Z" fill="${c}" stroke="${darken(c, 0.7)}" stroke-width="1.5" stroke-linejoin="round"/>
        <rect x="82" y="${by - 4}" width="56" height="8" rx="3" fill="${darken(c, 0.82)}"/>
        <circle cx="110" cy="${by - 25}" r="4" fill="#ff6b9d"/><circle cx="86" cy="${by - 22}" r="2.6" fill="#7dd3fc"/><circle cx="134" cy="${by - 22}" r="2.6" fill="#7dd3fc"/></g>`;
    },
    champion_helmet(by, c) {
      const d = darken(c, 0.62);
      return `<g class="acc-bob"><path d="M78 ${by} C78 ${by - 34} 94 ${by - 42} 110 ${by - 42} C126 ${by - 42} 142 ${by - 34} 142 ${by} Z" fill="${c}"/>
        <path d="M78 ${by} C78 ${by - 34} 94 ${by - 42} 110 ${by - 42}" fill="none" stroke="${d}" stroke-width="3"/>
        <rect x="106" y="${by - 56}" width="8" height="16" rx="3" fill="${d}"/><path d="M110 ${by - 56} q13 -2 16 9 q-11 -4 -16 2 Z" fill="#ff6b6b"/>
        <rect x="76" y="${by - 6}" width="68" height="9" rx="4.5" fill="${d}"/></g>`;
    },
  };
  const hatDefault = (by, c) => HATS.focus_beanie(by, c);

  // ---- GLASSES (eyes at x=92 & x=128, y=ey) ----
  const GLASSES = {
    analyst_glasses(ey, c) {
      return `<g><circle cx="92" cy="${ey}" r="13" fill="rgba(180,220,255,0.16)" stroke="#26303f" stroke-width="3"/>
        <circle cx="128" cy="${ey}" r="13" fill="rgba(180,220,255,0.16)" stroke="#26303f" stroke-width="3"/>
        <path d="M105 ${ey}h10" stroke="#26303f" stroke-width="3"/><path d="M79 ${ey - 4}l-6-3M141 ${ey - 4}l6-3" stroke="#26303f" stroke-width="3" stroke-linecap="round"/></g>`;
    },
    vr_visor(ey, c) {
      return `<g><rect x="72" y="${ey - 13}" width="76" height="26" rx="13" fill="#0b1220" stroke="${c}" stroke-width="2.5"/>
        <rect x="79" y="${ey - 7}" width="62" height="14" rx="7" fill="url(#visorGrad)"/>
        <path d="M86 ${ey}h12M122 ${ey}h12" stroke="${c}" stroke-width="2" opacity=".7"/></g>`;
    },
    neon_lenses(ey, c) {
      return `<g filter="url(#neonGlow)"><rect x="80" y="${ey - 11}" width="26" height="22" rx="8" fill="rgba(167,139,250,0.18)" stroke="${c}" stroke-width="2.5"/>
        <rect x="114" y="${ey - 11}" width="26" height="22" rx="8" fill="rgba(167,139,250,0.18)" stroke="${c}" stroke-width="2.5"/>
        <path d="M106 ${ey}h8" stroke="${c}" stroke-width="2.5"/></g>`;
    },
    seer_eyes(ey, c) {
      return `<g filter="url(#neonGlow)"><circle cx="92" cy="${ey}" r="14" fill="none" stroke="${c}" stroke-width="2.5"/>
        <circle cx="128" cy="${ey}" r="14" fill="none" stroke="${c}" stroke-width="2.5"/>
        <circle cx="92" cy="${ey}" r="5" fill="${c}" opacity=".55"/><circle cx="128" cy="${ey}" r="5" fill="${c}" opacity=".55"/>
        <path d="M106 ${ey}h8" stroke="${c}" stroke-width="2"/></g>`;
    },
  };
  const glassesDefault = GLASSES.analyst_glasses;

  // ---- SCARVES (neck baseline = ny) ----
  function scarf(ny, c) {
    const d = darken(c, 0.72);
    return `<g class="acc-bob"><path d="M82 ${ny} q28 16 56 0 l-3 13 q-25 12 -50 0 Z" fill="${c}"/>
      <path d="M124 ${ny + 8} q10 6 9 26 l-13 -2 q-4 -16 -8 -22 Z" fill="${d}"/></g>`;
  }

  // ---- ARMOR (chest baseline = cy) ----
  function armor(cy, c) {
    const d = darken(c, 0.66);
    return `<g><path d="M88 ${cy} q22 -10 44 0 q4 18 -22 26 q-26 -8 -22 -26 Z" fill="${c}" stroke="${d}" stroke-width="2"/>
      <path d="M110 ${cy - 4}v26" stroke="${d}" stroke-width="2"/><circle cx="110" cy="${cy + 4}" r="3.5" fill="${d}"/></g>`;
  }

  // ---- BADGE (small medallion, chest-left) ----
  function badge(cy, c) {
    return `<g><circle cx="86" cy="${cy + 6}" r="10" fill="${c}" stroke="${darken(c, 0.65)}" stroke-width="1.5"/>
      <path d="M86 ${cy + 1}l1.6 3.3 3.6.5-2.6 2.5.6 3.6-3.2-1.7-3.2 1.7.6-3.6-2.6-2.5 3.6-.5Z" fill="#fff" opacity=".92"/></g>`;
  }

  // ---- EFFECTS (ambient particles, full frame) ----
  const EFFECTS = {
    xp_sparks() {
      return `<g class="acc-spark">${[[40, 60], [176, 70], [54, 150], [168, 140], [110, 30]].map(([x, y], i) =>
        `<path d="M${x} ${y - 6}l1.6 4.4 4.4 1.6-4.4 1.6-1.6 4.4-1.6-4.4-4.4-1.6 4.4-1.6Z" fill="#f5b642" opacity=".9" style="animation-delay:${i * 0.4}s"/>`).join("")}</g>`;
    },
    comet_trail() {
      return `<g class="acc-orbit" style="transform-origin:110px 110px"><circle cx="186" cy="64" r="5" fill="#a78bfa"/>
        <path d="M186 64 L168 52" stroke="#a78bfa" stroke-width="5" stroke-linecap="round" opacity=".5"/></g>`;
    },
    star_vortex() {
      return `<g class="acc-spin" style="transform-origin:110px 110px">${[0, 72, 144, 216, 288].map((a) => {
        const x = 110 + 86 * Math.cos(a * Math.PI / 180), y = 110 + 86 * Math.sin(a * Math.PI / 180);
        return `<path d="M${x} ${y - 5}l1.4 3.6 3.6.4-2.6 2.4.6 3.6-3-1.6-3 1.6.6-3.6-2.6-2.4 3.6-.4Z" fill="#f5b642"/>`;
      }).join("")}</g>`;
    },
    hologram() {
      return `<g class="acc-spark"><circle cx="110" cy="110" r="92" fill="none" stroke="#38bdf8" stroke-width="1.5" stroke-dasharray="3 6" opacity=".5"/>
        <circle cx="110" cy="110" r="78" fill="none" stroke="#22d3ee" stroke-width="1" stroke-dasharray="2 8" opacity=".4"/></g>`;
    },
  };

  // ---- EMOTION (face overlay, eyes at 92/128, y=ey) ----
  const EMOTIONS = {
    joyful(ey) {
      return `<g><ellipse cx="80" cy="${ey + 14}" rx="7" ry="4" fill="#fb7185" opacity=".55"/><ellipse cx="140" cy="${ey + 14}" rx="7" ry="4" fill="#fb7185" opacity=".55"/>
        <path d="M100 ${ey + 22} q10 9 20 0" stroke="#26303f" stroke-width="2.5" fill="none" stroke-linecap="round"/></g>`;
    },
    battle_ready(ey) {
      return `<g><path d="M82 ${ey - 14} l16 5" stroke="#26303f" stroke-width="3" stroke-linecap="round"/><path d="M138 ${ey - 14} l-16 5" stroke="#26303f" stroke-width="3" stroke-linecap="round"/></g>`;
    },
    zen(ey) {
      return `<g class="acc-spark"><text x="150" y="${ey - 18}" font-size="13" fill="#a78bfa" opacity=".8">z</text><text x="160" y="${ey - 28}" font-size="9" fill="#a78bfa" opacity=".6">z</text></g>`;
    },
    focused() { return ""; },
  };

  const SCENE_DEFS = `<defs>
    <linearGradient id="visorGrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
    <filter id="neonGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>`;

  function accessoryOverlay(type, size, appearance) {
    const a = appearance || {};
    const acc = a.accessories || {};
    const an = ANCHOR[type] || ANCHOR.fox;
    let layers = "";
    // effects behind, then body, scarf, armor, hat, glasses, emotion, badge on top
    if (acc.effect) layers += (EFFECTS[acc.effect] || EFFECTS.xp_sparks)();
    if (acc.scarf) layers += scarf(an.neckY, rar(acc.scarf));
    if (acc.armor) layers += armor(an.chestY, rar(acc.armor));
    if (acc.hat) layers += (HATS[acc.hat] || hatDefault)(an.hatY, rar(acc.hat));
    if (acc.glasses) layers += (GLASSES[acc.glasses] || glassesDefault)(an.eyeY, rar(acc.glasses));
    if (a.emotion && EMOTIONS[a.emotion]) layers += EMOTIONS[a.emotion](an.eyeY);
    if (acc.badge) layers += badge(an.chestY, rar(acc.badge));
    if (!layers) return "";
    return `<svg viewBox="0 0 220 220" width="${size}" height="${size}" class="pet-acc" fill="none" xmlns="http://www.w3.org/2000/svg"
      style="position:absolute;inset:0;pointer-events:none">${SCENE_DEFS}${layers}</svg>`;
  }

  window.gcPetScene = (type, size, appearance) => {
    const s = size || 160;
    const overlay = accessoryOverlay(type, s, appearance);
    if (!overlay) return window.gcPet(type, s);
    return `<div class="pet-scene" style="position:relative;width:${s}px;height:${s}px;display:inline-block;line-height:0">${window.gcPet(type, s)}${overlay}</div>`;
  };

  window.PET_TYPES = [
    { id: 'fox',      name: 'Лисёнок-стратег',  trait: 'Умный · собранный · планирует',  desc: 'Команды, которые хорошо планируют, держат дедлайны и закрывают задачи в срок.', accent: '#FB923C' },
    { id: 'capybara', name: 'Капибара гармонии', trait: 'Спокойная · поддерживающая',      desc: 'Команды с тёплой коммуникацией, низким напряжением и высокой взаимопомощью.',   accent: '#34D399' },
    { id: 'dragon',   name: 'Дракончик энергии', trait: 'Мощный · быстрый · батл',         desc: 'Команды с высокой скоростью, объёмом закрытых задач и батл-потенциалом.',       accent: '#F472B6' },
    { id: 'owl',      name: 'Сова фокуса',       trait: 'Внимательная · стабильная',       desc: 'Команды с хорошим фокусом, регулярными статусами и стабильной работой.',        accent: '#818CF8' },
  ];
})();

// ES-module exports для SPA-view страницы питомца. gcPet/PET_TYPES также в window.
export const gcPet = window.gcPet;
export const gcPetScene = window.gcPetScene;
export const PET_TYPES = window.PET_TYPES;
