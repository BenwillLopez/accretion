// Accretion store. Loads data/index.json once and filters in memory; an app's full
// details come from its shard (data/apps/NNN.json) when its page opens.
// Routes: #/ (with ?q=&c=&s=&src=&fit=), #/app/<bundle id>, #/sources, #/saved
(() => {
  "use strict";

  const PAGE = 60;
  const SHELF = 20; // apps per home section: pages of LIST rows, swiped sideways
  const LIST = 5; // rows per page
  const CATEGORY_NAMES = {
    games: "Games", utilities: "Utilities", "photo-video": "Photo & Video", entertainment: "Entertainment",
    social: "Social", lifestyle: "Lifestyle", developer: "Developer", other: "Other",
  };
  const SOURCE_URL = {
    full: "https://getaccretion.github.io/source.json",
    core: "https://getaccretion.github.io/curated.json",
  };
  const QR_LIB = "https://cdnjs.cloudflare.com/ajax/libs/qrcode-generator/1.4.4/qrcode.min.js";

  const $ = (id) => document.getElementById(id);
  const state = { apps: [], byId: new Map(), sources: [], shards: 128, list: [], shown: PAGE, f: {}, trend: new Map(), from: null, support: {} };
  const shardCache = new Map();

  // ---- small helpers ------------------------------------------------------------
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid);
    return el;
  }
  const safeUrl = (u) => (typeof u === "string" && /^https:\/\//i.test(u) ? u : null);
  const fmt = (n) => Number(n || 0).toLocaleString("en-US");
  const DAY = 864e5;
  const dayMs = (d) => Date.parse(`${d}T00:00:00Z`);
  function bytes(n) {
    if (!n) return "–";
    const u = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
  }
  function ago(day) {
    const d = dayMs(day);
    if (!d) return day || "";
    const days = Math.floor((Date.now() - d) / DAY);
    if (days <= 0) return "today";
    if (days === 1) return "yesterday";
    if (days < 30) return `${days}d ago`;
    if (days < 365) return `${Math.floor(days / 30)}mo ago`;
    return `${Math.floor(days / 365)}y ago`;
  }
  function fnv1a(text) {
    let x = 0x811c9dc5;
    for (const byte of new TextEncoder().encode(text)) {
      x ^= byte;
      x = Math.imul(x, 0x01000193) >>> 0;
    }
    return x >>> 0;
  }
  const verParts = (v) => (String(v || "").match(/\d+/g) || []).slice(0, 4).map(Number);
  function verCmp(a, b) {
    const x = verParts(a), y = verParts(b);
    for (let i = 0; i < Math.max(x.length, y.length); i++) {
      const d = (x[i] || 0) - (y[i] || 0);
      if (d) return d;
    }
    return 0;
  }
  function icon(url, name, cls) {
    const src = safeUrl(url);
    const ph = () => h("div", { class: `${cls} ph`, "aria-hidden": "true" }, (name || "?").trim().charAt(0).toUpperCase());
    if (!src) return ph();
    const img = h("img", { class: cls, src, alt: "", loading: "lazy", decoding: "async", referrerpolicy: "no-referrer" });
    img.addEventListener("error", () => img.replaceWith(ph()), { once: true });
    return img;
  }
  let toastTimer;
  function toast(msg) {
    const t = $("toast");
    t.textContent = msg;
    t.classList.add("on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("on"), 1800);
  }
  async function copy(text, label) {
    try {
      await navigator.clipboard.writeText(text);
      toast(label || "Copied");
    } catch {
      window.prompt("Copy this link:", text);
    }
  }
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };

  // ---- device + saved apps -----------------------------------------------------
  const iosMatch = navigator.userAgent.match(/(?:iPhone|iPad|iPod)[^)]*? OS (\d+)_(\d+)(?:_(\d+))?/);
  const deviceIOS = iosMatch ? `${iosMatch[1]}.${iosMatch[2]}${iosMatch[3] ? `.${iosMatch[3]}` : ""}` : null;
  const fits = (a) => !deviceIOS || !a.m || verCmp(a.m, deviceIOS) <= 0;

  let saved = store.get("acc.saved", {});          // bundle id -> version when saved
  const lastVisit = store.get("acc.visit", null);  // YYYY-MM-DD of the previous visit
  store.set("acc.visit", new Date().toISOString().slice(0, 10));
  const isNew = (a) => !a.u && Date.now() - dayMs(a.f) < 30 * DAY;
  // apps whose source gives no real release date sort as oldest and never count as fresh
  const when = (a) => (a.u ? "" : a.t);
  const since = (a) => (a.u ? "date unknown" : ago(a.t));
  const hasUpdate = (a) => saved[a.i] !== undefined && saved[a.i] !== a.v;
  function toggleSave(a) {
    if (saved[a.i] !== undefined) {
      delete saved[a.i];
      toast("Removed from saved");
    } else {
      saved[a.i] = a.v;
      toast("Saved. You'll see when it updates.");
    }
    store.set("acc.saved", saved);
    updateSavedCount();
  }
  function updateSavedCount() {
    const ids = Object.keys(saved).filter((id) => state.byId.has(id));
    const updates = ids.filter((id) => hasUpdate(state.byId.get(id))).length;
    const pill = $("saved-n");
    pill.hidden = !ids.length;
    pill.textContent = updates ? `${updates} new` : String(ids.length);
    pill.classList.toggle("hot", updates > 0);
  }

  // ---- routing + filters ---------------------------------------------------------
  function parse() {
    const raw = location.hash.replace(/^#/, "") || "/";
    const [pathPart, query = ""] = raw.split("?");
    const p = new URLSearchParams(query);
    const app = pathPart.match(/^\/app\/(.+)$/);
    if (app) return { view: "app", bid: decodeURIComponent(app[1]) };
    if (pathPart === "/sources") return { view: "sources" };
    if (pathPart === "/support") return { view: "support" };
    if (pathPart === "/sign") return { view: "sign" };
    if (/^\/(feed|u\/.+|notifications|mod|me|signin)$/.test(pathPart)) return { view: "social", path: pathPart, params: Object.fromEntries(p) };
    return {
      view: "home",
      saved: pathPart === "/saved",
      q: p.get("q") || "",
      c: p.get("c") || "all",
      s: p.get("s") || "updated",
      src: p.has("src") ? Number(p.get("src")) : null,
      fit: p.has("fit") ? p.get("fit") === "1" : Boolean(deviceIOS),
      l: p.get("l") === "1", // full list (See all), without the home sections
    };
  }
  function homeHash(f) {
    const p = new URLSearchParams();
    if (f.q) p.set("q", f.q);
    if (f.c && f.c !== "all") p.set("c", f.c);
    if (f.s && f.s !== "updated") p.set("s", f.s);
    if (f.src !== null && f.src !== undefined) p.set("src", f.src);
    if (deviceIOS && !f.fit) p.set("fit", "0");
    if (f.l) p.set("l", "1");
    const qs = p.toString();
    return `#${f.saved ? "/saved" : "/"}${qs ? `?${qs}` : ""}`;
  }
  function go(partial, { replace = false } = {}) {
    const next = homeHash({ ...state.f, ...partial });
    if (replace) {
      history.replaceState(null, "", next);
      route();
    } else if (location.hash !== next) {
      location.hash = next;
    } else {
      route();
    }
  }

  function route() {
    const r = parse();
    for (const a of document.querySelectorAll("[data-nav]")) {
      const on = (r.view === "home" && !r.saved && a.dataset.nav === "home") || (r.view === "sources" && a.dataset.nav === "sources") || (r.view === "home" && r.saved && a.dataset.nav === "saved") || (r.view === "social" && r.path === "/feed" && a.dataset.nav === "feed") || (r.view === "support" && a.dataset.nav === "support");
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    }
    $("home").hidden = r.view !== "home";
    $("detail").hidden = r.view !== "app";
    $("sources").hidden = r.view !== "sources";
    $("support").hidden = r.view !== "support";
    $("sign").hidden = r.view !== "sign";
    $("social").hidden = r.view !== "social";
    if (r.view === "social") {
      window.scrollTo(0, 0);
      document.dispatchEvent(new CustomEvent("acc:route", { detail: r }));
      return;
    }
    if (r.view === "app") return openApp(r.bid);
    if (r.view === "sources") {
      document.title = "Sources · Accretion";
      window.scrollTo(0, 0);
      return renderSources();
    }
    if (r.view === "sign") {
      document.title = "Sign your own apps · Accretion";
      window.scrollTo(0, 0);
      return renderSign();
    }
    if (r.view === "support") {
      document.title = "Support · Accretion";
      window.scrollTo(0, 0);
      return renderSupport();
    }
    document.title = r.saved ? "Saved · Accretion" : "Accretion";
    const changed = JSON.stringify(r) !== JSON.stringify(state.f);
    const leavingHome = changed && state.f.view === "home" && defaultView(state.f) && !defaultView(r) && !r.q;
    state.f = r;
    if ($("q").value !== r.q && document.activeElement !== $("q")) $("q").value = r.q;
    $("sort").value = r.s;
    if (changed || !state.list.length) apply();
    if (leavingHome && state.scroll === undefined) window.scrollTo(0, 0);
    if (state.scroll !== undefined) {
      window.scrollTo(0, state.scroll);
      state.scroll = undefined;
    }
  }

  // ---- demand: anonymous counts (sent by social.js; nothing leaves the page without it) ----
  const counted = new Set();
  function track(kind, app, q) {
    const key = `${kind}|${app || q}`;
    if (counted.has(key)) return;
    counted.add(key);
    document.dispatchEvent(new CustomEvent("acc:track", { detail: { kind, app: app || null, q: q || null } }));
  }
  let missTimer;
  function trackMiss(q) {
    clearTimeout(missTimer);
    missTimer = setTimeout(() => { if (state.f.q === q && !state.list.length) track("miss", null, q); }, 1500);
  }
  const trendScore = (a) => state.trend.get(a.i) || 0;
  // a.p: how many sources carry the app, plus a boost for the apps guides and communities name
  // most (popular.txt). Live store searches add on top; the square root keeps a few visits from
  // outranking Spotify, while steady demand still climbs the list.
  const popScore = (a) => (a.p || 0) + 4 * Math.sqrt(trendScore(a));

  // ---- closest working apps --------------------------------------------------------
  // When an app has no working download (or a search finds nothing), point to the apps that
  // are most likely what the person wanted: same name words, same maker, same category.
  const NOISE = new Set("the app apps for ios ipa and by mod mods hack hacked tweak tweaked patched beta free premium plus pro lite official unlocked cracked paid edition version new client mobile com org net io www".split(" "));
  function words(text) {
    return (text || "")
      .toLowerCase()
      .replace(/\(.*?\)|\[.*?\]/g, " ")
      .split(/[^a-z0-9]+/)
      .filter((w) => w.length > 1 && !NOISE.has(w) && !/^v?\d+$/.test(w));
  }
  const appWords = (a) => (a._w ||= new Set([...words(a.n), ...words(a.i.replace(/\./g, " "))]));
  function closest({ name = "", bid = "", dev = "", cat = "" }, n = 6) {
    const want = [...new Set([...words(name), ...words(bid.replace(/\./g, " "))])];
    const vendor = bid.split(".").slice(0, 2).join(".").toLowerCase();
    const scored = [];
    for (const a of state.apps) {
      if (a.i === bid) continue;
      const have = appWords(a);
      let hit = 0;
      for (const w of want) {
        if (have.has(w)) hit += 1;
        else if (w.length >= 4 && [...have].some((x) => x.length >= 4 && (x.startsWith(w) || w.startsWith(x)))) hit += 0.6;
      }
      let score = want.length ? (hit / want.length) * 10 : 0;
      if (vendor.includes(".") && a.i.toLowerCase().startsWith(`${vendor}.`)) score += 4;
      if (dev && a.d === dev) score += 2;
      if (cat && a.c === cat && cat !== "other") score += 1;
      if (score >= 4) scored.push([score + popScore(a) / 8, a]); // popular apps first among equals
    }
    return scored.sort((x, y) => y[0] - x[0]).slice(0, n).map((x) => x[1]);
  }
  let goneData;
  const loadGone = () => (goneData ||= fetch("data/gone.json").then((r) => (r.ok ? r.json() : {})).catch(() => ({})));

  // ---- home: shelves + grid -----------------------------------------------------
  const defaultView = (f) => !f.q && f.c === "all" && f.src === null && !f.saved && !f.l;
  const LIST_TITLES = { popular: "Most popular", updated: "Recently updated", new: "Newest apps", name: "All apps A–Z", size: "Largest apps" };

  function apply() {
    const f = state.f;
    const words = f.q.toLowerCase().split(/\s+/).filter(Boolean);
    let list = state.apps.filter(
      (a) =>
        (f.c === "all" || a.c === f.c) &&
        (f.src === null || a.o === f.src) &&
        (!f.saved || saved[a.i] !== undefined) &&
        (!f.fit || fits(a)) &&
        words.every((w) => a._s.includes(w)),
    );
    const by = {
      updated: (a, b) => (when(a) < when(b) ? 1 : when(a) > when(b) ? -1 : a.n.localeCompare(b.n)),
      new: (a, b) => (a.f < b.f ? 1 : a.f > b.f ? -1 : a.n.localeCompare(b.n)),
      name: (a, b) => a.n.localeCompare(b.n, undefined, { sensitivity: "base" }),
      size: (a, b) => (b.z || 0) - (a.z || 0),
      popular: (a, b) => popScore(b) - popScore(a) || (a.t < b.t ? 1 : -1),
    }[f.s] || ((a, b) => (a.t < b.t ? 1 : -1));
    if (f.saved) {
      list.sort((a, b) => hasUpdate(b) - hasUpdate(a) || by(a, b));
    } else if (words.length) {
      const rank = (a) => (a.n.toLowerCase().startsWith(words[0]) ? 0 : a.n.toLowerCase().includes(words[0]) ? 1 : 2);
      list.sort((a, b) => rank(a) - rank(b) || popScore(b) - popScore(a) || by(a, b));
    } else {
      list.sort(by);
    }
    state.list = list;
    state.shown = PAGE;
    if (words.length && !list.length && !f.saved && f.src === null) trackMiss(f.q);

    const def = defaultView(f);
    $("hero").hidden = !def;
    renderShelves(def);
    $("all-title").textContent = f.saved
      ? "Saved apps"
      : f.src !== null
        ? (state.sources[f.src] || {}).name || "Source"
        : f.q
          ? "Results"
          : f.c !== "all"
            ? CATEGORY_NAMES[f.c] || "Apps"
            : f.l
              ? LIST_TITLES[f.s] || "All apps"
              : "All apps";
    for (const el of $("cats").children) el.setAttribute("aria-selected", String(el.dataset.cat === f.c));
    renderFit();
    renderGrid();
  }

  function card(a) {
    const badges = [];
    if (hasUpdate(a)) badges.push(h("em", { class: "badge hot" }, "update"));
    else if (isNew(a)) badges.push(h("em", { class: "badge" }, "new"));
    return h(
      "a",
      { class: "card", href: `#/app/${encodeURIComponent(a.i)}`, onclick: () => { state.scroll = window.scrollY; state.from = state.f.q ? "search" : null; } },
      icon(a.ic, a.n, "icon"),
      h(
        "div",
        { class: "card-body" },
        h("div", { class: "card-name" }, h("span", {}, a.n), badges),
        h("div", { class: "card-dev" }, a.d),
        h("div", { class: "card-meta" }, h("span", { class: "v" }, `v${a.v}`), h("span", {}, since(a)), a.z ? h("span", {}, bytes(a.z)) : null),
      ),
    );
  }

  function renderGrid() {
    const f = state.f;
    $("grid").replaceChildren(...state.list.slice(0, state.shown).map(card));
    const bits = [`${fmt(state.list.length)} ${state.list.length === 1 ? "app" : "apps"}`];
    if (f.c !== "all") bits.push(`in ${CATEGORY_NAMES[f.c]}`);
    if (f.q) bits.push(`matching "${f.q}"`);
    $("count").textContent = bits.join(" ");
    $("more").hidden = state.shown >= state.list.length;
    const empty = $("empty");
    empty.hidden = state.list.length > 0;
    const near = !state.list.length && f.q && !f.saved ? closest({ name: f.q }) : [];
    $("closest").hidden = !near.length;
    $("closest").replaceChildren(near.length ? shelf("Closest matches", "apps that work", near, null) : "");
    empty.textContent = f.saved
      ? "Nothing saved yet. Open any app and tap Save to get a heads-up when it updates."
      : near.length
        ? `Nothing named "${f.q}". These are the closest apps that work:`
        : "No apps match. Try a shorter word, another category, or turn off the iOS filter.";
    const note = $("filter-note");
    const hidden = f.fit && deviceIOS ? state.apps.filter((a) => !fits(a)).length : 0;
    note.hidden = !(f.src !== null || hidden);
    note.replaceChildren(
      f.src !== null ? h("span", {}, "Showing one source. ", h("a", { href: homeHash({ ...f, src: null }) }, "Show all sources")) : "",
      hidden && f.src === null ? h("span", {}, `${fmt(hidden)} apps that need a newer iOS than ${deviceIOS} are hidden.`) : "",
    );
  }

  function showMore() {
    const from = state.shown;
    state.shown += PAGE;
    $("grid").append(...state.list.slice(from, state.shown).map(card));
    $("more").hidden = state.shown >= state.list.length;
  }

  function renderFit() {
    const b = $("fit");
    if (!deviceIOS) return;
    b.hidden = false;
    b.setAttribute("aria-pressed", String(state.f.fit));
    b.textContent = state.f.fit ? `Works on iOS ${deviceIOS} ✓` : `Show only apps for iOS ${deviceIOS}`;
  }

  // home and app-page sections: a short vertical list (top 5) with a link to the full list
  function listRow(a, rank) {
    return h(
      "li",
      {},
      h(
        "a",
        { class: "row", href: `#/app/${encodeURIComponent(a.i)}`, onclick: () => { state.scroll = window.scrollY; } },
        rank ? h("span", { class: "row-rank" }, String(rank)) : null,
        icon(a.ic, a.n, "icon row-icon"),
        h(
          "span",
          { class: "row-body" },
          h("span", { class: "row-name" }, a.n),
          h("span", { class: "row-meta" }, [`v${a.v}`, CATEGORY_NAMES[a.c], since(a)].filter(Boolean).join(" · ")),
        ),
        h("span", { class: "row-go", "aria-hidden": "true" }, "›"),
      ),
    );
  }

  function shelf(title, note, apps, seeAll, { ranked = false } = {}) {
    if (!apps.length) return null;
    const list = apps.slice(0, SHELF);
    const pages = [];
    for (let i = 0; i < list.length; i += LIST) pages.push(list.slice(i, i + LIST));
    const scroller = h(
      "div",
      { class: `shelf-pages${pages.length > 1 ? " multi" : ""}` },
      pages.map((page, p) => h("ol", { class: "shelf-list", start: String(p * LIST + 1) }, page.map((a, i) => listRow(a, ranked ? p * LIST + i + 1 : 0)))),
    );
    const step = (dir) => scroller.scrollBy({ left: dir * scroller.clientWidth * 0.9, behavior: "smooth" });
    const arrows = pages.length > 1
      ? h("span", { class: "shelf-nav" },
          h("button", { type: "button", "aria-label": `Previous ${title}`, onclick: () => step(-1) }, "‹"),
          h("button", { type: "button", "aria-label": `More ${title}`, onclick: () => step(1) }, "›"))
      : null;
    return h(
      "section",
      { class: "shelf" },
      h("div", { class: "shelf-head" }, h("h2", {}, title, note ? h("span", {}, note) : null), h("span", { class: "shelf-tools" }, arrows, seeAll ? h("a", { href: seeAll }, "See all") : null)),
      scroller,
    );
  }

  function renderShelves(show) {
    const box = $("shelves");
    if (!show) return box.replaceChildren();
    const pool = state.apps.filter((a) => !state.f.fit || fits(a));
    const byUpdated = [...pool].sort((a, b) => (when(a) < when(b) ? 1 : -1));
    const byNew = [...pool].sort((a, b) => (a.f < b.f ? 1 : -1)).filter(isNew);
    const core = byUpdated.filter((a) => (state.sources[a.o] || {}).core);
    const savedUpd = pool.filter(hasUpdate);
    const today = new Date().toISOString().slice(0, 10);
    const fresh = byUpdated.filter((a) => !a.u && (a.t >= today || Date.now() - dayMs(a.t) < 2 * DAY));
    const socialShelves = h("div", { id: "social-shelves" });
    const popular = pool.filter((a) => popScore(a) > 0).sort((a, b) => popScore(b) - popScore(a) || (a.t < b.t ? 1 : -1));
    box.replaceChildren(
      ...[
        shelf("Most popular", "this week", popular, homeHash({ ...state.f, s: "popular", l: true }), { ranked: true }),
        shelf("Updates for your saved apps", `${savedUpd.length}`, savedUpd.slice(0, SHELF), "#/saved"),
        shelf("Fresh today", `${fmt(fresh.length)} updated`, fresh.slice(0, SHELF), homeHash({ ...state.f, s: "updated", l: true })),
        shelf("New this month", `${fmt(byNew.length)} apps`, byNew.slice(0, SHELF), homeHash({ ...state.f, s: "new", l: true })),
        shelf("From Accretion Core", "hand-picked sources", core.slice(0, SHELF), null),
        shelf("Games", "just updated", byUpdated.filter((a) => a.c === "games").slice(0, SHELF), homeHash({ ...state.f, c: "games" })),
        socialShelves,
        shelf("Utilities", "just updated", byUpdated.filter((a) => a.c === "utilities").slice(0, SHELF), homeHash({ ...state.f, c: "utilities" })),
      ].filter(Boolean),
    );
    document.dispatchEvent(new CustomEvent("acc:home", { detail: { mount: socialShelves } }));
  }

  function buildChips() {
    const counts = { all: state.apps.length };
    for (const a of state.apps) counts[a.c] = (counts[a.c] || 0) + 1;
    const order = ["all", ...Object.keys(CATEGORY_NAMES).filter((c) => counts[c]).sort((x, y) => (x === "other") - (y === "other") || counts[y] - counts[x])];
    $("cats").replaceChildren(
      ...order.map((c) =>
        h(
          "button",
          { class: "chip", type: "button", role: "tab", "data-cat": c, "aria-selected": "false", onclick: () => go({ c }) },
          c === "all" ? "All" : CATEGORY_NAMES[c],
          h("span", {}, fmt(counts[c])),
        ),
      ),
    );
  }

  // ---- sources directory ----------------------------------------------------------
  function renderSources() {
    const counts = new Map();
    for (const a of state.apps) counts.set(a.o, (counts.get(a.o) || 0) + 1);
    const rows = state.sources
      .map((s, i) => ({ ...s, i, n: counts.get(i) || 0 }))
      .sort((a, b) => b.core - a.core || b.n - a.n || a.name.localeCompare(b.name));
    $("sources").replaceChildren(
      h("div", { class: "view-head" }, h("h1", { class: "view-title" }, "Sources"), h("p", { class: "muted" }, `${fmt(rows.length)} sources feed Accretion. "Apps" counts the apps where that source has the newest version.`)),
      h(
        "ul",
        { class: "src-list" },
        rows.map((s) =>
          h(
            "li",
            {},
            h("div", { class: "src-main" }, h("span", { class: "src-name" }, s.name, s.core ? h("em", { class: "badge core" }, "core") : null), h("code", { class: "src-url" }, s.url)),
            h("span", { class: "src-n" }, h("b", {}, fmt(s.n)), " apps"),
            h(
              "div",
              { class: "src-act" },
              s.n ? h("a", { class: "btn", href: homeHash({ q: "", c: "all", s: "updated", src: s.i, fit: state.f.fit, saved: false }) }, "Browse") : null,
              h("button", { class: "btn ghost", type: "button", onclick: () => copy(s.url, "Source link copied") }, "Copy"),
            ),
          ),
        ),
      ),
    );
  }

  // ---- install links for on-device signers -------------------------------------------------
  // Feather takes the plain https link after the prefix (see its FeatherApp.swift URL handler).
  const featherInstall = (url) => `feather://install/${url}`;
  const featherSource = (url) => `feather://source/${url}`;

  function installButtons(url) {
    return [
      h("a", { class: "btn primary", href: featherInstall(url) }, "Sign & install in Feather"),
      h("a", { class: "btn", href: `altstore://install?url=${encodeURIComponent(url)}` }, "AltStore"),
      h("a", { class: "btn", href: `sidestore://install?url=${encodeURIComponent(url)}` }, "SideStore"),
      h("a", { class: "btn", href: `apple-magnifier://install?url=${encodeURIComponent(url)}` }, "TrollStore"),
      h("a", { class: "btn ghost", href: url, rel: "nofollow noopener" }, "Download"),
    ];
  }

  // Sign your own apps: certificate -> Feather -> any app -> customize. Everything happens on the
  // device; the certificate import builds Feather's own link in the browser and uploads nothing.
  const FEATHER_ID = "kh.crysalis.feather";
  // paths as they appear on Feather's signing screen (checked against its source, 2026-09)
  const CUSTOMIZE = [
    ["New app name", "Name", "Emojis work too."],
    ["New bundle ID (install twice)", "Identifier", "Some apps lose their login or data when duplicated."],
    ["New version number", "Version", ""],
    ["Custom app icon", "Customization → Choose from Photos / Choose from Files", ""],
    ["Install on an older iOS", "Advanced → Properties → Minimum Requirement", "Lowers the iOS version the app asks for. It may still crash if it really needs newer iOS."],
    ["Browse the app's files", "Advanced → Properties → File Sharing / iTunes File Sharing", "Shows its Documents folder in the Files app."],
    ["Remove PlugIns", "Advanced → Modify → Frameworks & PlugIns", "Removing extensions often fixes apps that won't sign."],
    ["Inject tweaks (.dylib, .deb)", "Advanced → Modify → Tweaks", "Can inject into extensions too."],
    ["iPad full screen, ProMotion, Game Mode", "Advanced → Properties → App Features", ""],
  ];

  const b64 = (buf) => {
    let bin = "";
    const bytes = new Uint8Array(buf);
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  };

  function certImport() {
    const p12 = h("input", { type: "file", id: "imp-p12", accept: ".p12,application/x-pkcs12" });
    const prov = h("input", { type: "file", id: "imp-prov", accept: ".mobileprovision" });
    const pass = h("input", { class: "input", type: "password", id: "imp-pass", placeholder: "Certificate password (if it has one)", autocomplete: "off" });
    const msg = h("p", { class: "muted small", "aria-live": "polite" });
    const go = h("button", { class: "btn primary", type: "submit" }, "Add to Feather");
    const form = h("form", { class: "card-form imp" },
      h("label", {}, h("span", {}, "Certificate (.p12)"), p12),
      h("label", {}, h("span", {}, "Profile (.mobileprovision)"), prov),
      h("label", {}, h("span", {}, "Password"), pass),
      h("div", { class: "row" }, go),
      msg,
      h("p", { class: "muted small" }, "Your files stay on this device: the page only hands them to Feather. Nothing is uploaded to Accretion or anyone else."));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const [a, b] = [p12.files[0], prov.files[0]];
      if (!a || !b) { msg.textContent = "Pick both files first: the .p12 and the .mobileprovision."; return; }
      try {
        const [ca, cb] = await Promise.all([a.arrayBuffer(), b.arrayBuffer()]);
        const pw = b64(new TextEncoder().encode(pass.value));
        const link = `feather://import-certificate?p12=${encodeURIComponent(b64(ca))}&mobileprovision=${encodeURIComponent(b64(cb))}&password=${encodeURIComponent(pw)}`;
        form.dataset.link = link; // lets the browser tests read what Feather receives
        msg.textContent = "Opening Feather…";
        window.location.href = link;
      } catch {
        msg.textContent = "Couldn't read those files. Try picking them again.";
      }
    });
    return form;
  }

  function linkInstaller() {
    const input = h("input", { class: "input", id: "sign-url", type: "url", inputmode: "url", placeholder: "https://…/App.ipa", autocomplete: "off", spellcheck: "false" });
    const out = h("div", { class: "sign-out", "aria-live": "polite" });
    const show = () => {
      const url = safeUrl(input.value.trim());
      if (!url) {
        out.replaceChildren(input.value.trim() ? h("p", { class: "warn" }, "That isn't an https link. Use the direct link to the .ipa file.") : "");
        return;
      }
      const name = decodeURIComponent(url.split("?")[0].split("/").pop() || "").replace(/\.t?ipa$/i, "").replace(/[_+.-]+/g, " ").trim();
      const near = name ? closest({ name }, 4) : [];
      out.replaceChildren(...[
        h("div", { class: "actions" }, installButtons(url)),
        /\.t?ipa(\?|$)/i.test(url) ? null : h("p", { class: "muted small" }, "This link doesn't end in .ipa. If it opens a web page instead of the file, the installers can't use it."),
        near.length ? shelf("Already in Accretion", "checked links, kept up to date", near, null) : null,
      ].filter(Boolean));
    };
    input.addEventListener("input", show);
    const pre = new URLSearchParams(location.hash.split("?")[1] || "").get("url");
    if (pre) { input.value = pre; setTimeout(show); }
    return [h("label", { class: "sign-field" }, h("span", {}, "Paste an IPA link"), input), out];
  }

  function renderSign() {
    const feather = state.byId.get(FEATHER_ID);
    const step = (n, title, ...kids) => h("section", { class: "sec sign-step" }, h("h2", {}, h("span", { class: "step-n" }, String(n)), title), ...kids);
    $("sign").replaceChildren(...[
      h("div", { class: "view-head" },
        h("h1", { class: "view-title" }, "Sign your own apps"),
        h("p", { class: "muted" }, "Install any app on your iPhone, even one that isn't in Accretion yet: a tweaked YouTube the day it drops, or your own IPA. No computer, no 7-day limit. Feather signs it on your phone with your certificate.")),
      step(1, "Get a certificate",
        h("p", { class: "muted" }, "A paid certificate (a .p12 file, a .mobileprovision file and a password) installs apps for about a year without a computer."),
        certs().length
          ? h("div", {},
              h("ul", { class: "cert-list" }, certs().map((c) => h("li", {},
                h("div", {}, h("b", {}, c.name), c.note ? h("span", { class: "muted small" }, c.note) : null),
                h("a", { class: "btn", href: safeUrl(c.url), target: "_blank", rel: "sponsored noopener" }, "Get certificate")))),
              h("p", { class: "muted small" }, "Affiliate links: Accretion earns a commission, at no extra cost to you."))
          : h("p", { class: "muted small" }, "Pick a seller that replaces or refunds certificates Apple revokes."),
        h("p", { class: "muted small" }, "Free alternative: AltStore or SideStore with your own Apple ID (needs a computer once, apps refresh every 7 days).")),
      step(2, "Add it to Feather",
        h("p", {}, feather
          ? h("a", { class: "btn", href: `#/app/${encodeURIComponent(FEATHER_ID)}` }, "Get Feather")
          : null,
          h("span", { class: "muted small" }, feather ? " Free and open source. Most certificate sellers also give you a signed copy." : "Most certificate sellers give you a signed copy of Feather.")),
        h("p", { class: "muted" }, "Then add your certificate in one tap:"),
        certImport(),
        h("p", { class: "muted small" }, "Or in Feather: Settings → Certificates → + and pick the same files.")),
      step(3, "Pick an app",
        h("p", { class: "muted" }, "From Accretion: open any app and tap Feather. ", h("a", { href: "#/" }, "Browse apps"), " or search above."),
        ...linkInstaller(),
        h("p", { class: "muted small" }, "File already on your iPhone? Open it from Files or Safari downloads, tap Share and pick Feather.")),
      step(4, "Customize before installing",
        h("p", { class: "muted" }, "Feather opens the app's signing screen. Everything below is optional:"),
        h("ul", { class: "custom-list" }, CUSTOMIZE.map(([what, where, note]) => h("li", {},
          h("b", {}, what),
          h("span", { class: "where" }, where),
          note ? h("span", { class: "muted small" }, note) : null))),
        h("p", { class: "muted small" }, "Then tap Start Signing. With Install After Signing on (Advanced → Properties → Post Signing), it installs right away.")),
      h("section", { class: "sec" },
        h("h2", {}, "If something goes wrong"),
        h("dl", { class: "faq" },
          h("dt", {}, "The app won't open after installing"),
          h("dd", {}, "Your certificate may be revoked. Check its status in Feather (Settings → Certificates); sellers usually replace revoked ones."),
          h("dt", {}, "\"Redirected to a host outside the allowed list\" (iOSGods app)"),
          h("dd", {}, "The iOSGods signer only takes links from certain hosts. Download the IPA instead and pick it with \"Tap to select .IPA file\", or use Feather, which follows any link."),
          h("dt", {}, "It fails to sign"),
          h("dd", {}, "Remove the PlugIns (Advanced → Modify → Frameworks & PlugIns) and try again."))),
    ].filter(Boolean));
  }

  // ---- support: donations, supporter badge, signing certificates (support.json) -------------
  const certs = () => (state.support.certificates || []).filter((c) => c && c.name && safeUrl(c.url));
  const wallets = () => (state.support.crypto || []).filter((w) => w && w.name && w.address);
  const kofi = () => safeUrl(state.support.kofi || "");
  const hasSupport = () => Boolean(kofi() || wallets().length || certs().length);

  function renderSupport() {
    const donate = kofi() || wallets().length;
    $("support").replaceChildren(...[
      h("div", { class: "view-head" },
        h("h1", { class: "view-title" }, "Support Accretion"),
        h("p", { class: "muted" }, "Accretion is free and has no ads. If it saves you time, you can help keep it running.")),
      donate
        ? h("section", { class: "sec support-card" },
            h("h2", {}, "Donate"),
            kofi() ? h("p", {}, h("a", { class: "btn primary", href: kofi(), target: "_blank", rel: "noopener" }, "♥ Donate on Ko-fi")) : null,
            wallets().length
              ? h("ul", { class: "wallets" }, wallets().map((w) => h("li", {},
                  h("b", {}, w.name),
                  h("code", {}, w.address),
                  h("button", { class: "btn ghost", type: "button", onclick: () => copy(w.address, `${w.name} address copied`) }, "Copy"))))
              : null,
            h("p", { class: "muted small" }, h("em", { class: "badge supporter" }, "♥ supporter"), " Supporters get this badge on their profile, posts and comments. Add your Accretion username to the Ko-fi message, or send it after a crypto donation, and it's added within a day."))
        : null,
      certs().length
        ? h("section", { class: "sec support-card" },
            h("h2", {}, "Signing certificates"),
            h("p", { class: "muted" }, "A paid certificate installs apps from your iPhone for a year, with no computer and no weekly refresh."),
            h("ul", { class: "cert-list" }, certs().map((c) => h("li", {},
              h("div", {}, h("b", {}, c.name), c.note ? h("span", { class: "muted small" }, c.note) : null),
              h("a", { class: "btn", href: safeUrl(c.url), target: "_blank", rel: "sponsored noopener" }, "Get certificate")))),
            h("p", { class: "muted small" }, "Affiliate links: Accretion earns a commission when you buy, at no extra cost to you."))
        : null,
      !hasSupport() ? h("p", { class: "empty" }, "Support options are coming soon.") : null,
    ].filter(Boolean));
  }

  function certLine() {
    if (!certs().length) return null;
    const links = [];
    certs().forEach((c, i) => {
      if (i) links.push(" · ");
      links.push(h("a", { href: safeUrl(c.url), target: "_blank", rel: "sponsored noopener" }, c.name));
    });
    return h("p", { class: "cert-line" }, "Need a signing certificate? ", ...links, h("span", { class: "muted" }, " · affiliate"));
  }

  // A short screen before a direct IPA download: the download starts by itself after a few
  // seconds (or right away with "Download now"), with certificate offers and donations meanwhile.
  // Only the store's own Download buttons use it; AltStore/SideStore links and the sources stay direct.
  const WAIT = 4;
  function downloadScreen(e, a, url, version) {
    if (!hasSupport() || e.metaKey || e.ctrlKey || e.shiftKey) return; // nothing to show, or a new tab
    e.preventDefault();
    let left = WAIT;
    let timer;
    const go = () => { clearInterval(timer); dlg.close(); window.location.href = url; };
    const count = h("b", {}, String(left));
    const now = h("a", { class: "btn primary", href: url, rel: "nofollow noopener", onclick: (ev) => { ev.preventDefault(); go(); } }, "Download now");
    const offers = certs().length
      ? h("div", { class: "dl-offers" },
          h("p", { class: "dl-label" }, "Install it without a computer"),
          h("ul", { class: "cert-list" }, certs().map((c) => h("li", {},
            h("div", {}, h("b", {}, c.name), c.note ? h("span", { class: "muted small" }, c.note) : null),
            h("a", { class: "btn", href: safeUrl(c.url), target: "_blank", rel: "sponsored noopener", onclick: () => clearInterval(timer) }, "Get certificate")))),
          h("p", { class: "muted small" }, "Affiliate links: Accretion earns a commission, at no extra cost to you."))
      : null;
    const support = kofi() || wallets().length
      ? h("p", { class: "dl-support" }, "Accretion is free and ad-free. ",
          h("a", { href: kofi() || "#/support", target: kofi() ? "_blank" : null, rel: "noopener", onclick: () => { clearInterval(timer); if (!kofi()) dlg.close(); } }, "♥ Support it"))
      : null;
    const dlg = h("dialog", { class: "dl-screen", "aria-labelledby": "dl-title" },
      h("div", { class: "dl-head" },
        icon(a.ic, a.n, "icon"),
        h("div", {},
          h("h2", { id: "dl-title" }, `${a.n}${version ? ` ${version}` : ""}`),
          h("p", { class: "muted", "aria-live": "polite" }, "Your download starts in ", count, " s…"))),
      h("div", { class: "dl-actions" }, now, h("button", { class: "btn ghost", type: "button", onclick: () => { clearInterval(timer); dlg.close(); } }, "Cancel")),
      offers,
      support);
    dlg.addEventListener("close", () => { clearInterval(timer); dlg.remove(); });
    document.body.append(dlg);
    dlg.showModal();
    timer = setInterval(() => {
      left -= 1;
      count.textContent = String(left);
      if (left <= 0) go();
    }, 1000);
  }

  function showSupportLinks() {
    const on = hasSupport();
    $("nav-support").hidden = !on;
    $("nav-support-m").hidden = !on;
    $("foot-support").hidden = !on;
    $("foot-support-sep").hidden = !on;
  }

  // ---- app page ---------------------------------------------------------------------
  async function details(bid) {
    const n = fnv1a(bid) % state.shards;
    if (!shardCache.has(n)) {
      shardCache.set(n, fetch(`data/apps/${String(n).padStart(3, "0")}.json`).then((r) => (r.ok ? r.json() : {})).catch(() => ({})));
    }
    return (await shardCache.get(n))[bid];
  }
  const fact = (label, value) => h("div", {}, h("dt", {}, label), h("dd", {}, value || "–"));
  const shareUrl = (bid) => new URL(`app/${bid}/`, location.href.split("#")[0]).href;
  const desktop = () => window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  async function openApp(bid) {
    const a = state.byId.get(bid);
    const view = $("detail");
    window.scrollTo(0, 0);
    const back = h("a", { class: "btn back", href: homeHash(state.f.view ? state.f : { q: "", c: "all", s: "updated", src: null, fit: Boolean(deviceIOS) }) }, "← Back");
    if (!a) {
      view.replaceChildren(back, h("p", { class: "muted" }, "Looking for the closest working app…"));
      const g = (await loadGone())[bid];
      if (parse().bid !== bid) return;
      const near = closest({ name: g ? g.n : "", bid, dev: g ? g.d : "", cat: g ? g.c : "" }, 8);
      if (g) track("miss", null, g.n);
      document.title = `${g ? g.n : "App"} unavailable · Accretion`;
      view.replaceChildren(
        back,
        h(
          "section",
          { class: "gone" },
          g ? icon(g.ic, g.n, "icon d-icon") : null,
          h("div", {},
            h("h1", { class: "d-name" }, g ? g.n : "App not found"),
            h("p", { class: "muted" }, g
              ? "Every download link for this app is broken right now, so it's hidden until a source fixes it. These are the closest apps that work:"
              : "This app isn't in Accretion anymore. These are the closest apps that work:")),
        ),
        shelf(near.length ? "Closest working apps" : "", null, near, null) || h("p", { class: "empty" }, "Nothing close yet. Try searching for it."),
      );
      return;
    }
    document.title = `${a.n} · Accretion`;
    if (state.from === "search") track("search", a.i);
    state.from = null;
    track("view", a.i);
    view.replaceChildren(back, head(a, null), h("p", { class: "muted" }, "Loading details…"));
    const d = await details(bid);
    if (parse().bid !== bid) return;
    const social = h("div", { id: "social-app" }); // like + rating, under the header
    const comments = h("div", { id: "social-comments" }); // comments, at the very bottom
    view.replaceChildren(back, head(a, d), social, ...body(a, d), comments);
    if (desktop()) addQr(a);
    document.dispatchEvent(new CustomEvent("acc:app", { detail: { app: a, mount: social, comments } }));
  }

  function head(a, d) {
    const latest = d && d.versions && d.versions[0];
    const ipa = latest && safeUrl(latest.url);
    const tint = d && /^[0-9A-F]{6}$/i.test(d.tint || "") ? `#${d.tint}` : null;
    const isSaved = saved[a.i] !== undefined;
    const tooNew = deviceIOS && a.m && !fits(a);
    const installed = () => track("install", a.i);
    const actions = h(
      "div",
      { class: "actions" },
      ipa ? h("a", { class: "btn primary", href: ipa, rel: "nofollow noopener", onclick: (e) => { installed(); downloadScreen(e, a, ipa); } }, "Download IPA") : null,
      ipa ? h("a", { class: "btn", href: `altstore://install?url=${encodeURIComponent(ipa)}`, onclick: installed }, "AltStore") : null,
      ipa ? h("a", { class: "btn", href: `sidestore://install?url=${encodeURIComponent(ipa)}`, onclick: installed }, "SideStore") : null,
      ipa ? h("a", { class: "btn", href: featherInstall(ipa), onclick: installed, title: "Sign and install with your own certificate in Feather" }, "Feather") : null,
      ipa ? h("a", { class: "btn", href: `apple-magnifier://install?url=${encodeURIComponent(ipa)}`, onclick: installed }, "TrollStore") : null,
      h("button", { class: `btn${isSaved ? " on" : ""}`, type: "button", "aria-pressed": String(isSaved), onclick: (e) => { toggleSave(a); const on = saved[a.i] !== undefined; e.currentTarget.classList.toggle("on", on); e.currentTarget.setAttribute("aria-pressed", String(on)); e.currentTarget.textContent = on ? "Saved" : "Save"; } }, isSaved ? "Saved" : "Save"),
      h("button", { class: "btn ghost", type: "button", onclick: () => share(a) }, "Share"),
      ipa ? h("button", { class: "btn ghost", type: "button", onclick: () => copy(ipa, "IPA link copied") }, "Copy IPA link") : null,
    );
    if (isSaved && hasUpdate(a)) {
      saved[a.i] = a.v; // seen now
      store.set("acc.saved", saved);
      updateSavedCount();
    }
    return h(
      "section",
      { class: "d-head", style: tint ? `--tint:${tint}` : null },
      icon(a.ic, a.n, "icon d-icon"),
      h(
        "div",
        { class: "d-main" },
        h("h1", { class: "d-name" }, a.n),
        h("p", { class: "d-dev" }, h("a", { href: homeHash({ q: a.d, c: "all", s: "updated", src: null, fit: state.f.fit, saved: false }) }, a.d)),
        a.s ? h("p", { class: "d-sub" }, a.s) : null,
        tooNew ? h("p", { class: "warn" }, `Needs iOS ${a.m} or later. This device is on ${deviceIOS}.`) : null,
        d ? actions : null,
        d && ipa ? certLine() : null,
        d && ipa ? h("p", { class: "cert-line" }, h("a", { href: "#/sign" }, "How to sign your own apps →")) : null,
      ),
      h("div", { class: "qr", id: "qr", hidden: true }),
    );
  }

  async function share(a) {
    const url = shareUrl(a.i);
    if (navigator.share && !desktop()) {
      try { await navigator.share({ title: a.n, text: `${a.n} on Accretion`, url }); return; } catch { /* cancelled */ }
    }
    copy(url, "Link copied");
  }

  function addQr(a) {
    const box = $("qr");
    if (!box) return;
    const draw = () => {
      if (!window.qrcode) return;
      const qr = window.qrcode(0, "M");
      qr.addData(shareUrl(a.i));
      qr.make();
      box.innerHTML = qr.createSvgTag({ cellSize: 3, margin: 2, scalable: true }); // SVG built by the QR library
      box.append(h("span", {}, "Scan to open on your phone"));
      box.hidden = false;
    };
    if (window.qrcode) return draw();
    const s = document.createElement("script");
    s.src = QR_LIB;
    s.onload = draw;
    document.head.append(s);
  }

  function shot(u) {
    const img = h("img", { src: u, alt: "Screenshot", loading: "lazy", referrerpolicy: "no-referrer" });
    img.addEventListener("error", () => {
      const row = img.parentElement;
      img.remove();
      if (row && !row.children.length) row.closest(".sec").remove();
    }, { once: true });
    return img;
  }

  function body(a, d) {
    if (!d) return [h("p", { class: "muted" }, "Details couldn't load. Check your connection and refresh.")];
    const latest = d.versions[0] || {};
    const src = state.sources[a.o];
    const out = [
      h(
        "dl",
        { class: "facts" },
        fact("Version", latest.v),
        fact("Build", latest.b),
        fact("Released", a.u ? "Unknown (the source gives no date)" : latest.t ? `${latest.t} · ${ago(latest.t)}` : ""),
        fact("Size", bytes(latest.z)),
        fact("Min iOS", latest.min),
        fact("Category", CATEGORY_NAMES[a.c] || a.c),
      ),
    ];
    if (latest.notes) out.push(h("section", { class: "sec" }, h("h2", {}, "What's new"), h("p", { class: "prose" }, latest.notes)));
    const shots = (d.shots || []).map(safeUrl).filter(Boolean);
    if (shots.length) out.push(h("section", { class: "sec" }, h("h2", {}, "Screenshots"), h("div", { class: "shots" }, shots.map(shot))));
    if (d.desc) out.push(h("section", { class: "sec" }, h("h2", {}, "About"), h("p", { class: "prose" }, d.desc)));
    out.push(
      h(
        "section",
        { class: "sec" },
        h("h2", {}, "Versions"),
        h(
          "ul",
          { class: "vers" },
          d.versions.map((v) =>
            h(
              "li",
              {},
              h("span", {}, `v${v.v}${v.b && v.b !== v.v ? ` (${v.b})` : ""}`),
              h("span", { class: "muted" }, `${v.t} · ${bytes(v.z)}${v.min ? ` · iOS ${v.min}+` : ""}`),
              safeUrl(v.url) ? h("a", { href: v.url, rel: "nofollow noopener", onclick: (e) => downloadScreen(e, a, v.url, v.v) }, "Download") : null,
              v.notes && v !== latest ? h("span", { class: "notes" }, v.notes) : null,
            ),
          ),
        ),
      ),
    );
    const ents = (d.perms && d.perms.entitlements) || [];
    const priv = Object.keys((d.perms && d.perms.privacy) || {});
    if (ents.length || priv.length) {
      out.push(h("section", { class: "sec" }, h("h2", {}, "Permissions"), h("div", { class: "perm" }, priv.map((p) => h("span", {}, p.replace(/^NS|UsageDescription$/g, ""))), ents.map((e) => h("span", {}, e)))));
    }
    const sameDev = state.apps.filter((x) => x.d === a.d && x.i !== a.i).sort((x, y) => (x.t < y.t ? 1 : -1)).slice(0, SHELF);
    const similar = state.apps.filter((x) => x.c === a.c && x.i !== a.i && x.d !== a.d && x.c !== "other").sort((x, y) => (x.t < y.t ? 1 : -1)).slice(0, SHELF);
    out.push(shelf(`More from ${a.d}`, null, sameDev, null));
    out.push(shelf(`More ${CATEGORY_NAMES[a.c] || ""}`.trim(), "recently updated", similar, homeHash({ q: "", c: a.c, s: "updated", src: null, fit: state.f.fit, saved: false })));
    out.push(
      h(
        "section",
        { class: "sec" },
        h("h2", {}, "Info"),
        h(
          "dl",
          { class: "facts" },
          fact("Bundle ID", a.i),
          fact("Listed by", src ? h("a", { href: homeHash({ q: "", c: "all", s: "updated", src: a.o, fit: state.f.fit, saved: false }) }, src.name) : "–"),
          fact("First seen", a.f),
        ),
        h("p", { class: "muted small" }, "Files are hosted by the source above, not by Accretion. Install what you trust."),
      ),
    );
    return out.filter(Boolean);
  }

  // ---- add-source dialog -------------------------------------------------------------
  function updateAdd() {
    const which = document.querySelector('input[name="list"]:checked').value;
    const url = SOURCE_URL[which];
    $("add-url").textContent = url;
    $("add-altstore").href = `altstore://source?url=${encodeURIComponent(url)}`;
    $("add-sidestore").href = `sidestore://source?url=${encodeURIComponent(url)}`;
    $("add-feather").href = featherSource(url);
  }
  $("open-add").addEventListener("click", () => {
    updateAdd();
    $("add").showModal();
  });
  document.querySelectorAll('input[name="list"]').forEach((r) => r.addEventListener("change", updateAdd));
  $("add-copy").addEventListener("click", () => copy($("add-url").textContent, "Source link copied"));

  // ---- inputs ---------------------------------------------------------------------------
  let timer;
  $("q").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const q = e.target.value.trim();
      const base = parse().view === "home" ? state.f : { c: "all", s: "updated", src: null, fit: Boolean(deviceIOS), saved: false };
      const next = homeHash({ ...base, q });
      if (parse().view !== "home") location.hash = next;
      else { history.replaceState(null, "", next); route(); }
    }, 140);
  });
  $("q").addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.target.value = ""; go({ q: "" }, { replace: true }); e.target.blur(); }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
      e.preventDefault();
      $("q").focus();
    }
  });
  $("sort").addEventListener("change", (e) => go({ s: e.target.value }));
  $("fit").addEventListener("click", () => go({ fit: !state.f.fit }));
  $("more-btn").addEventListener("click", showMore);
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((entries) => entries.some((x) => x.isIntersecting) && !$("more").hidden && showMore(), { rootMargin: "800px" }).observe($("more"));
  }
  window.addEventListener("hashchange", route);
  if ("serviceWorker" in navigator && location.protocol === "https:") {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }

  // helpers shared with social.js
  // rows from the app_trending view: [{ app_id, score }]
  function setTrending(rows) {
    state.trend = new Map(rows.filter((r) => state.byId.has(r.app_id) && r.score > 0).map((r) => [r.app_id, r.score]));
    if (parse().view === "home") apply();
  }
  window.Acc = { h, toast, copy, fmt, ago, icon, safeUrl, shelf, homeHash, CATEGORY_NAMES, app: (id) => state.byId.get(id), apps: () => state.apps, route, setTrending };

  // ---- boot -------------------------------------------------------------------------------
  Promise.all([
    fetch("data/index.json").then((r) => r.json()),
    fetch("data/stats.json").then((r) => r.json()).catch(() => ({})),
    fetch("support.json").then((r) => (r.ok ? r.json() : {})).catch(() => ({})),
  ])
    .then(([index, stats, support]) => {
      state.support = support || {};
      showSupportLinks();
      state.sources = index.sources;
      state.shards = index.shards;
      state.apps = index.apps.map((a) => ({ ...a, _s: `${a.n} ${a.d} ${a.i} ${a.s}`.toLowerCase() }));
      for (const a of state.apps) state.byId.set(a.i, a);
      $("s-apps").textContent = fmt(stats.apps || state.apps.length);
      $("s-sources").textContent = fmt(stats.sources || state.sources.length);
      $("h-sources").textContent = fmt(stats.sources || state.sources.length);
      $("s-7d").textContent = fmt(stats.updated_7d);
      $("s-new").textContent = fmt(stats.new_30d);
      $("built").textContent = stats.updated ? `built ${stats.updated}` : "live";
      if (lastVisit) {
        const since = state.apps.filter((a) => !a.u && a.t > lastVisit).length;
        if (since) $("built").textContent += ` · ${fmt(since)} updated since your last visit`;
      }
      buildChips();
      updateSavedCount();
      document.dispatchEvent(new CustomEvent("acc:ready"));
      route();
    })
    .catch(() => {
      $("count").textContent = "Couldn't load the app list. Refresh to try again.";
    });
})();
