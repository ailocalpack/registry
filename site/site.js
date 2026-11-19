// The registry site (scripts/site.py). Every page works without this script; it adds the catalog's search and
// filters, the reader's language (from the browser, remembered on this device) and relative times.
(() => {
  "use strict";
  const html = document.documentElement;
  html.classList.remove("no-js");
  html.classList.add("js");

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private window */ } },
  };
  const json = (text, fallback) => { try { return JSON.parse(text); } catch { return fallback; } };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const icon = (id) => `<svg class="i sm" aria-hidden="true"><use href="#${id}"/></svg>`;
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  // ---------------------------------------------------------------- relative times
  const rtf = typeof Intl !== "undefined" && Intl.RelativeTimeFormat ? new Intl.RelativeTimeFormat("en", { numeric: "auto" }) : null;
  function ago(date) {
    const s = (date.getTime() - Date.now()) / 1000;
    const steps = [[60, "second"], [60, "minute"], [24, "hour"], [7, "day"], [4.35, "week"], [12, "month"], [Infinity, "year"]];
    let v = s;
    for (const [size, unit] of steps) {
      if (Math.abs(v) < size) return rtf.format(Math.round(v), unit);
      v /= size;
    }
    return "";
  }
  if (rtf) for (const t of $$("time[datetime]")) {
    const d = new Date(t.getAttribute("datetime"));
    if (!isNaN(d)) { t.title = d.toLocaleString("en"); t.textContent = ago(d); }
  }

  // ---------------------------------------------------------------- the reader's language
  function pickLanguage(names, has) {
    const params = new URLSearchParams(location.search);
    const wanted = params.get("lang") || store.get("lang");
    if (wanted === "*" || (wanted && names[wanted])) return wanted;
    const tags = Object.keys(names);
    const byLower = Object.fromEntries(tags.map(t => [t.toLowerCase(), t]));
    for (const raw of navigator.languages || [navigator.language || ""]) {
      const l = raw.toLowerCase();
      let tag = byLower[l];
      if (!tag && l.startsWith("zh")) tag = /^zh-(tw|hk|mo|hant)/.test(l) ? "zh-Hant" : "zh-Hans";
      if (!tag && l.startsWith("pt")) tag = l === "pt-pt" ? "pt-PT" : "pt-BR";
      if (!tag && l.startsWith("es")) tag = l === "es" || l === "es-es" ? "es-ES" : "es-419";
      if (!tag) tag = tags.find(t => t.toLowerCase().split("-")[0] === l.split("-")[0]);
      if (tag) return has(tag) ? tag : "*";
    }
    return "*";
  }

  const page = document.body.dataset.page;
  if (page === "catalog") catalog();
  if (page === "game") gamePage();
  if (page === "requests") requestsPage();

  // ---------------------------------------------------------------- catalog
  function catalog() {
    const select = $("#lang");
    const names = json(select.dataset.names, {});
    const cards = $$("#results .card").map(el => ({
      el,
      name: el.dataset.name,
      title: el.dataset.title,
      engine: el.dataset.engine,
      stats: json(el.dataset.stats, {}),
      votes: json(el.dataset.votes, {}),
      updated: el.dataset.updated || "",
      likes: +el.dataset.likes || 0,
      works: +el.dataset.works || 0,
    }));
    const hasPacks = tag => cards.some(c => c.stats[tag]);
    const S = { q: "", lang: pickLanguage(names, hasPacks), status: new Set(), engines: new Set(), wanted: false, sort: "likes", view: store.get("view") || "grid" };
    const params = new URLSearchParams(location.search);
    S.q = params.get("q") || "";
    $("#q").value = S.q;
    ensureOption(S.lang);
    select.value = S.lang;
    $("#sort").value = S.sort;

    function ensureOption(tag) {
      if (tag === "*" || [...select.options].some(o => o.value === tag)) return;
      const [en, native] = names[tag] || [tag, tag];
      select.add(new Option(en === native ? en : `${native} · ${en}`, tag));
    }
    const langName = tag => (names[tag] || [tag, tag])[1];

    function statusesOf(c) {
      if (S.lang === "*") {
        const s = new Set(Object.values(c.stats).map(x => x[0]));
        if (Object.keys(c.votes).length) s.add("requested");
        return s;
      }
      const st = c.stats[S.lang];
      return new Set(st ? [st[0]] : c.votes[S.lang] ? ["requested"] : []);
    }
    function inLanguage(c) {
      if (S.lang === "*") return Object.keys(c.stats).length > 0 || (S.wanted && Object.keys(c.votes).length > 0);
      return !!c.stats[S.lang] || (S.wanted && !!c.votes[S.lang]);
    }
    const matchesQuery = c => !S.q || c.name.includes(S.q.trim().toLowerCase());
    function visible(c, ignore = "") {
      if (!matchesQuery(c)) return false;
      if (ignore !== "engine" && S.engines.size && !S.engines.has(c.engine)) return false;
      if (ignore !== "status" && S.status.size) return [...statusesOf(c)].some(s => S.status.has(s));
      return inLanguage(c) || (ignore === "status" && statusesOf(c).size > 0);
    }
    const likesOf = c => S.lang !== "*" && c.stats[S.lang] ? c.stats[S.lang][1] : c.likes;
    const worksOf = c => S.lang !== "*" && c.stats[S.lang] ? c.stats[S.lang][2] : c.works;
    const votesOf = c => S.lang !== "*" ? c.votes[S.lang] || 0 : Object.values(c.votes).reduce((a, b) => a + b, 0);
    const sorters = {
      likes: (a, b) => likesOf(b) - likesOf(a) || b.likes - a.likes || a.title.localeCompare(b.title),
      new: (a, b) => b.updated.localeCompare(a.updated) || a.title.localeCompare(b.title),
      req: (a, b) => votesOf(b) - votesOf(a) || likesOf(b) - likesOf(a),
      az: (a, b) => a.title.localeCompare(b.title),
    };

    function paintCard(c) {
      const el = c.el;
      let badge = "";
      const st = S.lang === "*" ? (Object.keys(c.stats).length === 1 ? Object.values(c.stats)[0] : null) : c.stats[S.lang];
      if (st && st[0] === "verified") badge = `<span class="badge verified">${icon("i-shield")}Verified</span>`;
      else if (st) badge = `<span class="badge alpha">${icon("i-flask")}Alpha</span>`;
      else if (S.lang !== "*" && c.votes[S.lang]) badge = `<span class="badge req">${icon("i-hand")}${c.votes[S.lang]} asked</span>`;
      $(".status", el).innerHTML = badge;
      $(".likes b", el).textContent = likesOf(c);
      $(".works b", el).textContent = worksOf(c);
      const langs = $(".langs", el);
      for (const chip of $$(".lang", langs)) {
        const mine = chip.dataset.lang === S.lang;
        chip.classList.toggle("mine", mine && !chip.classList.contains("wanted"));
        if (mine) langs.prepend(chip);
      }
    }

    function render() {
      const list = cards.filter(c => visible(c));
      list.sort(sorters[S.sort]);
      const grid = $("#results");
      for (const c of cards) c.el.hidden = !list.includes(c);
      for (const c of list) { paintCard(c); grid.append(c.el); }
      grid.classList.toggle("list", S.view === "list");
      for (const b of $$("[data-view]")) b.setAttribute("aria-pressed", String(b.dataset.view === S.view));

      $(".count").innerHTML = `${plural(list.length, "game", "games")} <span>${S.lang === "*" ? "in any language" : "in " + esc(langName(S.lang))}</span>`;
      for (const k of ["verified", "alpha", "requested"]) {
        const n = cards.filter(c => matchesQuery(c) && (!S.engines.size || S.engines.has(c.engine)) && statusesOf(c).has(k)).length;
        $(`[data-count-status="${k}"]`).textContent = n;
      }
      for (const el of $$("[data-count-engine]")) {
        const k = el.dataset.countEngine;
        el.textContent = cards.filter(c => c.engine === k && visible(c, "engine")).length;
      }
      for (const box of $$("[data-status]")) box.checked = S.status.has(box.dataset.status);
      for (const box of $$("[data-engine]")) box.checked = S.engines.has(box.dataset.engine);
      $("[data-wanted]").checked = S.wanted;

      const chips = [];
      if (S.q) chips.push(["q", `“${esc(S.q)}”`]);
      for (const s of S.status) chips.push(["s:" + s, s[0].toUpperCase() + s.slice(1)]);
      for (const e of S.engines) chips.push(["e:" + e, esc($(`[data-engine="${e}"]`).parentElement.textContent.trim().replace(/\d+$/, ""))]);
      if (S.wanted) chips.push(["w", "Asked for"]);
      $(".chips").innerHTML = chips.map(([k, l]) => `<button type="button" class="chip" data-chip="${k}" aria-label="Remove filter ${l}">${l}<svg class="i sm" aria-hidden="true"><use href="#i-x"/></svg></button>`).join("")
        + (chips.length > 1 ? `<button type="button" class="chip clear" data-chip="all">Clear all</button>` : "");

      emptyState(list.length === 0, chips.length > (S.q ? 1 : 0));
      wantedSection();

      const url = new URL(location.href);
      S.q ? url.searchParams.set("q", S.q) : url.searchParams.delete("q");
      S.lang !== "*" ? url.searchParams.set("lang", S.lang) : url.searchParams.delete("lang");
      history.replaceState(null, "", url);
    }

    function emptyState(show, filtered) {
      const box = $("#empty");
      box.hidden = !show;
      if (!show) return;
      const into = S.lang === "*" ? "" : ` into ${langName(S.lang)}`;
      const pitch = !filtered;
      $("[data-empty-title]").textContent = S.q
        ? `No translation of “${S.q}”${into} yet`
        : pitch ? `No translations${into} yet` : "Nothing matches these filters";
      $("[data-empty-text]").textContent = pitch
        ? "You can be the first: the app translates the game with your own AI subscription, you try it in game, and it shows up here. Or ask for it, and you'll hear when someone takes it on."
        : "Try removing a filter, or look in another language.";
      $("[data-empty-ai]").hidden = !pitch;
      $("[data-empty-ask]").hidden = !pitch;
      $("[data-clear]").hidden = pitch;
      const similar = cards.filter(c => S.lang === "*" ? Object.keys(c.stats).length : c.stats[S.lang])
        .sort(sorters.likes).slice(0, 3);
      $("[data-empty-try]").innerHTML = S.q && similar.length
        ? `With a translation${esc(into)}: ` + similar.map(c => `<button type="button" data-try="${esc(c.title)}">${esc(c.title)}</button>`).join(" · ")
        : "";
    }

    function wantedSection() {
      const box = $("#wanted .reqs");
      if (!box) return;
      const rows = $$(".req", box);
      const mine = rows.filter(r => r.dataset.lang === S.lang);
      const shown = (S.lang !== "*" && mine.length ? mine : rows).slice(0, +box.dataset.top || 3);
      for (const r of rows) r.hidden = !shown.includes(r);
      $("#wanted .in-lang").textContent = S.lang !== "*" && mine.length ? ` in ${langName(S.lang)}` : "";
    }

    // events
    $("#q").addEventListener("input", e => { S.q = e.target.value; render(); });
    select.addEventListener("change", e => { S.lang = e.target.value; store.set("lang", S.lang); render(); });
    $("#sort").addEventListener("change", e => { S.sort = e.target.value; render(); });
    document.addEventListener("change", e => {
      const t = e.target;
      if (t.dataset.status) { t.checked ? S.status.add(t.dataset.status) : S.status.delete(t.dataset.status); render(); }
      if (t.dataset.engine) { t.checked ? S.engines.add(t.dataset.engine) : S.engines.delete(t.dataset.engine); render(); }
      if ("wanted" in t.dataset) { S.wanted = t.checked; render(); }
    });
    const filters = $("aside.filters"), shade = $(".drawer-bg"), opener = $("[data-open-filters]");
    const openFilters = open => {
      filters.classList.toggle("open", open);
      shade.hidden = !open;
      if (open) $("#lang").focus(); else opener.focus();
    };
    document.addEventListener("click", e => {
      const t = e.target;
      const view = t.closest("[data-view]");
      if (view) { S.view = view.dataset.view; store.set("view", S.view); render(); }
      const chip = t.closest("[data-chip]");
      if (chip) {
        const k = chip.dataset.chip;
        if (k === "all") { S.q = ""; S.status.clear(); S.engines.clear(); S.wanted = false; $("#q").value = ""; }
        else if (k === "q") { S.q = ""; $("#q").value = ""; }
        else if (k === "w") S.wanted = false;
        else if (k.startsWith("s:")) S.status.delete(k.slice(2));
        else if (k.startsWith("e:")) S.engines.delete(k.slice(2));
        render();
      }
      if (t.closest("[data-clear]")) { S.status.clear(); S.engines.clear(); S.wanted = false; render(); }
      const tryIt = t.closest("[data-try]");
      if (tryIt) { S.q = tryIt.dataset.try; $("#q").value = S.q; render(); }
      if (t.closest("[data-open-filters]")) openFilters(true);
      if (t.closest("[data-close-filters]") || t === shade) openFilters(false);
    });
    document.addEventListener("keydown", e => {
      const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName || "");
      if (e.key === "/" && !typing) { e.preventDefault(); $("#q").focus(); }
      if (e.key === "Escape" && filters.classList.contains("open")) openFilters(false);
    });
    render();
  }

  // ---------------------------------------------------------------- game page: the reader's language first
  function gamePage() {
    const trs = $$(".tr[data-lang]");
    if (!trs.length) return;
    const has = tag => trs.some(t => t.dataset.lang === tag);
    const names = Object.fromEntries(trs.map(t => [t.dataset.lang, [t.dataset.lang, t.dataset.lang]]));
    const lang = pickLanguage(names, has);
    const mine = trs.filter(t => t.dataset.lang === lang);
    const heading = $(".trs h2");
    for (const t of mine.reverse()) { t.classList.add("mine"); heading.after(t); }
  }

  // ---------------------------------------------------------------- requests: tabs by language
  function requestsPage() {
    const rows = $$(".req[data-lang]");
    const tabs = $$("[data-req-tab]");
    if (!tabs.length) return;
    const names = Object.fromEntries(rows.map(r => [r.dataset.lang, [r.dataset.lang, r.dataset.lang]]));
    const show = tag => {
      for (const b of tabs) b.setAttribute("aria-pressed", String(b.dataset.reqTab === tag));
      for (const r of rows) r.hidden = tag !== "*" && r.dataset.lang !== tag;
    };
    show(pickLanguage(names, tag => rows.some(r => r.dataset.lang === tag)));
    for (const b of tabs) b.addEventListener("click", () => show(b.dataset.reqTab));
  }
})();
