// Accretion store: loads data/index.json once, filters in memory, and fetches an
// app's full details from its shard (data/apps/NNN.json) when its page opens.
(() => {
  "use strict";

  const PAGE = 60;
  const CATEGORY_NAMES = {
    games: "Games", utilities: "Utilities", "photo-video": "Photo & Video", entertainment: "Entertainment",
    social: "Social", lifestyle: "Lifestyle", developer: "Developer", other: "Other",
  };
  const SOURCE_URL = {
    full: "https://raw.githubusercontent.com/benwilllopez/accretion/main/source.json",
    core: "https://raw.githubusercontent.com/benwilllopez/accretion/main/curated.json",
  };

  const $ = (id) => document.getElementById(id);
  const state = { apps: [], sources: [], shards: 128, q: "", cat: "all", sort: "updated", shown: PAGE, list: [] };
  const shardCache = new Map();

  // ---- helpers ------------------------------------------------------------
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
  function bytes(n) {
    if (!n) return "–";
    const u = ["B", "KB", "MB", "GB"];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(n >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
  }
  function ago(day) {
    const d = Date.parse(day + "T00:00:00Z");
    if (!d) return day || "";
    const days = Math.floor((Date.now() - d) / 864e5);
    if (days <= 0) return "today";
    if (days === 1) return "yesterday";
    if (days < 30) return `${days}d ago`;
    if (days < 365) return `${Math.floor(days / 30)}mo ago`;
    return `${Math.floor(days / 365)}y ago`;
  }
  function fnv1a(text) {
    let h = 0x811c9dc5;
    for (const byte of new TextEncoder().encode(text)) {
      h ^= byte;
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h >>> 0;
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
      prompt("Copy this link:", text); // eslint-disable-line no-alert
    }
  }
  const isNew = (a) => Date.now() - Date.parse(a.f + "T00:00:00Z") < 30 * 864e5;

  // ---- grid ---------------------------------------------------------------
  function apply() {
    const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    let list = state.apps.filter((a) => (state.cat === "all" || a.c === state.cat) && words.every((w) => a._s.includes(w)));
    const by = {
      updated: (a, b) => (a.t < b.t ? 1 : a.t > b.t ? -1 : a.n.localeCompare(b.n)),
      new: (a, b) => (a.f < b.f ? 1 : a.f > b.f ? -1 : a.n.localeCompare(b.n)),
      name: (a, b) => a.n.localeCompare(b.n, undefined, { sensitivity: "base" }),
      size: (a, b) => (b.z || 0) - (a.z || 0),
    }[state.sort];
    if (words.length) {
      // name matches first, then the chosen order
      const starts = (a) => (a.n.toLowerCase().startsWith(words[0]) ? 0 : a.n.toLowerCase().includes(words[0]) ? 1 : 2);
      list.sort((a, b) => starts(a) - starts(b) || by(a, b));
    } else {
      list.sort(by);
    }
    state.list = list;
    state.shown = PAGE;
    render();
  }

  function card(a) {
    return h(
      "a",
      { class: "card", href: `#/app/${encodeURIComponent(a.i)}` },
      icon(a.ic, a.n, "icon"),
      h(
        "div",
        { class: "card-body" },
        h("div", { class: "card-name" }, h("span", {}, a.n), isNew(a) ? h("em", { class: "badge" }, "new") : null),
        h("div", { class: "card-dev" }, a.d),
        h("div", { class: "card-meta" }, h("span", { class: "v" }, `v${a.v}`), h("span", {}, ago(a.t)), a.z ? h("span", {}, bytes(a.z)) : null),
      ),
    );
  }

  function render() {
    const grid = $("grid");
    grid.replaceChildren(...state.list.slice(0, state.shown).map(card));
    $("count").textContent = `${fmt(state.list.length)} ${state.list.length === 1 ? "app" : "apps"}${state.cat !== "all" ? ` in ${CATEGORY_NAMES[state.cat]}` : ""}${state.q ? ` matching "${state.q}"` : ""}`;
    $("more").hidden = state.shown >= state.list.length;
    $("empty").hidden = state.list.length > 0;
  }

  function showMore() {
    const from = state.shown;
    state.shown += PAGE;
    $("grid").append(...state.list.slice(from, state.shown).map(card));
    $("more").hidden = state.shown >= state.list.length;
  }

  function buildChips() {
    const counts = { all: state.apps.length };
    for (const a of state.apps) counts[a.c] = (counts[a.c] || 0) + 1;
    const order = ["all", ...Object.keys(CATEGORY_NAMES).filter((c) => counts[c]).sort((x, y) => (x === "other") - (y === "other") || counts[y] - counts[x])];
    $("cats").replaceChildren(
      ...order.map((c) =>
        h(
          "button",
          {
            class: "chip", type: "button", role: "tab", "aria-selected": String(c === state.cat),
            onclick: () => {
              state.cat = c;
              for (const el of $("cats").children) el.setAttribute("aria-selected", String(el.dataset.cat === c));
              apply();
            },
            "data-cat": c,
          },
          c === "all" ? "All" : CATEGORY_NAMES[c],
          h("span", {}, fmt(counts[c])),
        ),
      ),
    );
  }

  // ---- app page -----------------------------------------------------------
  async function details(bid) {
    const n = fnv1a(bid) % state.shards;
    if (!shardCache.has(n)) {
      shardCache.set(n, fetch(`data/apps/${String(n).padStart(3, "0")}.json`).then((r) => (r.ok ? r.json() : {})).catch(() => ({})));
    }
    return (await shardCache.get(n))[bid];
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

  function fact(label, value) {
    return h("div", {}, h("dt", {}, label), h("dd", {}, value || "–"));
  }

  async function openApp(bid) {
    const a = state.apps.find((x) => x.i === bid);
    const view = $("detail");
    $("store").hidden = true;
    view.hidden = false;
    window.scrollTo(0, 0);
    if (!a) {
      view.replaceChildren(h("a", { class: "btn back", href: "#/" }, "← All apps"), h("p", { class: "empty" }, "This app isn't in the source anymore. It may have been removed or renamed."));
      return;
    }
    document.title = `${a.n} · Accretion`;
    view.replaceChildren(h("a", { class: "btn back", href: "#/" }, "← All apps"), head(a, null), h("p", { class: "muted" }, "Loading details…"));
    const d = await details(bid);
    if (location.hash !== `#/app/${encodeURIComponent(bid)}`) return; // navigated away meanwhile
    view.replaceChildren(h("a", { class: "btn back", href: "#/" }, "← All apps"), head(a, d), ...body(a, d));
  }

  function head(a, d) {
    const latest = d && d.versions && d.versions[0];
    const ipa = latest && safeUrl(latest.url);
    const tint = d && /^[0-9A-F]{6}$/i.test(d.tint || "") ? `#${d.tint}` : null;
    const actions = ipa
      ? h(
          "div",
          { class: "actions" },
          h("a", { class: "btn primary", href: ipa, rel: "nofollow noopener" }, "Download IPA"),
          h("a", { class: "btn", href: `altstore://install?url=${encodeURIComponent(ipa)}` }, "AltStore"),
          h("a", { class: "btn", href: `sidestore://install?url=${encodeURIComponent(ipa)}` }, "SideStore"),
          h("button", { class: "btn", type: "button", onclick: () => copy(ipa, "IPA link copied") }, "Copy IPA link"),
        )
      : null;
    return h(
      "section",
      { class: "d-head", style: tint ? `--tint:${tint}` : null },
      icon(a.ic, a.n, "icon d-icon"),
      h("div", {}, h("h1", { class: "d-name" }, a.n), h("p", { class: "d-dev" }, a.d), a.s ? h("p", { class: "d-sub" }, a.s) : null, actions),
    );
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
        fact("Released", latest.t),
        fact("Size", bytes(latest.z)),
        fact("Min iOS", latest.min),
        fact("Category", CATEGORY_NAMES[a.c] || a.c),
      ),
    ];
    if (latest.notes) out.push(h("section", { class: "sec" }, h("h2", {}, "What's new"), h("p", { class: "prose" }, latest.notes)));
    if (d.shots && d.shots.length) {
      out.push(h("section", { class: "sec" }, h("h2", {}, "Screenshots"), h("div", { class: "shots" }, ...d.shots.map(safeUrl).filter(Boolean).map(shot))));
    }
    if (d.desc) out.push(h("section", { class: "sec" }, h("h2", {}, "About"), h("p", { class: "prose" }, d.desc)));
    out.push(
      h(
        "section",
        { class: "sec" },
        h("h2", {}, "Versions"),
        h(
          "ul",
          { class: "vers" },
          ...d.versions.map((v) =>
            h(
              "li",
              {},
              h("span", {}, `v${v.v}${v.b && v.b !== v.v ? ` (${v.b})` : ""}`),
              h("span", { class: "muted" }, `${v.t} · ${bytes(v.z)}`),
              safeUrl(v.url) ? h("a", { href: v.url, rel: "nofollow noopener" }, "Download") : null,
            ),
          ),
        ),
      ),
    );
    const ents = (d.perms && d.perms.entitlements) || [];
    const priv = Object.keys((d.perms && d.perms.privacy) || {});
    if (ents.length || priv.length) {
      out.push(h("section", { class: "sec" }, h("h2", {}, "Permissions"), h("div", { class: "perm" }, ...priv.map((p) => h("span", {}, p.replace(/^NS|UsageDescription$/g, ""))), ...ents.map((e) => h("span", {}, e)))));
    }
    out.push(
      h(
        "section",
        { class: "sec" },
        h("h2", {}, "Info"),
        h(
          "dl",
          { class: "facts" },
          fact("Bundle ID", a.i),
          fact("Listed by", src ? h("a", { href: src.url, rel: "nofollow noopener" }, src.name) : "–"),
          fact("First seen", a.f),
        ),
        h("p", { class: "muted small" }, "Files are hosted by the source above, not by Accretion. Install what you trust."),
      ),
    );
    return out;
  }

  // ---- routing --------------------------------------------------------------
  function route() {
    const m = location.hash.match(/^#\/app\/(.+)$/);
    if (m) {
      openApp(decodeURIComponent(m[1]));
    } else {
      document.title = "Accretion";
      $("detail").hidden = true;
      $("detail").replaceChildren();
      $("store").hidden = false;
      if (state.scroll) window.scrollTo(0, state.scroll);
    }
  }
  window.addEventListener("hashchange", route);
  document.addEventListener("click", (e) => {
    const link = e.target.closest("a.card");
    if (link) state.scroll = window.scrollY;
  });

  // ---- add-source dialog ----------------------------------------------------
  function updateAdd() {
    const which = document.querySelector('input[name="list"]:checked').value;
    const url = SOURCE_URL[which];
    $("add-url").textContent = url;
    $("add-altstore").href = `altstore://source?url=${encodeURIComponent(url)}`;
    $("add-sidestore").href = `sidestore://source?url=${encodeURIComponent(url)}`;
  }
  $("open-add").addEventListener("click", () => {
    updateAdd();
    $("add").showModal();
  });
  document.querySelectorAll('input[name="list"]').forEach((r) => r.addEventListener("change", updateAdd));
  $("add-copy").addEventListener("click", () => copy($("add-url").textContent, "Source link copied"));

  // ---- boot -----------------------------------------------------------------
  let timer;
  $("q").addEventListener("input", (e) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.q = e.target.value.trim();
      if (location.hash.startsWith("#/app/")) location.hash = "#/";
      apply();
    }, 120);
  });
  $("sort").addEventListener("change", (e) => {
    state.sort = e.target.value;
    apply();
  });
  $("more-btn").addEventListener("click", showMore);
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((entries) => entries.some((x) => x.isIntersecting) && !$("more").hidden && showMore(), { rootMargin: "600px" }).observe($("more"));
  }

  Promise.all([fetch("data/index.json").then((r) => r.json()), fetch("data/stats.json").then((r) => r.json()).catch(() => ({}))])
    .then(([index, stats]) => {
      state.sources = index.sources;
      state.shards = index.shards;
      state.apps = index.apps.map((a) => ({ ...a, _s: `${a.n} ${a.d} ${a.i} ${a.s}`.toLowerCase() }));
      $("s-apps").textContent = fmt(stats.apps || state.apps.length);
      $("s-sources").textContent = fmt(stats.sources || state.sources.length);
      $("h-sources").textContent = fmt(stats.sources || state.sources.length);
      $("s-7d").textContent = fmt(stats.updated_7d);
      $("s-new").textContent = fmt(stats.new_30d);
      $("built").textContent = stats.updated ? `built ${stats.updated}` : "live";
      buildChips();
      apply();
      route();
    })
    .catch(() => {
      $("count").textContent = "Couldn't load the app list. Refresh to try again.";
    });
})();
