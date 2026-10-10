// Accretion community: accounts, comments, likes, ratings, follows, feed,
// notifications and moderation, on Supabase. Turned off when config.js has no keys.
// All access rules live in the database (supabase/schema.sql); this file only shows UI.
(() => {
  "use strict";

  const cfg = window.ACCRETION_CONFIG || {};
  const enabled = Boolean((cfg.supabaseUrl && cfg.supabaseKey) || cfg.fake);
  if (!enabled) return;

  const PAGE = 30;
  // Sign-in providers, in button order. Icons are the brands' standard marks.
  const PROVIDERS = [
    { id: "apple", label: "Apple", paths: [["currentColor", "M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701"]] },
    { id: "google", label: "Google", paths: [
      ["#4285F4", "M23.49 12.27c0-.79-.07-1.54-.19-2.27H12v4.51h6.47c-.29 1.48-1.14 2.73-2.4 3.58v3h3.86c2.26-2.09 3.56-5.17 3.56-8.82z"],
      ["#34A853", "M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.16-4.07 1.16-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09C3.26 21.3 7.31 24 12 24z"],
      ["#FBBC05", "M5.27 14.29c-.25-.72-.38-1.49-.38-2.29s.14-1.57.38-2.29V6.62H1.29C.47 8.24 0 10.06 0 12s.47 3.76 1.29 5.38l3.98-3.09z"],
      ["#EA4335", "M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.31 0 3.26 2.7 1.29 6.62l3.98 3.09c.95-2.85 3.6-4.96 6.73-4.96z"]] },
    { id: "github", label: "GitHub", paths: [["currentColor", "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"]] },
    { id: "discord", label: "Discord", paths: [["currentColor", "M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.211.375-.445.865-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.618-1.25.077.077 0 0 0-.079-.037A19.74 19.74 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .078-.01c3.928 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .079.009c.12.1.246.198.373.292a.077.077 0 0 1-.007.128 12.3 12.3 0 0 1-1.873.891.077.077 0 0 0-.041.107c.36.698.772 1.363 1.225 1.993a.076.076 0 0 0 .084.029 19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.055c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.029zM8.02 15.331c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.211 0 2.176 1.095 2.157 2.419 0 1.333-.956 2.419-2.157 2.419zm7.975 0c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.095 2.157 2.419 0 1.333-.946 2.419-2.157 2.419z"]] },
  ];
  function brandIcon(paths) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    for (const [fill, d] of paths) {
      const p = document.createElementNS(NS, "path");
      p.setAttribute("fill", fill);
      p.setAttribute("d", d);
      svg.append(p);
    }
    return svg;
  }
  const COLORS = ["8B5CF6", "22D3EE", "34D399", "F59E0B", "F43F5E", "3B82F6", "EC4899", "A3E635"];
  let A; // helpers from app.js (window.Acc), set on acc:ready
  const $ = (id) => document.getElementById(id);
  const me = { user: null, profile: null, unread: 0 };
  let ready = false;

  // ---------------------------------------------------------------- data layer
  const api = cfg.fake ? fakeApi() : supabaseApi();

  function supabaseApi() {
    let client;
    const sb = () => (client ||= window.supabase.createClient(cfg.supabaseUrl, cfg.supabaseKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    }));
    const ok = ({ data, error, count }) => {
      if (error) throw new Error(error.message || "Something went wrong");
      return count !== undefined && count !== null && data === null ? count : data;
    };
    const uid = () => me.user && me.user.id;
    const feedCols = "id,author,app_id,parent_id,body,hidden,created_at,edited_at,username,display_name,color,role,likes,replies";
    return {
      async load() {
        if (!window.supabase) {
          await new Promise((res, rej) => {
            const s = document.createElement("script");
            s.src = "vendor/supabase-2.117.2.js";
            s.onload = res;
            s.onerror = () => rej(new Error("Couldn't load the account service"));
            document.head.append(s);
          });
        }
        const { data } = await sb().auth.getSession();
        sb().auth.onAuthStateChange((_e, session) => setUser(session ? session.user : null));
        return data.session ? data.session.user : null;
      },
      // which "Continue with …" buttons to show: the providers switched on in Supabase
      providers: async () => {
        const r = await fetch(`${cfg.supabaseUrl}/auth/v1/settings`, { headers: { apikey: cfg.supabaseKey } });
        if (!r.ok) return [];
        const ext = (await r.json()).external || {};
        return PROVIDERS.map((p) => p.id).filter((id) => ext[id]);
      },
      oauth: async (provider) => ok(await sb().auth.signInWithOAuth({ provider, options: { redirectTo: location.href.split("#")[0] } })),
      signUp: async (email, password, username) => ok(await sb().auth.signUp({ email, password, options: { data: { username }, emailRedirectTo: location.href.split("#")[0] } })),
      signIn: async (email, password) => ok(await sb().auth.signInWithPassword({ email, password })),
      magicLink: async (email) => ok(await sb().auth.signInWithOtp({ email, options: { shouldCreateUser: false, emailRedirectTo: location.href.split("#")[0] } })),
      resetPassword: async (email) => ok(await sb().auth.resetPasswordForEmail(email, { redirectTo: location.href.split("#")[0] })),
      signOut: async () => ok(await sb().auth.signOut()),
      profileById: async (id) => ok(await sb().from("profile_stats").select("*").eq("id", id).maybeSingle()),
      profileByName: async (name) => ok(await sb().from("profile_stats").select("*").eq("username", name).maybeSingle()), // citext: case-insensitive
      updateProfile: async (fields) => ok(await sb().from("profiles").update(fields).eq("id", uid())),
      appStats: async () => ok(await sb().from("app_stats").select("*").limit(5000)),
      appSocial: async (appId) => {
        const [stats, like, rating] = await Promise.all([
          sb().from("app_stats").select("*").eq("app_id", appId).maybeSingle(),
          uid() ? sb().from("app_likes").select("app_id").eq("app_id", appId).eq("user_id", uid()).maybeSingle() : { data: null },
          uid() ? sb().from("app_ratings").select("stars").eq("app_id", appId).eq("user_id", uid()).maybeSingle() : { data: null },
        ]);
        return { stats: ok(stats) || {}, liked: Boolean(like.data), stars: rating.data ? rating.data.stars : 0 };
      },
      likeApp: async (appId, on) => ok(on ? await sb().from("app_likes").insert({ app_id: appId }) : await sb().from("app_likes").delete().eq("app_id", appId).eq("user_id", uid())),
      rateApp: async (appId, stars) => ok(await sb().from("app_ratings").upsert({ app_id: appId, user_id: uid(), stars })),
      thread: async (appId) => ok(await sb().from("post_feed").select(feedCols).eq("app_id", appId).order("created_at", { ascending: true }).limit(500)),
      replies: async (postId) => ok(await sb().from("post_feed").select(feedCols).eq("parent_id", postId).order("created_at", { ascending: true }).limit(200)),
      feed: async ({ following, offset = 0 }) => {
        let q = sb().from("post_feed").select(feedCols).is("parent_id", null).order("created_at", { ascending: false }).range(offset, offset + PAGE - 1);
        if (following) {
          const ids = ok(await sb().from("follows").select("followee").eq("follower", uid())).map((r) => r.followee);
          if (!ids.length) return [];
          q = q.in("author", ids);
        }
        return ok(await q);
      },
      postsBy: async (userId, offset = 0) => ok(await sb().from("post_feed").select(feedCols).eq("author", userId).order("created_at", { ascending: false }).range(offset, offset + PAGE - 1)),
      createPost: async ({ body, appId, parentId }) => ok(await sb().from("posts").insert({ body, app_id: appId || null, parent_id: parentId || null }).select("id").single()),
      deletePost: async (id) => ok(await sb().from("posts").delete().eq("id", id)),
      hidePost: async (id, hidden) => ok(await sb().from("posts").update({ hidden }).eq("id", id)),
      myPostLikes: async (ids) => (uid() && ids.length ? ok(await sb().from("post_likes").select("post_id").eq("user_id", uid()).in("post_id", ids)).map((r) => r.post_id) : []),
      likePost: async (id, on) => ok(on ? await sb().from("post_likes").insert({ post_id: id }) : await sb().from("post_likes").delete().eq("post_id", id).eq("user_id", uid())),
      isFollowing: async (id) => Boolean(uid() && ok(await sb().from("follows").select("followee").eq("follower", uid()).eq("followee", id).maybeSingle())),
      follow: async (id, on) => ok(on ? await sb().from("follows").insert({ followee: id }) : await sb().from("follows").delete().eq("follower", uid()).eq("followee", id)),
      report: async ({ postId, profileId, reason }) => ok(await sb().from("reports").insert({ post_id: postId || null, profile_id: profileId || null, reason })),
      notifications: async () => ok(await sb().from("notifications").select("id,kind,post_id,read,created_at,actor:profiles!notifications_actor_fkey(username,display_name,color)").order("created_at", { ascending: false }).limit(60)),
      unread: async () => (uid() ? ok(await sb().from("notifications").select("id", { count: "exact", head: true }).eq("read", false)) : 0),
      markRead: async () => ok(await sb().from("notifications").update({ read: true }).eq("read", false)),
      reports: async () => ok(await sb().from("reports").select("id,reason,status,created_at,post:posts(id,body,app_id,hidden,author,author_p:profiles!posts_author_fkey(id,username,banned)),profile:profiles!reports_profile_id_fkey(id,username,banned),reporter_p:profiles!reports_reporter_fkey(username)").eq("status", "open").order("created_at", { ascending: true }).limit(100)),
      resolveReport: async (id, status) => ok(await sb().from("reports").update({ status }).eq("id", id)),
      setBanned: async (profileId, banned) => ok(await sb().from("profiles").update({ banned }).eq("id", profileId)),
      setRole: async (username, role) => ok(await sb().from("profiles").update({ role }).eq("username", username).select("username,role")),
      deleteAccount: async () => ok(await sb().rpc("delete_my_account")),
      // anonymous demand counts (see supabase/schema.sql)
      track: async ({ kind, app, q }) => ok(await sb().rpc("track", { p_kind: kind, p_app: app, p_q: q })),
      trending: async () => ok(await sb().from("app_trending").select("app_id,searches,views,installs,score").order("score", { ascending: false }).limit(200)),
      missing: async () => ok(await sb().from("missing_searches").select("query,hits,last_day").order("hits", { ascending: false }).limit(50)),
    };
  }

  // ---------------------------------------------------------------- session + header
  // The profile (role, ban, avatar) loads before anything that depends on it redraws.
  async function setUser(user) {
    const changed = (me.user && me.user.id) !== (user && user.id);
    me.user = user;
    if (!changed) return;
    me.profile = user ? await api.profileById(user.id).catch(() => null) : null;
    renderAccount();
    if (me.profile && /^user_[0-9a-z]+$/.test(me.profile.username) && !location.hash.startsWith("#/me")) {
      try {
        if (!sessionStorage.getItem("acc.named")) {
          sessionStorage.setItem("acc.named", "1");
          location.hash = "#/me";
        }
      } catch { /* private mode */ }
    }
    if (user) refreshUnread();
    if (ready) document.dispatchEvent(new CustomEvent("acc:auth"));
  }

  async function refreshUnread() {
    try { me.unread = await api.unread(); } catch { me.unread = 0; }
    renderAccount();
  }

  function avatar(p, size = 36) {
    const name = (p && (p.display_name || p.username)) || "?";
    const color = /^[0-9A-Fa-f]{6}$/.test((p && p.color) || "") ? p.color : "8B5CF6";
    return A.h("span", { class: "avatar", style: `--c:#${color};width:${size}px;height:${size}px;font-size:${Math.round(size * 0.42)}px`, "aria-hidden": "true" }, name.trim().charAt(0).toUpperCase());
  }
  const isMod = () => me.profile && ["mod", "admin"].includes(me.profile.role) && !me.profile.banned;
  const roleBadge = (role) => (role === "admin" || role === "mod" ? A.h("em", { class: `badge role-${role}` }, role) : null);

  function renderAccount() {
    const box = $("account");
    const { h } = A;
    if (!me.user) {
      box.replaceChildren(h("a", { class: "btn ghost signin", href: "#/signin", onclick: rememberSpot }, "Sign in"));
      return;
    }
    const p = me.profile || { username: "…" };
    box.replaceChildren(
      h("a", { class: "bell", href: "#/notifications", "aria-label": `Notifications${me.unread ? `, ${me.unread} unread` : ""}` },
        bellIcon(),
        me.unread ? h("span", { class: "dot" }, me.unread > 9 ? "9+" : String(me.unread)) : null),
      h("a", { class: "me", href: `#/u/${encodeURIComponent(p.username)}`, "aria-label": "Your profile" }, avatar(p, 32)),
    );
  }
  function bellIcon() {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", "M12 3a6 6 0 0 0-6 6v3.6L4.3 15.5A1 1 0 0 0 5.2 17h13.6a1 1 0 0 0 .9-1.5L18 12.6V9a6 6 0 0 0-6-6Zm-2.5 15.5a2.5 2.5 0 0 0 5 0Z");
    svg.append(p);
    return svg;
  }

  // ---------------------------------------------------------------- posts
  function bodyText(text) {
    // plain text with clickable https links and @mentions; never HTML
    const out = [];
    const re = /(https:\/\/[^\s<>"']+)|(@[A-Za-z0-9_]{3,20})/g;
    let last = 0;
    for (const m of text.matchAll(re)) {
      out.push(text.slice(last, m.index));
      if (m[1]) out.push(A.h("a", { href: m[1], rel: "nofollow noopener ugc", target: "_blank" }, m[1]));
      else out.push(A.h("a", { href: `#/u/${encodeURIComponent(m[2].slice(1))}` }, m[2]));
      last = m.index + m[0].length;
    }
    out.push(text.slice(last));
    return A.h("p", { class: "post-body" }, out);
  }

  function postEl(p, { liked = false, showApp = true, onReply = null, onChange = () => {} } = {}) {
    const { h } = A;
    const app = p.app_id && showApp ? A.app(p.app_id) : null;
    let likes = p.likes || 0;
    const likeBtn = h("button", { class: `act like${liked ? " on" : ""}`, type: "button", "aria-pressed": String(liked) }, `♥ ${likes || ""}`.trim());
    likeBtn.addEventListener("click", async () => {
      if (!requireUser()) return;
      const on = likeBtn.getAttribute("aria-pressed") !== "true";
      try {
        await api.likePost(p.id, on);
        likes += on ? 1 : -1;
        likeBtn.classList.toggle("on", on);
        likeBtn.setAttribute("aria-pressed", String(on));
        likeBtn.textContent = `♥ ${likes || ""}`.trim();
      } catch (e) { A.toast(e.message); }
    });
    const own = me.user && me.user.id === p.author;
    const menu = [];
    if (own) menu.push(h("button", { class: "act", type: "button", onclick: async () => { if (!confirmIn(el, "Delete this post?")) return; try { await api.deletePost(p.id); el.remove(); onChange(); A.toast("Deleted"); } catch (e) { A.toast(e.message); } } }, "Delete"));
    if (!own && me.user) menu.push(h("button", { class: "act", type: "button", onclick: () => reportDialog({ postId: p.id }) }, "Report"));
    if (isMod()) menu.push(h("button", { class: "act mod", type: "button", onclick: async () => { try { await api.hidePost(p.id, !p.hidden); p.hidden = !p.hidden; el.classList.toggle("hidden-post", p.hidden); A.toast(p.hidden ? "Hidden" : "Visible again"); } catch (e) { A.toast(e.message); } } }, p.hidden ? "Unhide" : "Hide"));
    const el = h(
      "article",
      { class: `post${p.hidden ? " hidden-post" : ""}`, id: `post-${p.id}` },
      h("a", { href: `#/u/${encodeURIComponent(p.username)}`, class: "post-av" }, avatar(p, 36)),
      h(
        "div",
        { class: "post-main" },
        h("div", { class: "post-head" },
          h("a", { href: `#/u/${encodeURIComponent(p.username)}`, class: "post-name" }, p.display_name || p.username),
          h("span", { class: "post-user" }, `@${p.username}`), roleBadge(p.role),
          h("span", { class: "post-time", title: new Date(p.created_at).toLocaleString() }, timeAgo(p.created_at)),
          p.edited_at ? h("span", { class: "post-time" }, "· edited") : null,
          p.hidden ? h("em", { class: "badge hidden-badge" }, "hidden") : null),
        bodyText(p.body),
        app ? h("a", { class: "app-chip", href: `#/app/${encodeURIComponent(app.i)}` }, A.icon(app.ic, app.n, "chip-icon"), h("span", {}, app.n), h("span", { class: "muted" }, `v${app.v}`)) : null,
        h("div", { class: "post-acts" },
          likeBtn,
          onReply ? h("button", { class: "act", type: "button", onclick: () => onReply(p) }, p.replies ? `Reply · ${p.replies}` : "Reply") : null,
          ...menu),
      ),
    );
    return el;
  }

  function confirmIn(el, question) {
    return window.confirm(question); // the store runs on its own site, where confirm() works
  }

  function timeAgo(iso) {
    const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
    if (s < 60) return "now";
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    if (s < 86400) return `${Math.floor(s / 3600)}h`;
    if (s < 604800) return `${Math.floor(s / 86400)}d`;
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: s > 31536000 ? "numeric" : undefined });
  }

  function composer({ placeholder, onSubmit, autofocus = false, compact = false }) {
    const { h } = A;
    if (!me.user) {
      return h("div", { class: "composer signed-out" }, h("p", { class: "muted" }, "Join the conversation."), h("a", { class: "btn primary", href: "#/signin" }, "Sign in or create an account"));
    }
    if (me.profile && me.profile.banned) return h("p", { class: "muted" }, "Your account can't post right now.");
    const ta = h("textarea", { class: "input", rows: compact ? 2 : 3, maxlength: 2000, placeholder, "aria-label": placeholder });
    const count = h("span", { class: "muted small" }, "0 / 2000");
    const send = h("button", { class: "btn primary", type: "submit", disabled: true }, "Post");
    ta.addEventListener("input", () => {
      count.textContent = `${ta.value.length} / 2000`;
      send.disabled = !ta.value.trim();
    });
    const form = h("form", { class: `composer${compact ? " compact" : ""}` }, avatar(me.profile, 36), h("div", { class: "composer-main" }, ta, h("div", { class: "composer-row" }, count, send)));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = ta.value.trim();
      if (!body) return;
      send.disabled = true;
      try {
        await onSubmit(body);
        ta.value = "";
        count.textContent = "0 / 2000";
      } catch (err) {
        A.toast(err.message);
      } finally {
        send.disabled = !ta.value.trim();
      }
    });
    if (autofocus) setTimeout(() => ta.focus(), 0);
    return form;
  }

  function requireUser() {
    if (me.user) return true;
    rememberSpot();
    location.hash = "#/signin";
    return false;
  }
  function rememberSpot() {
    try { sessionStorage.setItem("acc.back", location.hash && !location.hash.startsWith("#/signin") ? location.hash : "#/feed"); } catch { /* private mode */ }
  }
  function goBack() {
    let back = "#/feed";
    try { back = sessionStorage.getItem("acc.back") || back; sessionStorage.removeItem("acc.back"); } catch { /* private mode */ }
    location.hash = back;
  }

  // ---------------------------------------------------------------- app page
  async function renderAppSocial({ app, mount }) {
    const { h } = A;
    mount.replaceChildren(h("p", { class: "muted small" }, "Loading community…"));
    let data;
    try { data = await api.appSocial(app.i); } catch (e) { mount.replaceChildren(h("p", { class: "muted small" }, e.message)); return; }
    let { liked, stars } = data;
    let likeCount = data.stats.likes || 0;
    const avg = data.stats.avg_rating;
    const likeBtn = h("button", { class: `btn${liked ? " on" : ""}`, type: "button", "aria-pressed": String(liked) });
    const paintLike = () => { likeBtn.textContent = `♥ ${liked ? "Liked" : "Like"}${likeCount ? ` · ${A.fmt(likeCount)}` : ""}`; likeBtn.classList.toggle("on", liked); likeBtn.setAttribute("aria-pressed", String(liked)); };
    paintLike();
    likeBtn.addEventListener("click", async () => {
      if (!requireUser()) return;
      try { await api.likeApp(app.i, !liked); liked = !liked; likeCount += liked ? 1 : -1; paintLike(); } catch (e) { A.toast(e.message); }
    });
    const starsBox = h("div", { class: "stars", role: "radiogroup", "aria-label": "Your rating" });
    const paintStars = () => {
      starsBox.replaceChildren(...[1, 2, 3, 4, 5].map((n) => h("button", { type: "button", class: `star${n <= stars ? " on" : ""}`, role: "radio", "aria-checked": String(n === stars), "aria-label": `${n} star${n > 1 ? "s" : ""}`, onclick: async () => {
        if (!requireUser()) return;
        try { await api.rateApp(app.i, n); stars = n; paintStars(); A.toast("Thanks for rating"); } catch (e) { A.toast(e.message); }
      } }, "★")));
    };
    paintStars();
    const summary = h("span", { class: "muted small" }, avg ? `${Number(avg).toFixed(1)} ★ from ${A.fmt(data.stats.ratings)} rating${data.stats.ratings > 1 ? "s" : ""}` : "No ratings yet");
    const list = h("div", { class: "thread" });
    const head = h("section", { class: "sec community" },
      h("div", { class: "community-top" }, likeBtn, h("div", { class: "rate" }, starsBox, summary)),
      h("h2", {}, `Comments${data.stats.comments ? ` · ${A.fmt(data.stats.comments)}` : ""}`),
      composer({ placeholder: `Say something about ${app.n}…`, onSubmit: async (body) => { await api.createPost({ body, appId: app.i }); await loadThread(); } }),
      list);
    mount.replaceChildren(head);

    async function loadThread() {
      let rows;
      try { rows = await api.thread(app.i); } catch (e) { list.replaceChildren(h("p", { class: "muted small" }, e.message)); return; }
      const liked = new Set(await api.myPostLikes(rows.map((r) => r.id)).catch(() => []));
      const top = rows.filter((r) => !r.parent_id).reverse();
      const kids = new Map();
      for (const r of rows) if (r.parent_id) (kids.get(r.parent_id) || kids.set(r.parent_id, []).get(r.parent_id)).push(r);
      if (!top.length) return list.replaceChildren(h("p", { class: "muted small empty-thread" }, "No comments yet. Be the first."));
      list.replaceChildren(...top.map((t) => {
        const replyBox = h("div", { class: "replies" }, ...(kids.get(t.id) || []).map((r) => postEl(r, { liked: liked.has(r.id), showApp: false, onChange: loadThread })));
        const onReply = () => {
          if (!requireUser()) return;
          if (replyBox.querySelector("form")) return;
          replyBox.append(composer({ placeholder: `Reply to @${t.username}…`, compact: true, autofocus: true, onSubmit: async (body) => { await api.createPost({ body, parentId: t.id }); await loadThread(); } }));
        };
        return h("div", { class: "thread-item" }, postEl(t, { liked: liked.has(t.id), showApp: false, onReply, onChange: loadThread }), replyBox);
      }));
    }
    loadThread();
  }

  // ---------------------------------------------------------------- home shelves
  let statsCache = null;
  async function renderHomeShelves({ mount }) {
    try {
      statsCache ||= await api.appStats();
    } catch { return; }
    const known = statsCache.filter((s) => A.app(s.app_id));
    const liked = [...known].filter((s) => s.likes > 0).sort((a, b) => b.likes - a.likes).slice(0, 18).map((s) => A.app(s.app_id));
    const rated = [...known].filter((s) => s.ratings >= 3).sort((a, b) => b.avg_rating - a.avg_rating || b.ratings - a.ratings).slice(0, 18).map((s) => A.app(s.app_id));
    const talked = [...known].filter((s) => s.comments > 0).sort((a, b) => b.comments - a.comments).slice(0, 18).map((s) => A.app(s.app_id));
    mount.replaceChildren(...[
      A.shelf("Most liked", "by the community", liked, null, { ranked: true }),
      A.shelf("Top rated", "3+ ratings", rated, null, { ranked: true }),
      A.shelf("Most discussed", "comments", talked, "#/feed", { ranked: true }),
    ].filter(Boolean));
  }

  // ---------------------------------------------------------------- views
  const view = () => $("social");
  function page(title, ...kids) {
    document.title = `${title} · Accretion`;
    view().replaceChildren(...kids);
  }

  async function renderFeed(params) {
    const { h } = A;
    const following = params.tab === "following" && me.user;
    const list = h("div", { class: "feed-list" });
    const more = h("button", { class: "btn", type: "button", hidden: true }, "Load more");
    let offset = 0;
    const tabs = h("div", { class: "tabs", role: "tablist" },
      h("a", { href: "#/feed", class: following ? "" : "on", role: "tab", "aria-selected": String(!following) }, "Everyone"),
      me.user ? h("a", { href: "#/feed?tab=following", class: following ? "on" : "", role: "tab", "aria-selected": String(Boolean(following)) }, "Following") : null);
    page("Feed",
      h("div", { class: "view-head" }, h("h1", { class: "view-title" }, "Feed"), h("p", { class: "muted" }, "What people are saying about apps, plus anything else on their mind.")),
      composer({ placeholder: "What's new?", onSubmit: async (body) => { await api.createPost({ body }); offset = 0; list.replaceChildren(); await load(); } }),
      tabs, list, h("div", { class: "more" }, more));
    async function load() {
      more.disabled = true;
      let rows;
      try { rows = await api.feed({ following, offset }); } catch (e) { list.append(h("p", { class: "muted" }, e.message)); return; }
      const liked = new Set(await api.myPostLikes(rows.map((r) => r.id)).catch(() => []));
      if (!rows.length && !offset) list.append(h("p", { class: "muted empty-thread" }, following ? "Nothing yet from people you follow. Find people in comments and tap Follow." : "No posts yet. Say hi!"));
      list.append(...rows.map((r) => threadItem(r, liked.has(r.id))));
      offset += rows.length;
      more.hidden = rows.length < PAGE;
      more.disabled = false;
    }
    more.addEventListener("click", load);
    load();
  }

  function threadItem(r, liked) {
    const { h } = A;
    const replyBox = h("div", { class: "replies" });
    let open = false;
    const onReply = async () => {
      if (open) return;
      open = true;
      try {
        const kids = await api.replies(r.id);
        const likedKids = new Set(await api.myPostLikes(kids.map((k) => k.id)).catch(() => []));
        replyBox.append(...kids.map((k) => postEl(k, { liked: likedKids.has(k.id), showApp: false })));
      } catch (e) { A.toast(e.message); }
      if (me.user) replyBox.append(composer({ placeholder: `Reply to @${r.username}…`, compact: true, autofocus: true, onSubmit: async (body) => { await api.createPost({ body, parentId: r.id }); replyBox.replaceChildren(); open = false; r.replies = (r.replies || 0) + 1; await onReply(); } }));
    };
    return h("div", { class: "thread-item" }, postEl(r, { liked, onReply }), replyBox);
  }

  async function renderProfile(username) {
    const { h } = A;
    page(`@${username}`, h("p", { class: "muted" }, "Loading…"));
    let p;
    try { p = await api.profileByName(username); } catch (e) { return page("Profile", h("p", { class: "muted" }, e.message)); }
    if (!p) return page("Profile", h("div", { class: "view-head" }, h("h1", { class: "view-title" }, "No such user"), h("p", { class: "muted" }, `Nobody here goes by @${username}.`)));
    const own = me.user && me.user.id === p.id;
    let following = own ? false : await api.isFollowing(p.id).catch(() => false);
    let followers = p.followers;
    const followersEl = h("b", {}, A.fmt(followers));
    const followBtn = own ? null : h("button", { class: `btn${following ? " on" : " primary"}`, type: "button" }, following ? "Following" : "Follow");
    if (followBtn) {
      followBtn.addEventListener("click", async () => {
        if (!requireUser()) return;
        try {
          await api.follow(p.id, !following);
          following = !following;
          followers += following ? 1 : -1;
          followersEl.textContent = A.fmt(followers);
          followBtn.textContent = following ? "Following" : "Follow";
          followBtn.className = `btn${following ? " on" : " primary"}`;
        } catch (e) { A.toast(e.message); }
      });
    }
    const list = h("div", { class: "feed-list" });
    const modTools = isMod() && !own ? h("button", { class: "btn ghost mod", type: "button", onclick: async () => { try { await api.setBanned(p.id, !p.banned); p.banned = !p.banned; A.toast(p.banned ? "User banned" : "User unbanned"); renderProfile(username); } catch (e) { A.toast(e.message); } } }, p.banned ? "Unban" : "Ban") : null;
    page(`@${p.username}`,
      h("section", { class: "profile-card" },
        avatar(p, 84),
        h("div", { class: "profile-main" },
          h("h1", { class: "view-title" }, p.display_name || p.username, roleBadge(p.role), p.banned ? h("em", { class: "badge hidden-badge" }, "banned") : null),
          h("p", { class: "muted" }, `@${p.username} · joined ${new Date(p.created_at).toLocaleDateString(undefined, { month: "short", year: "numeric" })}`),
          p.bio ? bodyText(p.bio) : null,
          h("p", { class: "profile-stats" }, h("span", {}, h("b", {}, A.fmt(p.posts)), " posts"), h("span", {}, followersEl, " followers"), h("span", {}, h("b", {}, A.fmt(p.following)), " following"), h("span", {}, h("b", {}, A.fmt(p.liked_apps)), " liked apps")),
          h("div", { class: "actions" },
            followBtn,
            own ? h("a", { class: "btn", href: "#/me" }, "Edit profile") : null,
            !own && me.user ? h("button", { class: "btn ghost", type: "button", onclick: () => reportDialog({ profileId: p.id }) }, "Report") : null,
            modTools))),
      h("h2", { class: "section-title" }, "Posts"),
      list);
    try {
      const rows = await api.postsBy(p.id);
      const liked = new Set(await api.myPostLikes(rows.map((r) => r.id)).catch(() => []));
      list.replaceChildren(...(rows.length ? rows.map((r) => postEl(r, { liked: liked.has(r.id) })) : [h("p", { class: "muted empty-thread" }, "No posts yet.")]));
    } catch (e) { list.replaceChildren(h("p", { class: "muted" }, e.message)); }
  }

  async function renderSettings() {
    const { h } = A;
    if (!me.user) return renderSignIn();
    const p = me.profile || (await api.profileById(me.user.id));
    let color = p.color;
    const welcome = /^user_[0-9a-z]+$/.test(p.username);
    const uname = h("input", { class: "input", id: "set-user", maxlength: 20, pattern: "[A-Za-z0-9_]{3,20}", required: true, value: p.username, autocomplete: "username" });
    const name = h("input", { class: "input", id: "set-name", maxlength: 40, value: p.display_name || "", placeholder: p.username });
    const bio = h("textarea", { class: "input", id: "set-bio", rows: 3, maxlength: 280, placeholder: "A line about you" });
    bio.value = p.bio || "";
    const swatches = h("div", { class: "swatches", role: "radiogroup", "aria-label": "Avatar color" }, ...COLORS.map((c) => h("button", { type: "button", class: `swatch${c === color ? " on" : ""}`, style: `--c:#${c}`, role: "radio", "aria-checked": String(c === color), "aria-label": `#${c}`, onclick: (e) => { color = c; for (const s of swatches.children) { s.classList.toggle("on", s === e.currentTarget); s.setAttribute("aria-checked", String(s === e.currentTarget)); } } })));
    const form = h("form", { class: "card-form" },
      welcome ? h("p", { class: "welcome" }, "Welcome! Pick a username so people can find and mention you.") : null,
      h("label", { for: "set-user" }, "Username"), uname,
      h("label", { for: "set-name" }, "Display name"), name,
      h("label", { for: "set-bio" }, "Bio"), bio,
      h("span", { class: "label" }, "Avatar color"), swatches,
      h("div", { class: "actions" }, h("button", { class: "btn primary", type: "submit" }, "Save"), h("a", { class: "btn ghost", href: `#/u/${encodeURIComponent(p.username)}` }, "Cancel")));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const username = uname.value.trim();
        if (!/^[A-Za-z0-9_]{3,20}$/.test(username)) throw new Error("Usernames are 3–20 letters, numbers or underscores.");
        try {
          await api.updateProfile({ username, display_name: name.value.trim(), bio: bio.value.trim(), color });
        } catch (err) {
          throw new Error(/duplicate|unique|23505/i.test(err.message) ? "That username is taken. Try another." : err.message);
        }
        me.profile = await api.profileById(me.user.id);
        renderAccount();
        A.toast("Profile saved");
        location.hash = `#/u/${encodeURIComponent(me.profile.username)}`;
      } catch (err) { A.toast(err.message); }
    });
    const danger = h("section", { class: "card-form danger" },
      h("h2", {}, "Account"),
      h("p", { class: "muted small" }, `Signed in as ${me.user.email || p.username}.`),
      h("div", { class: "actions" },
        h("button", { class: "btn", type: "button", onclick: async () => { await api.signOut(); await setUser(null); location.hash = "#/"; } }, "Sign out"),
        h("button", { class: "btn ghost warn-btn", type: "button", onclick: async () => {
          if (!window.confirm("Delete your account? Your profile, posts, likes and follows are removed for good.")) return;
          try { await api.deleteAccount(); await api.signOut().catch(() => {}); await setUser(null); location.hash = "#/"; A.toast("Account deleted"); } catch (err) { A.toast(err.message); }
        } }, "Delete account")));
    page("Edit profile", h("div", { class: "view-head" }, h("h1", { class: "view-title" }, "Edit profile"), h("p", { class: "muted" }, `@${p.username}`)), form, danger,
      isMod() ? h("p", {}, h("a", { class: "btn", href: "#/mod" }, "Open moderation")) : null);
  }

  async function renderNotifications() {
    const { h } = A;
    if (!me.user) return renderSignIn();
    page("Notifications", h("div", { class: "view-head" }, h("h1", { class: "view-title" }, "Notifications")), h("p", { class: "muted" }, "Loading…"));
    let rows;
    try { rows = await api.notifications(); } catch (e) { return page("Notifications", h("p", { class: "muted" }, e.message)); }
    const verb = { like: "liked your post", reply: "replied to you", follow: "followed you" };
    const list = h("ul", { class: "notes" }, ...rows.map((n) => {
      const who = n.actor || { username: "someone" };
      const link = n.kind === "follow" ? `#/u/${encodeURIComponent(who.username)}` : "#/feed";
      return h("li", { class: n.read ? "" : "unread" },
        avatar(who, 32),
        h("a", { href: link }, h("b", {}, `@${who.username}`), ` ${verb[n.kind] || n.kind}`),
        h("span", { class: "muted small" }, timeAgo(n.created_at)));
    }));
    page("Notifications", h("div", { class: "view-head" }, h("h1", { class: "view-title" }, "Notifications")), rows.length ? list : h("p", { class: "muted empty-thread" }, "Nothing yet. Likes, replies and new followers show up here."));
    if (rows.some((n) => !n.read)) {
      api.markRead().then(() => { me.unread = 0; renderAccount(); }).catch(() => {});
    }
  }

  async function renderMod() {
    const { h } = A;
    if (!isMod()) return page("Moderation", h("p", { class: "muted" }, "Moderators only."));
    page("Moderation", h("p", { class: "muted" }, "Loading reports…"));
    let rows;
    try { rows = await api.reports(); } catch (e) { return page("Moderation", h("p", { class: "muted" }, e.message)); }
    const list = h("ul", { class: "reports" }, ...rows.map((r) => {
      const target = r.post ? r.post.author_p : r.profile;
      const li = h("li", {},
        h("div", { class: "report-head" }, h("b", {}, r.post ? "Post" : "Profile"), h("span", { class: "muted small" }, `reported by @${(r.reporter_p || {}).username || "?"} · ${timeAgo(r.created_at)}`)),
        h("p", { class: "report-reason" }, `“${r.reason}”`),
        r.post ? h("blockquote", { class: "report-post" }, r.post.body) : null,
        target ? h("p", { class: "muted small" }, "Author: ", h("a", { href: `#/u/${encodeURIComponent(target.username)}` }, `@${target.username}`), target.banned ? " (banned)" : "") : null,
        h("div", { class: "actions" },
          r.post ? h("button", { class: "btn", type: "button", onclick: async () => { try { await api.hidePost(r.post.id, true); await api.resolveReport(r.id, "resolved"); li.remove(); A.toast("Post hidden"); } catch (e) { A.toast(e.message); } } }, "Hide post") : null,
          target && !target.banned ? h("button", { class: "btn", type: "button", onclick: async () => { try { await api.setBanned(target.id, true); await api.resolveReport(r.id, "resolved"); li.remove(); A.toast(`@${target.username} banned`); } catch (e) { A.toast(e.message); } } }, "Ban user") : null,
          h("button", { class: "btn ghost", type: "button", onclick: async () => { try { await api.resolveReport(r.id, "dismissed"); li.remove(); A.toast("Dismissed"); } catch (e) { A.toast(e.message); } } }, "Dismiss")));
      return li;
    }));
    const roleForm = me.profile.role === "admin" ? (() => {
      const user = h("input", { class: "input", id: "role-user", placeholder: "username" });
      const role = h("select", { class: "input", id: "role-pick" }, h("option", { value: "mod" }, "Moderator"), h("option", { value: "user" }, "Regular user"), h("option", { value: "admin" }, "Admin"));
      const f = h("form", { class: "card-form" }, h("h2", {}, "Roles"), h("p", { class: "muted small" }, "Give or take moderator rights."), h("div", { class: "row" }, user, role, h("button", { class: "btn primary", type: "submit" }, "Apply")));
      f.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          const res = await api.setRole(user.value.trim(), role.value);
          A.toast(res && res.length ? `@${res[0].username} is now ${res[0].role}` : "No user with that name");
        } catch (err) { A.toast(err.message); }
      });
      return f;
    })() : null;
    const demand = h("section", { class: "demand" }, h("p", { class: "muted" }, "Loading what people look for…"));
    page("Moderation",
      h("div", { class: "view-head" }, h("h1", { class: "view-title" }, "Moderation"), h("p", { class: "muted" }, `${rows.length} open report${rows.length === 1 ? "" : "s"}. Hidden posts stay visible to their author and to mods.`)),
      rows.length ? list : h("p", { class: "muted empty-thread" }, "No open reports."),
      demand,
      roleForm);
    renderDemand(demand);
  }

  // What people look for: anonymous counts, to decide which apps and sources to prioritise
  async function renderDemand(box) {
    const { h } = A;
    let top;
    let missing;
    try { [top, missing] = await Promise.all([api.trending(), api.missing()]); } catch (e) { box.replaceChildren(h("p", { class: "muted" }, e.message)); return; }
    const searched = top.filter((r) => r.searches > 0).sort((a, b) => b.searches - a.searches || b.score - a.score).slice(0, 25);
    const num = (n) => h("span", { class: "demand-n" }, `${A.fmt(n)} ${n === 1 ? "search" : "searches"}`);
    const appLink = (id) => { const a = A.app(id); return h("a", { href: `#/app/${encodeURIComponent(id)}` }, a ? a.n : id); };
    box.replaceChildren(
      h("h2", {}, "What people look for"),
      h("p", { class: "muted small" }, "Anonymous counts: each visitor counts once per app per day. Searches that led to an app count most."),
      h("div", { class: "demand-grid" },
        h("div", {},
          h("h3", {}, "Most searched apps", h("span", { class: "muted small" }, " · 7 days")),
          searched.length
            ? h("ol", { class: "demand-list" }, searched.map((r) => h("li", {}, appLink(r.app_id), num(r.searches), h("span", { class: "muted small" }, `${A.fmt(r.views)} views · ${A.fmt(r.installs)} installs`))))
            : h("p", { class: "muted small" }, "No searches counted yet.")),
        h("div", {},
          h("h3", {}, "Searched but not in the store", h("span", { class: "muted small" }, " · 30 days")),
          missing.length
            ? h("ol", { class: "demand-list" }, missing.map((r) => h("li", {}, h("span", {}, r.query), num(r.hits), h("span", { class: "muted small" }, `last ${r.last_day}`))))
            : h("p", { class: "muted small" }, "Nothing missing so far.")),
      ));
  }

  function renderSignIn(params = {}) {
    const { h } = A;
    if (me.user) { location.hash = `#/u/${encodeURIComponent((me.profile || {}).username || "")}`; return; }
    let mode = params.mode === "signup" ? "signup" : "signin";
    const email = h("input", { class: "input", id: "au-email", type: "email", autocomplete: "email", required: true, placeholder: "you@example.com" });
    const pass = h("input", { class: "input", id: "au-pass", type: "password", autocomplete: "current-password", minlength: 8, required: true, placeholder: "At least 8 characters" });
    const user = h("input", { class: "input", id: "au-user", autocomplete: "username", pattern: "[A-Za-z0-9_]{3,20}", placeholder: "3–20 letters, numbers or _" });
    const age = h("input", { type: "checkbox", id: "au-age" });
    const msg = h("p", { class: "form-msg", role: "status" });
    const submit = h("button", { class: "btn primary", type: "submit" });
    const signupOnly = [
      h("label", { for: "au-user" }, "Username"), user,
      h("label", { class: "check", for: "au-age" }, age, h("span", {}, "I'm 13 or older and agree to the ", h("a", { href: "rules.html", target: "_blank" }, "community rules"), " and ", h("a", { href: "privacy.html", target: "_blank" }, "privacy policy"), ".")),
    ];
    const switcher = h("p", { class: "muted small" });
    const extra = h("div", { class: "actions small-actions" },
      h("button", { class: "btn ghost", type: "button", onclick: async () => { if (!email.value) return (msg.textContent = "Enter your email first."); try { await api.magicLink(email.value); msg.textContent = "Check your email for a sign-in link."; } catch (e) { msg.textContent = e.message; } } }, "Email me a sign-in link"),
      h("button", { class: "btn ghost", type: "button", onclick: async () => { if (!email.value) return (msg.textContent = "Enter your email first."); try { await api.resetPassword(email.value); msg.textContent = "Check your email to reset your password."; } catch (e) { msg.textContent = e.message; } } }, "Forgot password"));
    const fields = h("div", { class: "signup-fields" }, ...signupOnly);
    const social = h("div", { class: "oauth", hidden: true });
    const form = h("form", { class: "card-form auth" }, h("h1", { class: "view-title" }), social, h("label", { for: "au-email" }, "Email"), email, h("label", { for: "au-pass" }, "Password"), pass, fields, submit, msg, extra, switcher);
    api.providers().then((ids) => {
      if (!ids.length) return;
      social.replaceChildren(
        ...PROVIDERS.filter((p) => ids.includes(p.id)).map((p) =>
          h("button", { class: `btn oauth-btn oauth-${p.id}`, type: "button", onclick: async (e) => {
            e.currentTarget.disabled = true;
            rememberSpot();
            try { await api.oauth(p.id); } catch (err) { msg.textContent = err.message; e.currentTarget.disabled = false; }
          } }, brandIcon(p.paths), h("span", {}, `Continue with ${p.label}`))),
        h("p", { class: "muted small oauth-note" }, "By continuing you confirm you're 13 or older and agree to the ", h("a", { href: "rules.html", target: "_blank" }, "community rules"), " and ", h("a", { href: "privacy.html", target: "_blank" }, "privacy policy"), "."),
        h("div", { class: "or" }, h("span", {}, "or use email")));
      social.hidden = false;
    }).catch(() => {});
    const paint = () => {
      form.querySelector("h1").textContent = mode === "signup" ? "Create your account" : "Sign in";
      submit.textContent = mode === "signup" ? "Create account" : "Sign in";
      fields.hidden = mode !== "signup";
      extra.hidden = mode === "signup";
      user.required = mode === "signup";
      age.required = mode === "signup";
      pass.autocomplete = mode === "signup" ? "new-password" : "current-password";
      switcher.replaceChildren(mode === "signup" ? "Already have an account? " : "New here? ", h("a", { href: "#", onclick: (e) => { e.preventDefault(); mode = mode === "signup" ? "signin" : "signup"; msg.textContent = ""; paint(); } }, mode === "signup" ? "Sign in" : "Create an account"));
    };
    paint();
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      msg.textContent = "";
      submit.disabled = true;
      try {
        if (mode === "signup") {
          if (!/^[A-Za-z0-9_]{3,20}$/.test(user.value)) throw new Error("Usernames are 3–20 letters, numbers or underscores.");
          const res = await api.signUp(email.value.trim(), pass.value, user.value.trim());
          if (res && res.session) { await setUser(res.session.user); location.hash = "#/me"; A.toast("Welcome to Accretion"); }
          else msg.textContent = "Almost done: check your email and tap the confirmation link.";
        } else {
          const res = await api.signIn(email.value.trim(), pass.value);
          await setUser(res.user || (res.session && res.session.user));
          goBack();
          A.toast("Signed in");
        }
      } catch (err) {
        msg.textContent = err.message;
      } finally {
        submit.disabled = false;
      }
    });
    page(mode === "signup" ? "Create account" : "Sign in", form);
  }

  function reportDialog({ postId, profileId }) {
    const reason = window.prompt(postId ? "What's wrong with this post? (spam, harassment, malware link…)" : "What's wrong with this account?");
    if (!reason || !reason.trim()) return;
    api.report({ postId, profileId, reason: reason.trim().slice(0, 500) }).then(() => A.toast("Reported. Thanks, a moderator will look.")).catch((e) => A.toast(e.message));
  }

  // ---------------------------------------------------------------- wiring
  function onRoute(r) {
    const path = r.path;
    if (path === "/feed") return renderFeed(r.params || {});
    if (path === "/signin") return renderSignIn(r.params || {});
    if (path === "/me") return renderSettings();
    if (path === "/notifications") return renderNotifications();
    if (path === "/mod") return renderMod();
    const u = path.match(/^\/u\/(.+)$/);
    if (u) return renderProfile(decodeURIComponent(u[1]));
  }

  const queue = [];
  const whenReady = (fn) => (ready ? fn() : queue.push(fn));
  document.addEventListener("acc:route", (e) => whenReady(() => onRoute(e.detail)));
  document.addEventListener("acc:app", (e) => whenReady(() => renderAppSocial(e.detail)));
  document.addEventListener("acc:home", (e) => whenReady(() => renderHomeShelves(e.detail)));
  document.addEventListener("acc:track", (e) => whenReady(() => api.track(e.detail).catch(() => {})));
  document.addEventListener("acc:auth", () => {
    const r = location.hash;
    if (/^#\/(feed|u\/|notifications|mod|me)/.test(r) || r.startsWith("#/app/")) A.route();
  });

  document.addEventListener("acc:ready", async () => {
    A = window.Acc;
    $("nav-feed").hidden = false;
    renderAccount();
    try {
      await setUser(await api.load());
      if (me.user && /[?&]code=/.test(location.search)) {
        history.replaceState(null, "", location.pathname + location.hash); // tidy the address bar
        if (!location.hash.startsWith("#/me")) goBack();
      }
    } catch (e) {
      $("account").replaceChildren();
      console.warn(e);
    }
    ready = true;
    queue.splice(0).forEach((fn) => fn());
    api.trending().then((rows) => A.setTrending(rows || [])).catch(() => {});
    setInterval(() => me.user && refreshUnread(), 60000);
  });

  // ---------------------------------------------------------------- fake backend (local testing only)
  function fakeApi() {
    const users = [
      { id: "u1", username: "benwill", display_name: "Benwill", bio: "Built Accretion. Say hi.", color: "8B5CF6", role: "admin", banned: false, created_at: "2026-10-01T10:00:00Z" },
      { id: "u2", username: "sideloadr", display_name: "Side Loader", bio: "Emulators all day", color: "22D3EE", role: "user", banned: false, created_at: "2026-10-03T10:00:00Z" },
      { id: "u3", username: "modmia", display_name: "Mia", bio: "", color: "34D399", role: "mod", banned: false, created_at: "2026-10-04T10:00:00Z" },
    ];
    const t = (h) => new Date(Date.now() - h * 3600e3).toISOString();
    let pid = 10;
    const posts = [];
    const likes = new Set();
    const appLikes = new Set();
    const ratings = new Map();
    const follows = new Set(["u2>u1"]);
    const reports = [];
    const notes = [];
    const tracked = [];
    let cur = cfg.fakeUser ? users.find((u) => u.username === cfg.fakeUser) : null;
    const add = (author, body, app_id = null, parent_id = null, hours = 1) => {
      const p = { id: ++pid, author, body, app_id, parent_id, hidden: false, created_at: t(hours), edited_at: null };
      posts.push(p);
      return p;
    };
    const firstApp = () => (A && A.apps()[0] ? A.apps()[0].i : "com.example");
    const view = (p) => {
      const u = users.find((x) => x.id === p.author);
      return { ...p, username: u.username, display_name: u.display_name, color: u.color, role: u.role, likes: [...likes].filter((k) => k.startsWith(`${p.id}>`)).length, replies: posts.filter((r) => r.parent_id === p.id && !r.hidden).length };
    };
    const stat = (u) => ({ ...u, posts: posts.filter((p) => p.author === u.id && !p.hidden).length, followers: [...follows].filter((f) => f.endsWith(`>${u.id}`)).length, following: [...follows].filter((f) => f.startsWith(`${u.id}>`)).length, liked_apps: [...appLikes].filter((k) => k.endsWith(`>${u.id}`)).length });
    const visible = (p) => !p.hidden || (cur && (cur.id === p.author || ["mod", "admin"].includes(cur.role)));
    let seeded = false;
    const seed = () => {
      if (seeded || !A) return;
      seeded = true;
      const apps = A.apps().slice(0, 6).map((a) => a.i);
      const a0 = apps[0] || firstApp();
      const c1 = add("u2", "Works great on iOS 17.5, no crashes so far. The new version fixed the audio bug 🙌", a0, null, 5);
      add("u1", "Thanks for the report! Glad it's fixed. @sideloadr which device?", null, c1.id, 4);
      add("u3", "Reminder: only install from sources you trust. Report sketchy links and we'll take a look.", null, null, 2);
      add("u2", `Anyone else using this with a controller? ${apps[1] ? "" : ""}`, apps[1] || a0, null, 1);
      add("u1", "Accretion now has a feed, comments and ratings. Let me know what you think!", null, null, 0.5);
      likes.add(`${c1.id}>u1`);
      apps.slice(0, 4).forEach((a, i) => { appLikes.add(`${a}>u1`); if (i < 2) appLikes.add(`${a}>u2`); ratings.set(`${a}>u1`, 5 - i); ratings.set(`${a}>u2`, 4); ratings.set(`${a}>u3`, 5); });
      notes.push({ id: 1, user_id: "u1", actor: "u2", kind: "follow", post_id: null, read: false, created_at: t(3) });
      reports.push({ id: 1, reporter: "u2", post_id: posts[posts.length - 2].id, profile_id: null, reason: "Looks like spam", status: "open", created_at: t(1) });
    };
    const need = () => { if (!cur) throw new Error("Sign in first"); if (cur.banned) throw new Error("Your account can't do that"); };
    const delay = (v) => new Promise((r) => setTimeout(() => r(v), 30));
    const obj = {
      load: async () => (seed(), cur ? { id: cur.id, email: `${cur.username}@example.com` } : null),
      signUp: async (email, password, username) => { const u = { id: `u${users.length + 1}`, username, display_name: "", bio: "", color: "F59E0B", role: "user", banned: false, created_at: new Date().toISOString() }; users.push(u); cur = u; return { session: { user: { id: u.id, email } } }; },
      signIn: async (email) => { cur = users.find((u) => email.startsWith(u.username)) || users[1]; return { user: { id: cur.id, email } }; },
      magicLink: async () => delay(null), resetPassword: async () => delay(null),
      providers: async () => delay(cfg.fakeProviders || PROVIDERS.map((p) => p.id)),
      oauth: async (provider) => { const u = { id: `u${users.length + 1}`, username: `user_${provider}${users.length}`, display_name: `${provider} person`, bio: "", color: "3B82F6", role: "user", banned: false, created_at: new Date().toISOString() }; users.push(u); cur = u; setUser({ id: u.id, email: `${provider}@example.com` }); },
      signOut: async () => { cur = null; },
      profileById: async (id) => delay(stat(users.find((u) => u.id === id))),
      profileByName: async (n) => { const u = users.find((x) => x.username.toLowerCase() === n.toLowerCase()); return delay(u ? stat(u) : null); },
      updateProfile: async (f) => { need(); if (f.username && users.some((u) => u !== cur && u.username.toLowerCase() === f.username.toLowerCase())) throw new Error("duplicate key value violates unique constraint"); Object.assign(cur, f); },
      appStats: async () => { seed(); const ids = new Set([...[...appLikes].map((k) => k.split(">")[0]), ...[...ratings.keys()].map((k) => k.split(">")[0]), ...posts.filter((p) => p.app_id).map((p) => p.app_id)]); return [...ids].map((app_id) => { const rs = [...ratings].filter(([k]) => k.startsWith(`${app_id}>`)).map(([, v]) => v); return { app_id, likes: [...appLikes].filter((k) => k.startsWith(`${app_id}>`)).length, ratings: rs.length, avg_rating: rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : null, comments: posts.filter((p) => p.app_id === app_id && !p.hidden).length }; }); },
      appSocial: async (appId) => { seed(); const all = await obj.appStats(); return { stats: all.find((s) => s.app_id === appId) || {}, liked: Boolean(cur && appLikes.has(`${appId}>${cur.id}`)), stars: (cur && ratings.get(`${appId}>${cur.id}`)) || 0 }; },
      likeApp: async (a, on) => { need(); on ? appLikes.add(`${a}>${cur.id}`) : appLikes.delete(`${a}>${cur.id}`); },
      rateApp: async (a, s) => { need(); ratings.set(`${a}>${cur.id}`, s); },
      thread: async (appId) => delay(posts.filter((p) => p.app_id === appId && visible(p)).map(view)),
      replies: async (id) => delay(posts.filter((p) => p.parent_id === id && visible(p)).map(view)),
      feed: async ({ following, offset }) => { seed(); let list = posts.filter((p) => !p.parent_id && visible(p)); if (following) list = list.filter((p) => follows.has(`${cur.id}>${p.author}`)); return delay(list.sort((a, b) => (a.created_at < b.created_at ? 1 : -1)).slice(offset, offset + PAGE).map(view)); },
      postsBy: async (id) => delay(posts.filter((p) => p.author === id && visible(p)).sort((a, b) => (a.created_at < b.created_at ? 1 : -1)).map(view)),
      createPost: async ({ body, appId, parentId }) => { need(); const parent = parentId && posts.find((p) => p.id === parentId); const p = add(cur.id, body, parent ? parent.app_id : appId || null, parent ? parent.parent_id || parent.id : null, 0); return { id: p.id }; },
      deletePost: async (id) => { need(); const i = posts.findIndex((p) => p.id === id); posts.splice(i, 1); },
      hidePost: async (id, hidden) => { posts.find((p) => p.id === id).hidden = hidden; },
      myPostLikes: async (ids) => (cur ? ids.filter((id) => likes.has(`${id}>${cur.id}`)) : []),
      likePost: async (id, on) => { need(); on ? likes.add(`${id}>${cur.id}`) : likes.delete(`${id}>${cur.id}`); },
      isFollowing: async (id) => Boolean(cur && follows.has(`${cur.id}>${id}`)),
      follow: async (id, on) => { need(); on ? follows.add(`${cur.id}>${id}`) : follows.delete(`${cur.id}>${id}`); },
      report: async (r) => { need(); reports.push({ id: reports.length + 1, reporter: cur.id, status: "open", created_at: new Date().toISOString(), ...r }); },
      notifications: async () => notes.filter((n) => cur && n.user_id === cur.id).map((n) => ({ ...n, actor: users.find((u) => u.id === n.actor) })),
      unread: async () => notes.filter((n) => cur && n.user_id === cur.id && !n.read).length,
      markRead: async () => notes.forEach((n) => { if (cur && n.user_id === cur.id) n.read = true; }),
      reports: async () => reports.filter((r) => r.status === "open").map((r) => { const p = posts.find((x) => x.id === r.post_id); const pr = users.find((u) => u.id === r.profile_id); return { ...r, post: p ? { ...p, author_p: users.find((u) => u.id === p.author) } : null, profile: pr || null, reporter_p: users.find((u) => u.id === r.reporter) }; }),
      resolveReport: async (id, status) => { reports.find((r) => r.id === id).status = status; },
      setBanned: async (id, banned) => { users.find((u) => u.id === id).banned = banned; },
      setRole: async (username, role) => { const u = users.find((x) => x.username === username); if (!u) return []; u.role = role; return [{ username, role }]; },
      deleteAccount: async () => { users.splice(users.indexOf(cur), 1); cur = null; },
      track: async (t) => { tracked.push(t); },
      trending: async () => { seed(); return A.apps().slice(3, 9).map((a, i) => ({ app_id: a.i, searches: 12 - i, views: 30 - i, installs: 5, score: 60 - i * 5 })); },
      missing: async () => [{ query: "spotify plus", hits: 7, last_day: "2026-10-10" }, { query: "cercube", hits: 3, last_day: "2026-10-09" }],
    };
    window.__accTracked = tracked;
    return obj;
  }
})();
