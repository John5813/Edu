(() => {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp;
  const initData = tg && tg.initData;
  const $ = (selector) => document.querySelector(selector);
  const colors = ["#315efb", "#10a37f", "#f29c38", "#8b5cf6", "#e24b5a", "#08a4bd"];
  const weekdays = ["Yakshanba", "Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"];
  const months = ["yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"];
  let period = 30;
  let loading = false;

  if (tg) {
    tg.ready();
    tg.expand();
  }

  function notice(message, good = false) {
    const node = $("#notice");
    node.textContent = message;
    node.classList.toggle("ok", good);
    node.hidden = !message;
  }

  function money(value) {
    return `${Number(value || 0).toLocaleString("uz-UZ")} so‘m`;
  }

  function number(value) {
    return Number(value || 0).toLocaleString("uz-UZ");
  }

  function api(path, options = {}) {
    return fetch(path, {
      cache: "no-store",
      ...options,
      headers: {
        "X-Telegram-Init-Data": initData || "",
        ...(options.headers || {}),
      },
    }).then(async (response) => {
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "So‘rov bajarilmadi");
      return result;
    });
  }

  function svgNode(name, attrs = {}, parent) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
    if (parent) parent.appendChild(node);
    return node;
  }

  function svgFrame(target, viewBox = "0 0 700 250") {
    const root = $(target);
    root.replaceChildren();
    const svg = svgNode("svg", { viewBox, role: "img", "aria-label": root.closest(".panel")?.querySelector("h2")?.textContent || "Grafik" });
    root.appendChild(svg);
    return { root, svg };
  }

  function showEmpty(target, message = "Bu davr uchun ma’lumot yo‘q") {
    const root = $(target);
    root.replaceChildren();
    const label = document.createElement("div");
    label.className = "empty";
    label.textContent = message;
    root.appendChild(label);
  }

  function tickLabel(value, isMoney) {
    if (!isMoney) return number(value);
    const n = Number(value || 0);
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}m`;
    if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
    return number(n);
  }

  function xAxisLabel(date) {
    if (period === 1) return "Bugun";
    const [year, month, day] = date.split("-").map(Number);
    const parsed = new Date(Date.UTC(year, month - 1, day));
    if (period === 7) return weekdays[parsed.getUTCDay()];
    return `${day} ${months[month - 1]}`;
  }

  function xAxisRangeLabel(start, end) {
    if (period !== 90 || start === end) return xAxisLabel(start);
    const [startYear, startMonth, startDay] = start.split("-").map(Number);
    const [endYear, endMonth, endDay] = end.split("-").map(Number);
    if (startYear === endYear && startMonth === endMonth) {
      return `${startDay}–${endDay} ${months[startMonth - 1]}`;
    }
    return `${xAxisLabel(start)}–${xAxisLabel(end)}`;
  }

  function compact(rows, key, limit = 30) {
    if (rows.length <= limit) {
      return rows.map((row) => ({ date: row.date, end_date: row.date, value: Number(row[key] || 0) }));
    }
    const size = Math.ceil(rows.length / limit);
    const grouped = [];
    for (let i = 0; i < rows.length; i += size) {
      const group = rows.slice(i, i + size);
      grouped.push({
        date: group[0].date,
        end_date: group[group.length - 1].date,
        value: group.reduce((sum, row) => sum + Number(row[key] || 0), 0),
      });
    }
    return grouped;
  }

  function lineChart(target, rows, key, isMoney = false) {
    const values = compact(rows, key);
    if (!values.some((row) => row.value)) return showEmpty(target);
    const { svg } = svgFrame(target);
    const width = 700, height = 250, left = 60, right = 15, top = 18, bottom = 38;
    const max = Math.max(...values.map((row) => row.value), 1) * 1.12;
    const chartHeight = height - top - bottom;
    const chartWidth = width - left - right;
    for (let i = 0; i <= 4; i++) {
      const y = top + chartHeight * i / 4;
      const value = max * (4 - i) / 4;
      svgNode("line", { x1: left, y1: y, x2: width - right, y2: y, stroke: "#e9edf4", "stroke-width": 1 }, svg);
      const label = svgNode("text", { x: left - 9, y: y + 4, "text-anchor": "end", fill: "#7c8799", "font-size": 11 }, svg);
      label.textContent = tickLabel(value, isMoney);
    }
    const points = values.map((row, i) => ({
      x: left + (values.length === 1 ? chartWidth / 2 : chartWidth * i / (values.length - 1)),
      y: top + chartHeight - chartHeight * row.value / max,
      ...row,
    }));
    const areaPath = `M ${points[0].x} ${height - bottom} ` +
      points.map((point) => `L ${point.x} ${point.y}`).join(" ") +
      ` L ${points[points.length - 1].x} ${height - bottom} Z`;
    svgNode("path", { d: areaPath, fill: "#315efb", opacity: .09 }, svg);
    svgNode("polyline", {
      points: points.map((point) => `${point.x},${point.y}`).join(" "),
      fill: "none", stroke: "#315efb", "stroke-width": 3, "stroke-linecap": "round", "stroke-linejoin": "round",
    }, svg);
    points.forEach((point) => {
      const circle = svgNode("circle", { cx: point.x, cy: point.y, r: 3.5, fill: "#315efb", stroke: "#fff", "stroke-width": 2 }, svg);
      const title = svgNode("title", {}, circle);
      title.textContent = `${xAxisRangeLabel(point.date, point.end_date)}: ${isMoney ? money(point.value) : number(point.value)}`;
    });
    const step = Math.max(1, Math.floor(points.length / 5));
    points.forEach((point, i) => {
      if (i % step !== 0 && i !== points.length - 1) return;
      const label = svgNode("text", { x: point.x, y: height - 12, "text-anchor": "middle", fill: "#7c8799", "font-size": 10 }, svg);
      label.textContent = xAxisRangeLabel(point.date, point.end_date);
    });
  }

  function barChart(target, items, valueKey = "count", isMoney = false) {
    const usable = (items || []).filter((item) => Number(item[valueKey] || 0) > 0);
    if (!usable.length) return showEmpty(target);
    const { root, svg } = svgFrame(target, `0 0 700 ${Math.max(190, usable.length * 39 + 28)}`);
    const width = 700, top = 10, rowH = 39, labelW = 190, valueW = 92;
    const max = Math.max(...usable.map((item) => Number(item[valueKey] || 0)), 1);
    usable.forEach((item, index) => {
      const y = top + index * rowH;
      const name = svgNode("text", { x: labelW - 10, y: y + 20, "text-anchor": "end", fill: "#526079", "font-size": 12 }, svg);
      name.textContent = item.name || item.key || "";
      const barW = Math.max(2, (width - labelW - valueW) * Number(item[valueKey] || 0) / max);
      svgNode("rect", { x: labelW, y: y + 5, width: barW, height: 18, rx: 7, fill: colors[index % colors.length] }, svg);
      const value = svgNode("text", { x: labelW + barW + 9, y: y + 20, fill: "#263451", "font-size": 11, "font-weight": 700 }, svg);
      value.textContent = isMoney ? tickLabel(item[valueKey], true) : number(item[valueKey]);
    });
    if (root) root.setAttribute("data-chart", "bars");
  }

  function donutChart(target, items, valueKey = "revenue", moneyValues = true) {
    const usable = (items || []).filter((item) => Number(item[valueKey] || 0) > 0);
    if (!usable.length) return showEmpty(target);
    const { root, svg } = svgFrame(target, "0 0 700 235");
    const total = usable.reduce((sum, item) => sum + Number(item[valueKey] || 0), 0);
    const cx = 125, cy = 112, radius = 72, circumference = 2 * Math.PI * radius;
    let offset = 0;
    usable.forEach((item, index) => {
      const value = Number(item[valueKey] || 0);
      const length = circumference * value / total;
      const ring = svgNode("circle", {
        cx, cy, r: radius, fill: "none", stroke: colors[index % colors.length],
        "stroke-width": 25, "stroke-dasharray": `${length} ${circumference - length}`,
        "stroke-dashoffset": -offset, transform: `rotate(-90 ${cx} ${cy})`,
      }, svg);
      const title = svgNode("title", {}, ring);
      title.textContent = `${item.source || item.name}: ${moneyValues ? money(value) : number(value)}`;
      offset += length;
    });
    const centerTop = svgNode("text", { x: cx, y: cy - 2, "text-anchor": "middle", fill: "#24324d", "font-size": 15, "font-weight": 800 }, svg);
    centerTop.textContent = tickLabel(total, moneyValues);
    const centerBottom = svgNode("text", { x: cx, y: cy + 17, "text-anchor": "middle", fill: "#7c8799", "font-size": 10 }, svg);
    centerBottom.textContent = "jami";
    usable.forEach((item, index) => {
      const y = 43 + index * 34;
      svgNode("circle", { cx: 275, cy: y - 4, r: 5, fill: colors[index % colors.length] }, svg);
      const label = svgNode("text", { x: 289, y, fill: "#526079", "font-size": 12 }, svg);
      label.textContent = `${item.source || item.name}: ${moneyValues ? money(item[valueKey]) : number(item[valueKey])}`;
    });
    root.classList.add("donut");
  }

  function drawKpis(summary) {
    const items = [
      ["Tasdiqlangan tushum", money(summary.revenue), `Tanlangan ${period} kun`],
      ["Taxminiy foyda", money(summary.estimated_profit), summary.profit_complete ? "Xizmat va faol kampaniya tannarxi kiritilgan" : "Kiritilgan xarajatlar bo‘yicha taxmin"],
      ["Jami foydalanuvchilar", number(summary.users), `Davrda yangi: ${number(summary.new_users)}`],
      ["Mahsulotlar yakunlandi", number(summary.created), "Hujjat, taqdimot va tayyor ishlar"],
      ["To‘lov qilganlar", number(summary.paying_users), `Davrda faol to‘lovchi: ${number(summary.period_payers)}`],
      ["Bir foydalanuvchiga tushum", money(summary.avg_revenue_per_user), "Umumiy tasdiqlangan tushum / barcha foydalanuvchi"],
      ["To‘lovchi mijoz LTV", money(summary.avg_lifetime_revenue), "Umumiy tushum / to‘lov qilgan mijoz"],
      ["Qayta foydalanish · tarix", `${summary.repeat_use_rate}%`, `${number(summary.repeat_users)} / ${number(summary.spenders)} balans ishlatgan: kamida 2 yechim / kamida 1 yechim`],
      ["Qayta to‘lov · tarix", `${summary.repeat_payment_rate}%`, `${number(summary.repeat_payers)} / ${number(summary.paying_users)} to‘lovchi: 2+ / 1+ tasdiqlangan to‘lov`],
      ["Ilk to‘lovdan keyin ishlatgan", `${summary.cohort_use_rate}%`, `${number(summary.cohort_used_after_first_payment)} / ${number(summary.cohort_first_payers)} ilk to‘lovchilar · tanlangan davr kohorti`],
      ["Ishlatgach qayta to‘lagan", `${summary.cohort_repayment_after_use_rate}%`, `${number(summary.cohort_repaid_after_use)} / ${number(summary.cohort_used_after_first_payment)} ishlatganlar · hozirgacha kuzatilgan`],
      ["Taxminiy foyda / to‘lovchi", money(summary.estimated_profit_per_payer), "Tanlangan davr · xarajatlar taxminiy"],
    ];
    const root = $("#kpis");
    root.replaceChildren();
    items.forEach(([label, value, foot], index) => {
      const card = document.createElement("article");
      card.className = `kpi${index === 1 && (!summary.profit_complete || summary.estimated_profit < 0) ? " warn" : index === 1 ? " good" : ""}`;
      for (const [className, text] of [["kpi-label", label], ["kpi-value", value], ["kpi-foot", foot]]) {
        const node = document.createElement("span");
        node.className = className;
        node.textContent = text;
        card.appendChild(node);
      }
      root.appendChild(card);
    });
  }

  function drawAcquisition(items) {
    const root = $("#chart-acquisition");
    root.replaceChildren();
    if (!items?.length) return showEmpty("#chart-acquisition");
    const { svg } = svgFrame("#chart-acquisition", `0 0 700 ${Math.max(170, items.length * 70 + 20)}`);
    items.forEach((item, index) => {
      const y = 25 + index * 70;
      const label = svgNode("text", { x: 10, y: y + 15, fill: "#34435e", "font-size": 12, "font-weight": 750 }, svg);
      label.textContent = item.source;
      const barMax = 460;
      const value = Number(item.users || 0);
      const barW = value ? Math.max(3, barMax * value / Math.max(...items.map((x) => Number(x.users || 0)), 1)) : 0;
      svgNode("rect", { x: 10, y: y + 24, width: barW, height: 13, rx: 6, fill: colors[index % colors.length] }, svg);
      const stat = svgNode("text", { x: 480, y: y + 35, fill: "#536078", "font-size": 11 }, svg);
      stat.textContent = `${number(item.users)} kishi · ${number(item.payers)} to‘lovchi · ${tickLabel(item.revenue, true)}`;
    });
  }

  function drawFunnel(data) {
    const s = data.summary;
    const items = [
      { name: "Yangi kelgan", value: s.new_users },
      { name: "To‘lov qilgan", value: s.new_payers },
      { name: "Hali to‘lamagan", value: s.unconverted_users },
    ];
    barChart("#chart-funnel", items);
  }

  function drawRepeat(summary) {
    const items = [
      { name: "Ilk to‘lov qilgan kohort", count: summary.cohort_first_payers },
      { name: "To‘lovdan keyin balans ishlatgan", count: summary.cohort_used_after_first_payment },
      { name: "Ishlatgach yana to‘lagan", count: summary.cohort_repaid_after_use },
    ];
    barChart("#chart-repeat", items);
  }

  function drawAI(items) {
    const labels = { photo: "Rasm", image: "AI rasm", text: "Matn" };
    const rows = (items || []).map((item) => ({
      key: `${labels[item.kind] || item.kind}: ${item.name}`,
      name: `${labels[item.kind] || item.kind}: ${item.name}`,
      count: item.count,
    }));
    barChart("#chart-ai", rows.slice(0, 10));
  }

  function drawCampaigns(items) {
    const rows = items || [];
    const chartRows = rows.filter((row) => row.revenue > 0).map((row) => ({ ...row, name: row.name }));
    barChart("#chart-campaigns", chartRows, "revenue", true);
    const body = $("#campaign-table");
    body.replaceChildren();
    rows.forEach((item) => {
      const tr = document.createElement("tr");
      const values = [
        item.name, number(item.sent),
        `${number(item.clicks)} (${number(item.click_rate)}%)`,
        number(item.buyers), money(item.revenue), money(item.cost), money(item.revenue - item.cost),
        item.roi === null ? "—" : `${number(item.roi)}%`,
      ];
      values.forEach((text, index) => {
        const td = document.createElement("td");
        td.textContent = text;
        if (index) td.className = "num";
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  function renderCosts(data) {
    const serviceRoot = $("#service-costs");
    serviceRoot.replaceChildren();
    data.services.forEach((item) => addCostInput(serviceRoot, "service", item.key, item.name,
      item.unit_cost, item.cost_configured, item.cost_configured
        ? `${number(item.count)} ta · tannarx ${money(item.estimated_cost)}`
        : `${number(item.count)} ta · tannarx kiritilmagan`));
    const campaignRoot = $("#campaign-costs");
    campaignRoot.replaceChildren();
    data.campaigns.forEach((item) => addCostInput(campaignRoot, "campaign", item.key, item.name,
      item.cost, item.cost_configured, item.cost_configured
        ? `${number(item.sent)} yuborildi · tushum ${money(item.revenue)}`
        : `${number(item.sent)} yuborildi · xarajat kiritilmagan`));

    const summary = data.summary;
    const incomplete = summary.missing_costs.length
      ? `Tannarx kiritilmagan xizmatlar: ${summary.missing_costs.join(", ")}.`
      : "Faol xizmatlarning tannarxi kiritilgan.";
    const adWarning = summary.campaign_cost_missing
      ? " Ba’zi kampaniya xarajatlari kiritilmagan — foyda to‘liq emas."
      : " Kampaniya xarajatlari kiritilgan.";
    $("#cost-note").textContent = `${incomplete}${adWarning} Foyda tasdiqlangan tushumdan kiritilgan tannarx va kampaniya xarajatlarini ayirib taxmin qilinadi.`;
  }

  function addCostInput(root, category, key, label, value, configured, hint) {
    const row = document.createElement("div");
    row.className = "cost-row";
    const wrapper = document.createElement("div");
    wrapper.style.minWidth = "0";
    const name = document.createElement("label");
    name.textContent = label;
    const note = document.createElement("small");
    note.textContent = hint;
    note.style.cssText = "display:block;color:#8a95a7;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis";
    wrapper.append(name, note);
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "1000000000";
    input.step = "1";
    input.inputMode = "numeric";
    input.value = configured ? String(value || 0) : "";
    input.placeholder = "kiritilmagan";
    input.dataset.category = category;
    input.dataset.key = key;
    input.setAttribute("aria-label", `${label} xarajati`);
    row.append(wrapper, input);
    root.appendChild(row);
  }

  function render(data) {
    $("#period-label").textContent = `${data.period.start} — ${data.period.end}`;
    $("#revenue-label").textContent = period === 90
      ? "Tasdiqlangan to‘lovlar yig‘indisi · so‘m · har nuqta 3 kunlik yig‘indi"
      : "Tasdiqlangan to‘lovlar yig‘indisi · so‘m · har nuqta bir kun";
    document.querySelectorAll(".periods button").forEach((button) =>
      button.classList.toggle("selected", Number(button.dataset.days) === period));
    drawKpis(data.summary);
    lineChart("#chart-revenue", data.daily, "revenue", true);
    lineChart("#chart-users", data.daily, "users");
    lineChart("#chart-created", data.daily, "created");
    barChart("#chart-services", data.services, "count");
    donutChart("#chart-payment-sources", data.payment_sources, "revenue");
    drawAcquisition(data.acquisition);
    drawFunnel(data);
    drawRepeat(data.summary);
    drawAI(data.ai_usage);
    drawCampaigns(data.campaigns);
    renderCosts(data);
  }

  async function load() {
    if (loading) return;
    if (!initData) {
      notice("Admin statistikasi faqat bot ichidan ochiladi. Botdagi 📊 Statistika tugmasini bosing.");
      return;
    }
    loading = true;
    notice("");
    try {
      const data = await api(`/api/v1/admin/statistics?days=${period}`);
      render(data);
    } catch (error) {
      notice(error.message === "Faqat adminlar uchun"
        ? "Kirish taqiqlangan: bu oyna faqat adminlar uchun."
        : `Statistikani yuklab bo‘lmadi: ${error.message}`);
    } finally {
      loading = false;
    }
  }

  async function saveCosts() {
    const status = $("#save-status");
    status.textContent = "Saqlanmoqda…";
    try {
      const service_costs = {};
      const campaign_costs = {};
      document.querySelectorAll(".cost-row input").forEach((input) => {
        const value = Number(input.value);
        if (!input.value.trim()) {
          (input.dataset.category === "service" ? service_costs : campaign_costs)[input.dataset.key] = null;
          return;
        }
        if (!Number.isSafeInteger(value) || value < 0 || value > 1_000_000_000) {
          input.focus();
          throw new Error("Xarajat 0 va 1 milliard so‘m oralig‘idagi butun son bo‘lishi kerak.");
        }
        (input.dataset.category === "service" ? service_costs : campaign_costs)[input.dataset.key] = value;
      });
      await api("/api/v1/admin/statistics/costs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days: period, service_costs, campaign_costs }),
      });
      status.textContent = "Saqlandi";
      status.style.color = "#12805c";
      await load();
    } catch (error) {
      status.textContent = error.message;
      status.style.color = "#bd4339";
    }
  }

  document.querySelectorAll(".periods button").forEach((button) => {
    button.addEventListener("click", () => {
      period = Number(button.dataset.days);
      load();
    });
  });
  $("#refresh").addEventListener("click", load);
  $("#save-costs").addEventListener("click", saveCosts);
  load();
})();
