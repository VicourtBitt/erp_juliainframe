/* Small helpers shared by the Chart.js pages. */
window.JuCharts = (function () {
  const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const palette = ["#2962FF", "#E8590C", "#2B8A3E", "#AE3EC9", "#F59F00", "#0B7285", "#C2255C", "#5C940D", "#495057"];
  const money = (v) => brl.format(v);
  const tooltipMoney = { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${money(ctx.parsed.y)}` } };
  function monthLabel(ym) {
    const [y, m] = ym.split("-");
    return new Date(+y, +m - 1, 1).toLocaleDateString("pt-BR", { month: "short", year: "2-digit" });
  }
  function make(id, config) {
    const el = document.getElementById(id);
    if (!el) return null;
    config.options = Object.assign({ responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false } }, config.options || {});
    return new Chart(el, config);
  }
  return { money, palette, tooltipMoney, monthLabel, make };
})();
