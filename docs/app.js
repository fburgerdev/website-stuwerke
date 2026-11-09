/* Plant-based Mensa Tracker: renders docs/data.json. No dependencies. */
(async function () {
  const data = await (await fetch("data.json", { cache: "no-cache" })).json();
  const $ = (s, el = document) => el.querySelector(s);
  const NS = "http://www.w3.org/2000/svg";
  const svg = (tag, attrs = {}, parent) => {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(el);
    return el;
  };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const pct = (v, d = 0) => (v == null ? "–" : (v * 100).toFixed(d) + "%");
  const num = (n) => n.toLocaleString("en-GB");
  const RAMP = ["#cfdcb9", "#a3c595", "#6fa878", "#3f8a5d", "#1d5a3c"];
  const STEPS = [0.2, 0.4, 0.6, 0.8];
  const colour = (v) => RAMP[STEPS.filter((s) => v >= s).length];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const byId = Object.fromEntries(data.stuwerke.map((s) => [s.id, s]));
  const stateName = Object.fromEntries(data.states.map((s) => [s.code, s.name]));
  const monthName = (m) => new Date(m + "-15").toLocaleDateString("en-GB", { month: "short", year: "numeric" });

  function change(v) {
    if (v == null) return '<span class="chg flat">–</span>';
    const pts = v * 100;
    if (Math.abs(pts) < 0.5) return '<span class="chg flat">±0</span>';
    return `<span class="chg ${pts > 0 ? "up" : "down"}">${pts > 0 ? "↑" : "↓"} ${Math.abs(pts).toFixed(0)} pts</span>`;
  }
  function bar(now, cls = "") {
    if (!now) return '<span class="nodata">No open menu data</span>';
    const seg = (k, c, label) => (now[k] > 0.004 ? `<i class="${c}" style="flex:0 0 ${(now[k] * 100).toFixed(1)}%" title="${label} ${pct(now[k])}"></i>` : "");
    return `<div class="bar ${cls}" role="img" aria-label="Vegan ${pct(now.vegan)}, vegetarian ${pct(now.vegetarian)}, meat or fish ${pct(now.meat)}, unlabelled ${pct(now.unlabelled)}">` +
      seg("vegan", "v", "Vegan") + seg("vegetarian", "g", "Vegetarian") + seg("meat", "m", "Meat or fish") + seg("unlabelled", "u", "Unlabelled") + "</div>";
  }

  /* ---------- tooltip ---------- */
  const tip = $("#tip");
  function showTip(html, x, y) {
    tip.innerHTML = html; tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x + 16, top = y + 16;
    if (left + r.width > innerWidth - 8) left = x - r.width - 16;
    if (top + r.height > innerHeight - 8) top = y - r.height - 16;
    tip.style.left = Math.max(8, left) + "px"; tip.style.top = Math.max(8, top) + "px";
  }
  const hideTip = () => { tip.hidden = true; };

  /* ---------- hero ---------- */
  const nat = data.national;
  const heroNum = $("#hero-num");
  const target = nat.vegan * 100;
  if (reduce) heroNum.textContent = target.toFixed(0) + "%";
  else {
    const t0 = performance.now();
    (function tick(t) {
      const p = Math.min(1, (t - t0) / 1300), e = 1 - Math.pow(1 - p, 3);
      heroNum.textContent = (target * e).toFixed(0) + "%";
      if (p < 1) requestAnimationFrame(tick);
    })(t0);
  }
  const chTxt = nat.change == null ? "" :
    Math.abs(nat.change) < 0.005 ? " That is about the same as a year ago." :
      ` That is ${Math.abs(nat.change * 100).toFixed(0)} percentage points ${nat.change > 0 ? "more" : "fewer"} than a year ago.`;
  $("#hero-sub").innerHTML =
    `Another <b>${pct(nat.vegetarian)}</b> are vegetarian.${chTxt} Measured over the last four weeks at ` +
    `<b>${nat.in_average} of ${nat.count}</b> Studierendenwerke, the ones whose menus are openly readable and well labelled. Together they serve ` +
    `${pct(nat.students_in_average / nat.students)} of Germany's ${(nat.students / 1e6).toFixed(1)} million students.`;
  $("#method-missing").textContent =
    `${nat.count - nat.with_data} of the ${nat.count} Studierendenwerke have no usable open menu data right now, either because nobody maintains their feed or because their menus carry no vegan labels.`;
  $("#updated").textContent = `Updated ${new Date(data.updated).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}. Shares cover the four weeks from ${data.window[0]}.`;

  /* ---------- line chart ---------- */
  function lineChart(el, series, { h = 170, animate = false } = {}) {
    el.innerHTML = "";
    if (!series || series.length < 3) { el.innerHTML = '<p class="empty">Not enough history yet.</p>'; return; }
    const w = 520, m = { t: 14, r: 46, b: 22, l: 30 };
    const s = svg("svg", { viewBox: `0 0 ${w} ${h}`, role: "img", "aria-label": "Line chart of the vegan share over time" }, el);
    const t = (mth) => { const [y, mo] = mth.split("-").map(Number); return y * 12 + mo - 1; };
    const x0 = t(series[0][0]), x1 = t(series[series.length - 1][0]);
    const ymax = Math.max(0.5, Math.ceil(Math.max(...series.map((p) => p[1])) * 10 + 0.5) / 10);
    const X = (mth) => m.l + ((t(mth) - x0) / Math.max(1, x1 - x0)) * (w - m.l - m.r);
    const Y = (v) => h - m.b - (v / ymax) * (h - m.t - m.b);
    for (let g = 0; g <= ymax + 1e-9; g += ymax > 0.6 ? 0.25 : 0.1) {
      svg("line", { class: "grid", x1: m.l, x2: w - m.r, y1: Y(g), y2: Y(g) }, s);
      svg("text", { class: "axis", x: m.l - 6, y: Y(g) + 4, "text-anchor": "end" }, s).textContent = (g * 100).toFixed(0);
    }
    const years = [...new Set(series.map((p) => p[0].slice(0, 4)))];
    let lastX = -99;
    years.forEach((y, i) => {
      const first = series.find((p) => p[0].startsWith(y));
      const nextX = i + 1 < years.length ? X(series.find((p) => p[0].startsWith(years[i + 1]))[0]) : 1e9;
      if (nextX - X(first[0]) < 34 || X(first[0]) - lastX < 34) return; // skip a stub year at the start
      lastX = X(first[0]);
      svg("text", { class: "axis", x: X(first[0]), y: h - 4 }, s).textContent = y;
    });
    const d = series.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + "," + Y(p[1]).toFixed(1)).join("");
    const path = svg("path", { class: "ln", d }, s);
    if (animate && !reduce) { path.style.setProperty("--len", path.getTotalLength()); path.classList.add("draw"); }
    const last = series[series.length - 1];
    svg("circle", { class: "pt", cx: X(last[0]), cy: Y(last[1]), r: 4.5 }, s);
    svg("text", { class: "endlab", x: X(last[0]) + 9, y: Y(last[1]) + 4 }, s).textContent = pct(last[1]);
    const cross = svg("line", { class: "cross", y1: m.t, y2: h - m.b, visibility: "hidden" }, s);
    const dot = svg("circle", { class: "pt", r: 4.5, visibility: "hidden" }, s);
    const hit = svg("rect", { x: m.l, y: 0, width: w - m.l - m.r, height: h, fill: "transparent" }, s);
    hit.addEventListener("pointermove", (ev) => {
      const r = s.getBoundingClientRect(), px = ((ev.clientX - r.left) / r.width) * w;
      let best = series[0];
      for (const p of series) if (Math.abs(X(p[0]) - px) < Math.abs(X(best[0]) - px)) best = p;
      cross.setAttribute("x1", X(best[0])); cross.setAttribute("x2", X(best[0])); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", X(best[0])); dot.setAttribute("cy", Y(best[1])); dot.setAttribute("visibility", "visible");
      showTip(`<b>${monthName(best[0])}</b><span>Vegan ${pct(best[1], 1)}</span><span>Vegetarian ${pct(best[2], 1)}</span>`, ev.clientX, ev.clientY);
    });
    hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); hideTip(); });
  }
  lineChart($("#nat-chart"), nat.series, { animate: true });

  /* ---------- map ---------- */
  const mapEl = $("#map");
  const m = svg("svg", { viewBox: `0 0 ${data.map.w} ${data.map.h}` }, mapEl);
  const gStates = svg("g", {}, m), gDots = svg("g", {}, m);
  const statePaths = {};
  data.states.forEach((st) => {
    const p = svg("path", { class: "state", d: st.path }, gStates);
    statePaths[st.code] = p;
    p.addEventListener("pointermove", (ev) => {
      p.classList.add("on");
      showTip(`<b>${esc(st.name)}</b><span>${st.with_data} of ${st.count} Studierendenwerke with open data</span>` +
        (st.vegan != null ? `<span class="big">${pct(st.vegan)} vegan</span>` : ""), ev.clientX, ev.clientY);
    });
    p.addEventListener("pointerleave", () => { p.classList.remove("on"); hideTip(); });
  });
  const maxStud = Math.max(...data.stuwerke.map((s) => s.students));
  const radius = (n) => 5 + 17 * Math.sqrt(n / maxStud);
  const dots = {};
  [...data.stuwerke].sort((a, b) => b.students - a.students).forEach((sw, i) => {
    const g = svg("g", { class: `sw ${sw.quality}`, tabindex: 0, role: "button", "aria-label": `${sw.name}: ${sw.now ? pct(sw.now.vegan) + " vegan" : "no open menu data"}` }, gDots);
    g.style.setProperty("--i", i);
    const c = svg("circle", { cx: sw.x, cy: sw.y, r: radius(sw.students) }, g);
    if (sw.now) c.setAttribute("fill", colour(sw.now.vegan));
    dots[sw.id] = g;
    const html = () => `<b>${esc(sw.name)}</b><span>${num(sw.students)} students in ${esc(sw.cities.slice(0, 4).join(", "))}${sw.cities.length > 4 ? " and " + (sw.cities.length - 4) + " more" : ""}</span>` +
      (sw.now ? `<span class="big">${sw.quality === "partial" ? "at least " : ""}${pct(sw.now.vegan)} vegan</span>` +
        (sw.change != null ? `<span>${sw.change >= 0 ? "+" : "−"}${Math.abs(sw.change * 100).toFixed(0)} points in a year</span>` : "")
        : "<span>No open menu data</span>");
    g.addEventListener("pointermove", (ev) => { showTip(html(), ev.clientX, ev.clientY); statePaths[sw.state].classList.add("on"); });
    g.addEventListener("pointerleave", () => { hideTip(); statePaths[sw.state].classList.remove("on"); });
    g.addEventListener("focus", () => { const r = c.getBoundingClientRect(); showTip(html(), r.right, r.top); });
    g.addEventListener("blur", hideTip);
    g.addEventListener("click", () => openDrawer(sw.id));
    g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openDrawer(sw.id); } });
  });
  if (!reduce) { mapEl.classList.add("intro"); setTimeout(() => mapEl.classList.remove("intro"), 2600); }
  $("#swatches").innerHTML = RAMP.map((c, i) => `<span><i style="background:${c}"></i>${i === 0 ? "under 20%" : i === 4 ? "80%+" : STEPS[i - 1] * 100 + "–" + STEPS[i] * 100}</span>`).join("");

  /* ---------- state table ---------- */
  $("#state-table").innerHTML =
    "<thead><tr><th>State</th><th class='r'>In the average</th><th class='r'>Vegan</th><th>Dishes on offer</th><th class='r'>In a year</th></tr></thead><tbody>" +
    [...data.states].sort((a, b) => (b.vegan ?? -1) - (a.vegan ?? -1)).map((s) =>
      `<tr><td class="name">${esc(s.name)}</td><td class="r">${s.in_average} of ${s.count}</td><td class="r">${pct(s.vegan)}</td>` +
      `<td class="barcell">${bar(s.vegan == null ? null : s)}</td><td class="r">${change(s.change)}</td></tr>`).join("") + "</tbody>";

  /* ---------- Studierendenwerk table ---------- */
  let sortKey = "change";
  function renderSW() {
    const val = (s) => sortKey === "name" ? s.short : sortKey === "students" ? s.students : sortKey === "vegan" ? (s.now ? s.now.vegan : -1) : (s.change ?? -9);
    const rows = [...data.stuwerke].sort((a, b) => sortKey === "name" ? a.short.localeCompare(b.short, "de") : val(b) - val(a) || a.short.localeCompare(b.short, "de"));
    $("#sw-table").innerHTML =
      "<thead><tr><th>Studierendenwerk</th><th class='r hide-s'>Students</th><th class='r'>Vegan</th><th>Dishes on offer</th><th class='r'>In a year</th></tr></thead><tbody>" +
      rows.map((s) => `<tr class="click" data-id="${s.id}" tabindex="0"><td class="name">${esc(s.short)}<small>${esc(stateName[s.state])}</small></td>` +
        `<td class="r hide-s">${num(s.students)}</td><td class="r">${s.now ? (s.quality === "partial" ? "≥ " : "") + pct(s.now.vegan) : "–"}</td>` +
        `<td class="barcell">${bar(s.now)}</td><td class="r">${change(s.change)}</td></tr>`).join("") + "</tbody>";
  }
  renderSW();
  $("#sw-table").addEventListener("click", (ev) => { const tr = ev.target.closest("tr[data-id]"); if (tr) openDrawer(tr.dataset.id); });
  $("#sw-table").addEventListener("keydown", (ev) => { const tr = ev.target.closest("tr[data-id]"); if (tr && ev.key === "Enter") openDrawer(tr.dataset.id); });
  document.querySelectorAll(".sort button").forEach((b) => b.addEventListener("click", () => {
    sortKey = b.dataset.sort;
    document.querySelectorAll(".sort button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    renderSW();
  }));

  /* ---------- umbrella bodies ---------- */
  $("#umbrella").innerHTML = data.umbrella.map((u) =>
    `<li><h3>${esc(u.name)}</h3><p class="scope">${esc(u.scope)}</p><p>${esc(u.what)}</p><p><a href="${esc(u.website)}" rel="noopener">${esc(u.website.replace(/^https?:\/\/(www\.)?/, ""))}</a></p></li>`).join("");

  /* ---------- drawer ---------- */
  const drawer = $("#drawer"), scrim = $("#scrim");
  let lastFocus = null;
  function openDrawer(id) {
    const s = byId[id];
    lastFocus = document.activeElement;
    Object.values(dots).forEach((d) => d.classList.remove("on")); dots[id].classList.add("on");
    const now = s.now;
    const list = (title, items, render, empty) => `<h3>${title}</h3>` + (items && items.length ? `<ul class="plain">${items.map(render).join("")}</ul>` : `<p class="empty">${empty}</p>`);
    drawer.innerHTML =
      `<button class="close" type="button">Close</button>` +
      `<h2>${esc(s.name)}</h2><p class="where">${esc(s.seat)}, ${esc(stateName[s.state])}</p>` +
      (now
        ? `<div class="bignum">${s.quality === "partial" ? "≥ " : ""}${pct(now.vegan)}<small>of ${num(now.n)} main dishes offered were vegan</small></div>` +
          `<div style="margin-top:16px">${bar({ vegan: 0, vegetarian: 0, meat: 0, unlabelled: 0 }, "big")}</div>` +
          `<div class="barkey"><span><i style="background:var(--vegan)"></i>Vegan <b>${pct(now.vegan)}</b></span><span><i style="background:var(--veggie)"></i>Vegetarian <b>${pct(now.vegetarian)}</b></span>` +
          `<span><i style="background:var(--meat)"></i>Meat or fish <b>${pct(now.meat)}</b></span><span><i style="background:var(--unl)"></i>Unlabelled <b>${pct(now.unlabelled)}</b></span></div>` +
          (s.quality === "partial" ? `<p class="note">Many dishes here carry no label in the open data, so the true vegan share is probably higher.</p>` : "")
        : `<p class="note">${s.has_feed ? "This Studierendenwerk's open menus do not label vegan dishes separately, so no share can be calculated." : "No current open menu data. Nobody maintains an OpenMensa feed for this Studierendenwerk at the moment."}</p>`) +
      `<div class="facts"><div><b>${num(s.students)}</b><span>students, winter 2024/25</span></div>` +
      (s.change != null ? `<div><b>${s.change >= 0 ? "+" : "−"}${Math.abs(s.change * 100).toFixed(0)} pts</b><span>vegan share, in a year</span></div>` : "") +
      (s.price ? `<div><b>€${s.price.vegan.toFixed(2)} / €${s.price.meat.toFixed(2)}</b><span>typical student price, vegan / meat or fish</span></div>` : "") + `</div>` +
      (now ? `<h3>Vegan share by month</h3><div class="chart" id="d-chart"></div>` : "") +
      `<h3>Cities served</h3><div class="tags">${s.cities.map((c) => `<span>${esc(c)}</span>`).join("")}</div>` +
      (s.universities.length ? list(`Universities served${s.universities_source ? ` · <a href="${esc(s.universities_source)}" rel="noopener">source</a>` : ""}`, s.universities, (u) => `<li>${esc(u)}</li>`, "") : "") +
      (now && s.canteens.length ? `<h3>Canteens, last four weeks</h3><ul class="rows">${s.canteens.map((c) =>
        `<li><span>${esc(c.name.replace(/^[^,]+, /, ""))}</span>${bar({ vegan: c.vegan, vegetarian: c.vegetarian, meat: 0, unlabelled: 0 })}<span>${pct(c.vegan)}</span></li>`).join("")}</ul>` : "") +
      list("Decisions and announcements", s.milestones, (x) => `<li>${esc(x.text)}<small>${esc(x.date)} · <a href="${esc(x.source)}" rel="noopener">source</a></small></li>`, "None recorded yet.") +
      list("Published contacts", s.people, (p) => `<li>${esc(p.name)}<small>${esc(p.role)} · <a href="${esc(p.source)}" rel="noopener">source</a>, ${esc(p.as_of)}</small></li>`, "None recorded yet.") +
      `<h3>Website</h3><p><a href="${esc(s.website)}" rel="noopener">${esc(s.website.replace(/^https?:\/\/(www\.)?/, ""))}</a></p>`;
    drawer.classList.add("open"); drawer.setAttribute("aria-hidden", "false");
    scrim.hidden = false; requestAnimationFrame(() => scrim.classList.add("show"));
    $(".close", drawer).addEventListener("click", closeDrawer);
    $(".close", drawer).focus({ preventScroll: true });
    drawer.scrollTop = 0;
    if (now) {
      lineChart($("#d-chart", drawer), s.series, { h: 160 });
      // grow the bar from zero so the split reads as a reveal
      const segs = [["v", now.vegan], ["g", now.vegetarian], ["m", now.meat], ["u", now.unlabelled]];
      const big = $(".bar.big", drawer);
      big.innerHTML = segs.map(([c]) => `<i class="${c}" style="flex:0 0 0%"></i>`).join("");
      requestAnimationFrame(() => requestAnimationFrame(() => segs.forEach(([, v], i) => { big.children[i].style.flexBasis = (v * 100).toFixed(1) + "%"; })));
    }
    history.replaceState(null, "", "#sw-" + id);
  }
  function closeDrawer() {
    drawer.classList.remove("open"); drawer.setAttribute("aria-hidden", "true");
    scrim.classList.remove("show"); setTimeout(() => { scrim.hidden = true; }, 300);
    Object.values(dots).forEach((d) => d.classList.remove("on"));
    history.replaceState(null, "", location.pathname);
    if (lastFocus) lastFocus.focus({ preventScroll: true });
  }
  scrim.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && drawer.classList.contains("open")) closeDrawer(); });
  const start = location.hash.match(/^#sw-(.+)$/);
  if (start && byId[start[1]]) openDrawer(start[1]);
})();
