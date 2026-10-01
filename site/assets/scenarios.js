(function () {
  const DATA = JSON.parse(document.getElementById("scenario-data").textContent);
  const SYS = [
    { k: "CoC6版", c: "var(--coc6)" },
    { k: "CoC7版", c: "var(--coc7)" },
    { k: "エモクロア", c: "var(--emo)" },
  ];
  const ROWS = [["あ", "ぁ-おゔ"], ["か", "か-ご"], ["さ", "さ-ぞ"], ["た", "た-ど"], ["な", "な-の"],
    ["は", "は-ぽ"], ["ま", "ま-も"], ["や", "ゃ-よ"], ["ら", "ら-ろ"], ["わ", "ゎ-ん"]];
  const ORDER = ["ABC", ...ROWS.map((r) => r[0])];
  const coll = new Intl.Collator("ja");
  function rowOf(f) {
    for (const [k, r] of ROWS) if (new RegExp("^[" + r + "]").test(f)) return k;
    return "ABC";
  }
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // 最初は「CoC6版・PL通過」で表示する
  const st = { sys: "CoC6版", q: "", own: false, pl: true, kp: false };

  const $sys = document.getElementById("systems");
  const $index = document.getElementById("index");
  const $list = document.getElementById("list");

  function renderSystems() {
    $sys.innerHTML = SYS.map((s) =>
      `<button class="sys" style="--c:${s.c}" aria-pressed="${st.sys === s.k}" data-s="${s.k}"><span class="dot"></span>${s.k}<span class="count">${DATA.filter((d) => d.s === s.k).length}</span></button>`
    ).join("");
  }

  function renderList() {
    const c = SYS.find((s) => s.k === st.sys).c;
    const q = st.q.trim().toLowerCase();
    const items = DATA.filter((d) => d.s === st.sys && (!st.own || d.own) && (!st.pl || d.pl) && (!st.kp || d.kp) &&
      (!q || d.n.toLowerCase().includes(q) || d.f.toLowerCase().includes(q)))
      .sort((a, b) => ORDER.indexOf(rowOf(a.f)) - ORDER.indexOf(rowOf(b.f)) || coll.compare(a.f, b.f));
    const groups = {};
    items.forEach((d) => (groups[rowOf(d.f)] ??= []).push(d));
    $index.innerHTML = ORDER.map((k) =>
      `<a href="#g-${k === "ABC" ? "abc" : k}" data-g="${k}" ${groups[k] ? "" : 'aria-disabled="true"'}>${k === "ABC" ? "A-Z" : k}</a>`
    ).join("");
    if (!items.length) {
      $list.innerHTML = '<p class="empty">条件に合うシナリオがありません。絞り込みを外してみてください。</p>';
      return;
    }
    $list.innerHTML = ORDER.filter((k) => groups[k]).map((k) => `<section class="group" id="g-${k === "ABC" ? "abc" : k}" data-group="${k}">
      <div class="ghead"><span class="kana ${k === "ABC" ? "latin" : ""}">${k === "ABC" ? "ABC・123" : k}</span><span class="n">${groups[k].length}件</span></div>
      <ul class="rows">${groups[k].map((d) => `<li class="row" style="--c:${c}"><span class="mark" aria-hidden="true"></span>
        <span class="name">${esc(d.n)}${d.ho ? `<span class="ho">${esc(d.ho)}</span>` : ""}</span>
        <span class="meta">${d.own ? '<span class="badge b-own">所持</span>' : ""}${d.pl ? '<span class="badge b-pl">PL通過</span>' : ""}${d.kp ? '<span class="badge b-kp">KP/GM済み</span>' : ""}${d.t.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}${d.url ? `<a class="booth" href="${esc(d.url)}" target="_blank" rel="noopener">BOOTH ↗</a>` : ""}</span></li>`).join("")}</ul></section>`).join("");
  }

  $sys.addEventListener("click", (e) => {
    const b = e.target.closest(".sys");
    if (!b) return;
    st.sys = b.dataset.s;
    renderSystems();
    renderList();
  });
  document.querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => {
    st[b.dataset.k] = !st[b.dataset.k];
    b.setAttribute("aria-pressed", st[b.dataset.k]);
    renderList();
  }));
  document.getElementById("q").addEventListener("input", (e) => { st.q = e.target.value; renderList(); });
  $index.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-g]");
    if (!a) return;
    e.preventDefault();
    document.querySelector(`[data-group="${a.dataset.g}"]`)?.scrollIntoView({ block: "start" });
  });

  const totop = document.getElementById("totop");
  const syncTop = () => { totop.hidden = window.scrollY < 400; };
  window.addEventListener("scroll", syncTop, { passive: true });
  totop.addEventListener("click", () => window.scrollTo({ top: 0 }));

  renderSystems();
  renderList();
  syncTop();
})();
