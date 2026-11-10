/* Plant-based Mensa Tracker: renders docs/data.json. No dependencies. */
(async function () {
  const data = await (await fetch("data.json", { cache: "no-cache" })).json();
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
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
  const host = (u) => u.replace(/^https?:\/\/(www\.)?/, "").replace(/\/.*$/, "");
  const RAMP = ["#cfdcb9", "#a3c595", "#6fa878", "#3f8a5d", "#1d5a3c"];
  const STEPS = [0.2, 0.4, 0.6, 0.8];
  const colour = (v) => RAMP[STEPS.filter((s) => v >= s).length];
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const byId = Object.fromEntries(data.stuwerke.map((s) => [s.id, s]));
  const stateBy = Object.fromEntries(data.states.map((s) => [s.code, s]));
  const umbrellaBy = Object.fromEntries(data.umbrella.map((u) => [u.id, u]));
  const share = (s) => (s.now ? (s.quality === "partial" ? "≥ " : "") + pct(s.now.vegan) : "–");

  function bar(now, cls = "") {
    if (!now) return "";
    const seg = (k, c, label) => (now[k] > 0.004 ? `<i class="${c}" style="flex:0 0 ${(now[k] * 100).toFixed(1)}%" title="${label} ${pct(now[k])}"></i>` : "");
    return `<div class="bar ${cls}" role="img" aria-label="Plant-based ${pct(now.vegan)}, vegetarian ${pct(now.vegetarian)}, meat or fish ${pct(now.meat)}, unlabelled ${pct(now.unlabelled)}">` +
      seg("vegan", "v", "Plant-based") + seg("vegetarian", "g", "Vegetarian") + seg("meat", "m", "Meat or fish") + seg("unlabelled", "u", "Unlabelled") + "</div>";
  }
  const barKey = (now) =>
    `<div class="barkey"><span><i style="background:var(--vegan)"></i>Plant-based <b>${pct(now.vegan)}</b></span><span><i style="background:var(--veggie)"></i>Vegetarian <b>${pct(now.vegetarian)}</b></span>` +
    `<span><i style="background:var(--meat)"></i>Meat or fish <b>${pct(now.meat)}</b></span><span><i style="background:var(--unl)"></i>Unlabelled <b>${pct(now.unlabelled)}</b></span></div>`;

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

  /* ---------- headline ---------- */
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
  $("#hero-sub").innerHTML =
    `Another <b>${pct(nat.vegetarian)}</b> are vegetarian. Measured over the last four weeks at <b>${nat.in_average} of ${nat.count}</b> ` +
    `Studierendenwerke with well-labelled menus, serving ${pct(nat.students_in_average / nat.students)} of Germany's ${(nat.students / 1e6).toFixed(1)} million students.`;
  $("#method-missing").textContent =
    `${nat.count - nat.with_data} of the ${nat.count} Studierendenwerke have no usable menu data right now: either nobody has built a reader for their website yet, or their menus carry no plant-based labels.`;
  $("#updated").textContent = `Updated ${new Date(data.updated).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}. Shares cover the four weeks from ${data.window[0]}.`;

  /* ---------- map ---------- */
  const mapEl = $("#map");
  const m = svg("svg", { viewBox: `0 0 ${data.map.w} ${data.map.h}` }, mapEl);
  const gStates = svg("g", {}, m), gDots = svg("g", {}, m), gMarks = svg("g", {}, m);
  const statePaths = {}, dots = {};
  const stateTip = (st) => `<b>${esc(st.name)}</b><span>${st.count} Studierendenwerke, ${st.in_average} in the average</span>` +
    (st.vegan != null ? `<span class="big">${pct(st.vegan)} plant-based</span>` : "<span>No average yet</span>");
  data.states.forEach((st) => {
    const p = svg("path", { class: "state", d: st.path, tabindex: 0, role: "button", "aria-label": `${st.name}: ${st.vegan != null ? pct(st.vegan) + " plant-based" : "no average yet"}` }, gStates);
    statePaths[st.code] = p;
    p.addEventListener("pointermove", (ev) => { p.classList.add("on"); showTip(stateTip(st), ev.clientX, ev.clientY); });
    p.addEventListener("pointerleave", () => { p.classList.remove("on"); hideTip(); });
    p.addEventListener("click", () => openState(st.code));
    p.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openState(st.code); } });
  });
  const maxStud = Math.max(...data.stuwerke.map((s) => s.students));
  const radius = (n) => 5 + 17 * Math.sqrt(n / maxStud);
  const swTip = (sw) => `<b>${esc(sw.name)}</b><span>${num(sw.students)} students in ${esc(sw.cities.slice(0, 4).join(", "))}${sw.cities.length > 4 ? " and " + (sw.cities.length - 4) + " more" : ""}</span>` +
    (sw.now ? `<span class="big">${sw.quality === "partial" ? "at least " : ""}${pct(sw.now.vegan)} plant-based</span>` : "<span>No menu data yet</span>");
  [...data.stuwerke].sort((a, b) => b.students - a.students).forEach((sw, i) => {
    const g = svg("g", { class: `sw ${sw.quality}`, tabindex: 0, role: "button", "aria-label": `${sw.name}: ${sw.now ? pct(sw.now.vegan) + " plant-based" : "no menu data yet"}` }, gDots);
    g.style.setProperty("--i", i);
    const c = svg("circle", { cx: sw.x, cy: sw.y, r: radius(sw.students) }, g);
    if (sw.now) c.setAttribute("fill", colour(sw.now.vegan));
    dots[sw.id] = g;
    g.addEventListener("pointermove", (ev) => { showTip(swTip(sw), ev.clientX, ev.clientY); statePaths[sw.state].classList.add("on"); });
    g.addEventListener("pointerleave", () => { hideTip(); statePaths[sw.state].classList.remove("on"); });
    g.addEventListener("focus", () => { const r = c.getBoundingClientRect(); showTip(swTip(sw), r.right, r.top); });
    g.addEventListener("blur", hideTip);
    g.addEventListener("click", () => openSW(sw.id));
    g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openSW(sw.id); } });
  });
  data.highlights.forEach((h, i) => {
    const g = svg("g", { class: "hl", tabindex: 0, role: "button", "aria-label": `Highlight: ${h.title}` }, gMarks);
    g.style.setProperty("--i", i);
    svg("circle", { cx: h.x, cy: h.y, r: 10.5, class: "halo" }, g);
    svg("rect", { x: h.x - 5.5, y: h.y - 5.5, width: 11, height: 11, rx: 1.5, transform: `rotate(45 ${h.x} ${h.y})` }, g);
    const html = `<b>${esc(h.title)}</b><span>${esc(byId[h.sw].short)}</span><span>${esc(h.text)}</span>`;
    g.addEventListener("pointermove", (ev) => showTip(html, ev.clientX, ev.clientY));
    g.addEventListener("pointerleave", hideTip);
    g.addEventListener("click", () => openSW(h.sw));
    g.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openSW(h.sw); } });
  });
  if (!reduce) { mapEl.classList.add("intro"); setTimeout(() => mapEl.classList.remove("intro"), 2800); }
  $("#swatches").innerHTML = RAMP.map((c, i) => `<span><i style="background:${c}"></i>${i === 0 ? "<20%" : i === 4 ? "80%+" : STEPS[i - 1] * 100 + "–" + STEPS[i] * 100}</span>`).join("");
  const flag = (id, on) => { if (dots[id]) dots[id].classList.toggle("on", on); };

  /* ---------- side panel: tabs, search, short list ---------- */
  const listEl = $("#list"), moreEl = $("#more"), qEl = $("#q");
  let tab = "sw", showAll = false;
  const LIMIT = 8;
  const hay = (s) => [s.name, s.short, s.seat, stateBy[s.state].name, ...s.cities, ...s.universities].join(" ").toLowerCase();
  function render() {
    const q = qEl.value.trim().toLowerCase();
    let rows = [];
    if (tab === "sw") {
      const rank = (s) => (s.now ? s.now.vegan + (s.quality === "good" ? 1 : 0) : -1);
      rows = data.stuwerke.filter((s) => !q || hay(s).includes(q))
        .sort((a, b) => rank(b) - rank(a) || a.short.localeCompare(b.short, "de"))
        .map((s) => {
          const hit = q && !s.short.toLowerCase().includes(q) ? s.cities.concat(s.universities).find((x) => x.toLowerCase().includes(q)) : "";
          return `<li><button type="button" data-sw="${s.id}"><span class="nm">${esc(s.short)}<small>${esc(stateBy[s.state].name)}${hit ? " · " + esc(hit) : ""}</small></span>` +
            `${s.now ? bar(s.now) : '<span class="nodata">no data yet</span>'}<span class="val">${share(s)}</span></button></li>`;
        });
    } else if (tab === "states") {
      rows = data.states.filter((s) => !q || s.name.toLowerCase().includes(q))
        .sort((a, b) => (b.vegan ?? -1) - (a.vegan ?? -1) || a.name.localeCompare(b.name))
        .map((s) => `<li><button type="button" data-state="${s.code}"><span class="nm">${esc(s.name)}<small>${s.count} Studierendenwerk${s.count > 1 ? "e" : ""}, ${s.in_average} in the average</small></span>` +
          `${s.vegan != null ? bar(s) : '<span class="nodata">no average yet</span>'}<span class="val">${pct(s.vegan)}</span></button></li>`);
    } else {
      rows = data.highlights.filter((h) => !q || (h.title + " " + h.text + " " + byId[h.sw].short).toLowerCase().includes(q))
        .map((h) => `<li><button type="button" class="hlrow" data-sw="${h.sw}"><i class="mark"></i><span class="nm">${esc(h.title)}<small>${esc(byId[h.sw].short)}</small><em>${esc(h.text)}</em></span></button></li>`);
    }
    const limited = !showAll && !q && rows.length > LIMIT;
    listEl.innerHTML = (limited ? rows.slice(0, LIMIT) : rows).join("") || `<li class="empty">Nothing matches “${esc(qEl.value)}”.</li>`;
    moreEl.hidden = !(rows.length > LIMIT && !q);
    moreEl.textContent = limited ? `Show all ${rows.length}` : "Show fewer";
    qEl.placeholder = tab === "sw" ? "Search a city, university or Studierendenwerk" : tab === "states" ? "Search a state" : "Search highlights";
  }
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => {
    tab = b.dataset.tab; showAll = false; qEl.value = "";
    $$(".tabs button").forEach((x) => x.setAttribute("aria-selected", x === b));
    render();
  }));
  qEl.addEventListener("input", render);
  moreEl.addEventListener("click", () => { showAll = !showAll; render(); });
  listEl.addEventListener("click", (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    if (b.dataset.sw) openSW(b.dataset.sw); else if (b.dataset.state) openState(b.dataset.state);
  });
  const hover = (ev, on) => {
    const b = ev.target.closest && ev.target.closest("button"); if (!b) return;
    if (b.dataset.sw) flag(b.dataset.sw, on);
    if (b.dataset.state) statePaths[b.dataset.state].classList.toggle("on", on);
  };
  listEl.addEventListener("pointerover", (ev) => hover(ev, true));
  listEl.addEventListener("pointerout", (ev) => hover(ev, false));
  render();

  /* ---------- umbrella bodies ---------- */
  const umbrellaCard = (u) => `<li><h3>${esc(u.name)}</h3><p class="scope">${esc(u.scope)}</p><p>${esc(u.what)}</p><p><a href="${esc(u.website)}" rel="noopener">${esc(host(u.website))}</a></p></li>`;
  $("#umbrella").innerHTML = data.umbrella.map(umbrellaCard).join("");

  /* ---------- drawer ---------- */
  const drawer = $("#drawer"), scrim = $("#scrim");
  let lastFocus = null;
  function show(html, hash) {
    if (!drawer.classList.contains("open")) lastFocus = document.activeElement;
    drawer.innerHTML = `<button class="close" type="button">Close</button>` + html;
    drawer.classList.add("open"); drawer.setAttribute("aria-hidden", "false");
    scrim.hidden = false; requestAnimationFrame(() => scrim.classList.add("show"));
    $(".close", drawer).addEventListener("click", closeDrawer);
    $(".close", drawer).focus({ preventScroll: true });
    drawer.scrollTop = 0;
    $$("[data-sw]", drawer).forEach((b) => b.addEventListener("click", () => openSW(b.dataset.sw)));
    $$("[data-state]", drawer).forEach((b) => b.addEventListener("click", () => openState(b.dataset.state)));
    const big = $(".bar.big", drawer);
    if (big && !reduce) {  // grow the bar from zero so the split reads as a reveal
      const widths = [...big.children].map((c) => c.style.flexBasis);
      [...big.children].forEach((c) => { c.style.flexBasis = "0%"; });
      requestAnimationFrame(() => requestAnimationFrame(() => [...big.children].forEach((c, i) => { c.style.flexBasis = widths[i]; })));
    }
    history.replaceState(null, "", hash);
  }
  function closeDrawer() {
    drawer.classList.remove("open"); drawer.setAttribute("aria-hidden", "true");
    scrim.classList.remove("show"); setTimeout(() => { scrim.hidden = true; }, 300);
    Object.keys(dots).forEach((id) => flag(id, false));
    Object.values(statePaths).forEach((p) => p.classList.remove("sel"));
    history.replaceState(null, "", location.pathname);
    if (lastFocus) lastFocus.focus({ preventScroll: true });
  }
  scrim.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && drawer.classList.contains("open")) closeDrawer(); });
  const list = (title, items, renderItem, empty) => `<h3>${title}</h3>` + (items && items.length ? `<ul class="plain">${items.map(renderItem).join("")}</ul>` : `<p class="empty">${empty}</p>`);
  const swRow = (s) => `<li><button type="button" data-sw="${s.id}"><span class="nm">${esc(s.short)}<small>${num(s.students)} students</small></span>${s.now ? bar(s.now) : '<span class="nodata">no data yet</span>'}<span class="val">${share(s)}</span></button></li>`;
  const cname = (c) => c.name.replace(/^[^,]+, /, "");

  /* Canteen map: dots first; the street map behind them loads from openstreetmap.org only after a click. */
  let streetOK = false;
  const merc = (lat, lon, z) => { const n = 256 * 2 ** z, r = lat * Math.PI / 180; return [(lon + 180) / 360 * n, (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * n]; };
  function mapPoints(cs) {
    const pts = cs.map((c, i) => ({ c, i })).filter((p) => p.c.pos);
    if (!pts.length) return pts;
    // drop the odd canteen with a wrong position in the source data (far from all the others)
    const med = (a) => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)];
    const mlat = med(pts.map((p) => p.c.pos[0])), mlon = med(pts.map((p) => p.c.pos[1]));
    return pts.filter((p) => Math.abs(p.c.pos[0] - mlat) < 1.2 && Math.abs(p.c.pos[1] - mlon) < 1.8);
  }
  const canteenMap = (cs) => (mapPoints(cs).length ? `<h3>Where the canteens are</h3><div class="cmap" id="cmap"></div>` : "");
  function drawCanteenMap(el, cs) {
    if (!el) return;
    const pts = mapPoints(cs), W = 440, H = 240, pad = 30;
    const lat = pts.map((p) => p.c.pos[0]), lon = pts.map((p) => p.c.pos[1]);
    const n = Math.max(...lat), so = Math.min(...lat), w = Math.min(...lon), e = Math.max(...lon);
    let z = 16;
    for (; z > 5; z--) { const a = merc(n, w, z), b = merc(so, e, z); if (b[0] - a[0] <= W - 2 * pad && b[1] - a[1] <= H - 2 * pad) break; }
    const a = merc(n, w, z), b = merc(so, e, z), x0 = (a[0] + b[0]) / 2 - W / 2, y0 = (a[1] + b[1]) / 2 - H / 2;
    let tiles = "";
    if (streetOK) {
      for (let tx = Math.floor(x0 / 256); tx <= Math.floor((x0 + W) / 256); tx++) {
        for (let ty = Math.floor(y0 / 256); ty <= Math.floor((y0 + H) / 256); ty++) {
          tiles += `<image href="https://tile.openstreetmap.org/${z}/${tx}/${ty}.png" x="${(tx * 256 - x0).toFixed(1)}" y="${(ty * 256 - y0).toFixed(1)}" width="256.5" height="256.5"></image>`;
        }
      }
    }
    const km = Math.max((e - w) * Math.cos(n * Math.PI / 180), n - so) * 111;
    el.classList.toggle("street", streetOK);
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Map of the canteens">${tiles}` +
      pts.map((p) => { const m = merc(p.c.pos[0], p.c.pos[1], z); return `<circle class="cdot" data-i="${p.i}" cx="${(m[0] - x0).toFixed(1)}" cy="${(m[1] - y0).toFixed(1)}" r="7" fill="${colour(p.c.vegan)}"></circle>`; }).join("") +
      `</svg>` + (streetOK
        ? `<p>Map data © <a href="https://www.openstreetmap.org/copyright" rel="noopener">OpenStreetMap contributors</a></p>`
        : `<p><button class="link" type="button" id="street">Show street map</button> · loads map tiles from openstreetmap.org${pts.length > 1 ? `. The dots span about ${km < 10 ? km.toFixed(1) : km.toFixed(0)} km.` : ""}</p>`);
    $$(".cdot", el).forEach((c) => {
      const cn = cs[+c.dataset.i];
      c.addEventListener("pointermove", (ev) => showTip(`<b>${esc(cname(cn))}</b><span>${esc(cn.city || "")}</span><span class="big">${pct(cn.vegan)} plant-based</span>`, ev.clientX, ev.clientY));
      c.addEventListener("pointerleave", hideTip);
    });
    const btn = $("#street", el);
    if (btn) btn.addEventListener("click", () => { streetOK = true; drawCanteenMap(el, cs); });
  }

  function openSW(id) {
    const s = byId[id], now = s.now;
    Object.keys(dots).forEach((x) => flag(x, x === id));
    Object.values(statePaths).forEach((p) => p.classList.remove("sel"));
    const hls = data.highlights.filter((h) => h.sw === id);
    const html =
      `<h2>${esc(s.name)}</h2><p class="where">${esc(s.seat)}, <button class="link" type="button" data-state="${s.state}">${esc(stateBy[s.state].name)}</button></p>` +
      (now
        ? `<div class="bignum">${s.quality === "partial" ? "≥ " : ""}${pct(now.vegan)}<small>of ${num(now.n)} main dishes offered were plant-based</small></div>` +
          `<div style="margin-top:16px">${bar(now, "big")}</div>${barKey(now)}` +
          (s.quality === "partial" ? `<p class="note">Many dishes here carry no label in the menu data, so the true plant-based share is probably higher.</p>` : "")
        : `<p class="note">${s.has_feed ? "This Studierendenwerk's menus do not label plant-based dishes separately, so no share can be calculated." : "No menu data yet. Its menus are not in OpenMensa, and no reader for its own website exists so far."}</p>`) +
      hls.map((h) => `<div class="hlbox"><i class="mark"></i><div><b>${esc(h.title)}</b><p>${esc(h.text)}${h.source ? ` <a href="${esc(h.source)}" rel="noopener">Source</a>` : ""}</p></div></div>`).join("") +
      `<div class="facts"><div><b>${num(s.students)}</b><span>students, winter 2024/25</span></div>` +
      (s.price ? `<div><b>€${s.price.vegan.toFixed(2)} / €${s.price.meat.toFixed(2)}</b><span>typical student price, plant-based / meat or fish</span></div>` : "") +
      (s.peta ? `<div><b>${s.peta.points} / 100</b><span><a href="${esc(s.peta.source)}" rel="noopener">PETA canteen ranking ${s.peta.year}</a>, ${esc(s.peta.canteen)}${s.peta.more ? ` (best of ${s.peta.more + 1} rated)` : ""}</span></div>` : "") + `</div>` +
      (now ? canteenMap(s.canteens) : "") +
      (now && s.canteens.length ? `<h3>Canteens, last four weeks</h3><ul class="rows">${s.canteens.map((c) =>
        `<li><span>${esc(cname(c))}${c.pos ? ` <a class="osm" href="https://www.openstreetmap.org/?mlat=${c.pos[0]}&mlon=${c.pos[1]}#map=17/${c.pos[0]}/${c.pos[1]}" rel="noopener" title="Open in OpenStreetMap">map</a>` : ""}</span>${bar({ vegan: c.vegan, vegetarian: c.vegetarian, meat: 0, unlabelled: 0 })}<span>${pct(c.vegan)}</span></li>`).join("")}</ul>` : "") +
      `<h3>Cities served</h3><div class="tags">${s.cities.map((c) => `<span>${esc(c)}</span>`).join("")}</div>` +
      (s.universities.length ? list(`Universities served${s.universities_source ? ` · <a href="${esc(s.universities_source)}" rel="noopener">source</a>` : ""}`, s.universities, (u) => `<li>${esc(u)}</li>`, "") : "") +
      list("Decisions and announcements", s.milestones, (x) => `<li>${esc(x.text)}<small>${esc(x.date)} · <a href="${esc(x.source)}" rel="noopener">source</a></small></li>`, "None recorded yet.") +
      list("Published contacts", s.people, (p) => `<li>${esc(p.name)}<small>${esc(p.role)} · <a href="${esc(p.source)}" rel="noopener">source</a>, ${esc(p.as_of)}</small></li>`, "None recorded yet.") +
      `<h3>Website and data</h3><p><a href="${esc(s.website)}" rel="noopener">${esc(host(s.website))}</a></p>` +
      (s.source ? `<p class="empty">Menus read from ${s.source === "website" ? "the Studierendenwerk's own website" : "OpenMensa"}${s.published_until ? `, published up to ${esc(s.published_until)}` : ""}.</p>` : "");
    show(html, "#sw-" + id);
    drawCanteenMap($("#cmap", drawer), s.canteens);
  }

  function openState(code) {
    const st = stateBy[code];
    Object.values(statePaths).forEach((p) => p.classList.remove("sel")); statePaths[code].classList.add("sel");
    Object.keys(dots).forEach((x) => flag(x, false));
    const members = st.members.map((id) => byId[id]).sort((a, b) => (b.now ? b.now.vegan : -1) - (a.now ? a.now.vegan : -1));
    const html =
      `<h2>${esc(st.name)}</h2><p class="where">${st.count} Studierendenwerk${st.count > 1 ? "e" : ""}, ${num(st.students)} students</p>` +
      (st.vegan != null
        ? `<div class="bignum">${pct(st.vegan)}<small>of main dishes offered were plant-based</small></div><div style="margin-top:16px">${bar(st, "big")}</div>${barKey(st)}` +
          `<p class="note">Average of ${st.in_average} of ${st.count} Studierendenwerke with well-labelled menus, weighted by students.</p>`
        : `<p class="note">No average yet: none of this state's Studierendenwerke has well-labelled menu data.</p>`) +
      `<h3>Studierendenwerke</h3><ul class="list in">${members.map(swRow).join("")}</ul>` +
      (st.umbrella.length ? `<h3>Networks</h3><ul class="cards">${st.umbrella.map((id) => umbrellaCard(umbrellaBy[id])).join("")}</ul>` : "");
    show(html, "#state-" + code);
  }

  const start = location.hash.match(/^#(sw|state)-(.+)$/);
  if (start && start[1] === "sw" && byId[start[2]]) openSW(start[2]);
  if (start && start[1] === "state" && stateBy[start[2]]) openState(start[2]);
})();
