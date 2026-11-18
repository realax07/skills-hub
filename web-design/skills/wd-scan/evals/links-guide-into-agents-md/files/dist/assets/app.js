// CSS-in-JS: правило вставляется через CSSOM, в файлах его нет
const s = document.createElement("style"); document.head.appendChild(s);
s.sheet.insertRule(".badge { display:inline-block; padding:2px 8px; border-radius:999px; background:#fff3bf; color:#7c5e00; font-size:12px; }");
// Карточки рендерятся из JS
const items = [["Аналитика","Отчёты в реальном времени"],["Интеграции","50+ сервисов"],["Безопасность","SSO и аудит"]];
document.querySelector("#cards").innerHTML = items.map(([t,d]) => `<article class="card"><span class="badge">новое</span><h3>${t}</h3><p>${d}</p><button class="btn btn-ghost">Подробнее</button></article>`).join("");
// Модалка создаётся в body по клику (как портал)
document.querySelector("[data-open=login]").addEventListener("click", () => {
  const el = document.createElement("div");
  el.className = "modal-backdrop";
  el.innerHTML = `<div class="modal" role="dialog" aria-modal="true" aria-labelledby="lt"><h2 id="lt">Вход</h2><label>Email<input type="email" placeholder="you@acme.io"></label><label>Пароль<input type="password"></label><button class="btn btn-primary">Войти</button></div>`;
  el.addEventListener("click", (e) => e.target === el && el.remove());
  document.body.appendChild(el);
});
document.querySelector(".dropdown > button").addEventListener("click", (e) => e.currentTarget.parentElement.classList.toggle("open"));
