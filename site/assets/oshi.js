(function () {
  // ライバーと種類のボタンで、好きな歌みた・配信を絞り込む
  const st = { liver: "", kind: "" };
  const cards = [...document.querySelectorAll(".vid")];
  const none = document.getElementById("none");
  function apply() {
    let shown = 0;
    cards.forEach((c) => {
      const ok = (!st.liver || c.dataset.livers.split("|").includes(st.liver)) && (!st.kind || c.dataset.kind === st.kind);
      c.hidden = !ok;
      if (ok) shown++;
    });
    if (none) none.hidden = shown > 0;
  }
  document.querySelectorAll(".chip[data-f]").forEach((b) => b.addEventListener("click", () => {
    st[b.dataset.f] = b.dataset.v;
    document.querySelectorAll(`.chip[data-f="${b.dataset.f}"]`).forEach((x) => x.setAttribute("aria-pressed", x === b));
    apply();
  }));
})();
