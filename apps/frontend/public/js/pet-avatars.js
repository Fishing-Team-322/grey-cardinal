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

  window.PET_TYPES = [
    { id: 'fox',      name: 'Лисёнок-стратег',  trait: 'Умный · собранный · планирует',  desc: 'Команды, которые хорошо планируют, держат дедлайны и закрывают задачи в срок.', accent: '#FB923C' },
    { id: 'capybara', name: 'Капибара гармонии', trait: 'Спокойная · поддерживающая',      desc: 'Команды с тёплой коммуникацией, низким напряжением и высокой взаимопомощью.',   accent: '#34D399' },
    { id: 'dragon',   name: 'Дракончик энергии', trait: 'Мощный · быстрый · батл',         desc: 'Команды с высокой скоростью, объёмом закрытых задач и батл-потенциалом.',       accent: '#F472B6' },
    { id: 'owl',      name: 'Сова фокуса',       trait: 'Внимательная · стабильная',       desc: 'Команды с хорошим фокусом, регулярными статусами и стабильной работой.',        accent: '#818CF8' },
  ];
})();

// ES-module exports для SPA-view страницы питомца. gcPet/PET_TYPES также в window.
export const gcPet = window.gcPet;
export const PET_TYPES = window.PET_TYPES;
