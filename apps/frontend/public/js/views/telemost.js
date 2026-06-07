import { api } from "../api.js";
import { escapeHtml, setTopbar } from "../view-utils.js";

export default async function telemostView(root) {
  setTopbar("Yandex Telemost");
  const status = await api.telemost.status();
  root.querySelector("#telemost-content").innerHTML = `<div class="card card-pad-lg" style="max-width:720px">
    <span class="pill ok"><span class="dot"></span>${escapeHtml(status.mode)}</span>
    <h2 class="mt-16">Telemost доступен</h2>
    <p class="page-desc mt-12">${escapeHtml(status.message)}</p>
  </div>`;
}
