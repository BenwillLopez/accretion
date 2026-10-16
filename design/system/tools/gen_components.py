# Writes project/components/<Comp>/README.md and preview.html for the Accretion design system.
# Markup is the store's own (site/index.html, app.js, social.js), styled by components/bundle.css.
import pathlib

ROOT = pathlib.Path(__file__).parent / "project" / "components"
ICON = "../../assets/Logos/accretion-icon.png"
LOGO = {
    "accretion": "../../assets/Installers/accretion.webp",
    "altstore": "../../assets/Installers/altstore.webp",
    "sidestore": "../../assets/Installers/sidestore.webp",
    "feather": "../../assets/Installers/feather.webp",
    "trollstore": "../../assets/Installers/trollstore.webp",
    "signulous": "../../assets/Installers/signulous.webp",
}
P = {
    "search": "M10.5 3a7.5 7.5 0 0 1 5.96 12.05l4.25 4.24-1.42 1.42-4.24-4.25A7.5 7.5 0 1 1 10.5 3Zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11Z",
    "heart": "M12 21s-7.5-4.6-9.6-9.4C.9 8.1 3 4.5 6.6 4.5c2 0 3.6 1.1 4.4 2.6.8-1.5 2.4-2.6 4.4-2.6 3.6 0 5.7 3.6 4.2 7.1C19.5 16.4 12 21 12 21Z",
    "bell": "M12 3a6 6 0 0 0-6 6v3.6L4.3 15.5A1 1 0 0 0 5.2 17h13.6a1 1 0 0 0 .9-1.5L18 12.6V9a6 6 0 0 0-6-6Zm-2.5 15.5a2.5 2.5 0 0 0 5 0Z",
    "download": "M12 4v11M7 10l5 5 5-5M5 19h14",
    "copy": "M9 9h10v10H9zM5 15V5h10",
    "cert": "M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6zM9 12l2 2 4-4",
}
svg = lambda name: f'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="{P[name]}"/></svg>'

C = {}

C["Backdrop"] = dict(
    group="Foundations",
    height=200,
    css="",
    html="""
<div class="backdrop" style="height:168px;border:1px solid var(--line);border-radius:var(--radius-xl);display:grid;place-items:center">
  <p class="eyebrow"><span class="live" aria-hidden="true"></span> live index · 2026-10-15 13:12 UTC</p>
</div>""",
    readme="""# Backdrop

The page background every Accretion screen sits on: `bg`, a faint 1px grid every `grid-pitch`, and two soft lights drifting over it.

## Use
- Put it on the page body, once. Content sits on `surface` cards above it; never put a backdrop inside a card.
- Paint order is fixed: colour, then the grid (`grid-line`), then the lights (`glow-accent` at 30% 25%, radius 42vmax; `glow-accent-2` at 75% 70%, radius 36vmax; both fade out by 70%).
- On the site the lights are a fixed `body::before`, 20vmax larger than the screen, moving on a 40 s `drift` loop (ease-in-out, alternating). The preview shows them still.
- With Reduce Motion (and, in the app, Low Power Mode) the lights stay still. Never animate the grid.

## Counterparts
- Site: `body` background plus `body::before` in `site/style.css`.
- App: `.accretionBackground()` (`AccretionGrid` and `AccretionAmbientGlow`, drawn at 15 fps).
""",
)

C["TopBar"] = dict(
    group="Navigation",
    height=150,
    css="body{padding:0}",
    html=f"""
<header class="top">
  <a class="brand" href="#" aria-label="Accretion home"><img src="{ICON}" alt="" width="30" height="30"><span>Accretion</span></a>
  <label class="search"><span class="sr">Search apps</span>{svg("search")}<input type="search" placeholder="Search apps, developers, bundle IDs"><kbd class="kbd" aria-hidden="true">/</kbd></label>
  <nav class="nav" aria-label="Sections"><a class="on" href="#">Discover</a><a href="#">Sources</a><a href="#">Feed</a><a href="#">Saved <span class="pill">3</span></a></nav>
  <a class="bell heart" href="#" aria-label="Support Accretion">{svg("heart")}</a>
  <a class="bell" href="#" aria-label="Notifications, 2 unread">{svg("bell")}<span class="dot">2</span></a>
  <button class="btn primary" type="button">Add source</button>
</header>""",
    readme="""# TopBar

The sticky bar at the top of every store page: brand, search, section nav, support heart, notifications and the Add source button.

## Use
- One per page, `position: sticky; top: 0`, on `bg` at 82% with a 14px backdrop blur and a `line` hairline below.
- Brand: the app icon at 30px (`radius-sm`) and "Accretion" in the `wordmark` style.
- Nav links: `control` style in `muted`; the current section is `fg` on `raised`. Sections are Discover, Sources, Feed, Saved, in that order (the app's Discover tab has the same four).
- The Saved count is a `pill`; the unread count is a `dot` on `rose-fill` with `on-accent` text.
- Add source is the one primary button on the page.
- Under 760px the search moves to its own full-width row and the nav spreads across the bottom; the heart moves into the nav.

## Consumer provides
The current section (`.on`), the saved and unread counts, and the signed-in account menu (`#account`).
""",
)

C["SearchField"] = dict(
    group="Navigation",
    height=136,
    css=".stack{display:grid;gap:12px;max-width:560px}",
    html=f"""
<div class="stack">
  <label class="search"><span class="sr">Search apps</span>{svg("search")}<input type="search" placeholder="Search apps, developers, bundle IDs"><kbd class="kbd" aria-hidden="true">/</kbd></label>
  <label class="search" style="border-color:var(--accent)"><span class="sr">Search apps</span>{svg("search")}<input type="search" value="emulator"></label>
</div>""",
    readme="""# SearchField

The store's search: one field for app names, developers and bundle IDs, with a `/` shortcut hint.

## Use
- A `surface` field with a `line-strong` edge, `radius-md`, 17px search glyph in `muted`. Focus turns the edge `accent` (second row).
- Placeholder wording: "Search apps, developers, bundle IDs".
- The `/` hint (`kbd`) shows only where there is a keyboard (`@media (hover: none)` hides it).
- Keep a visually hidden label ("Search apps").

## Refined
The site draws the edge in `line` (1.3:1) at 11px radius; this system uses `line-strong` (3:1) and `radius-md`.
""",
)

C["Tabs"] = dict(
    group="Navigation",
    height=80,
    css="",
    html="""
<nav class="tabs" aria-label="Profile"><a class="on" href="#" aria-current="page">Posts</a><a href="#">Replies</a><a href="#">Likes</a></nav>""",
    readme="""# Tabs

Underlined tabs that switch between lists on one page (profile posts and replies, notification kinds, moderation queues).

## Use
- Links in the `control` weight, `muted`; the current tab is `fg` with a 2px `accent` underline sitting on the `line` hairline.
- Mark the current tab with `aria-current="page"` as well as `.on`.
- For switching whole sections use the TopBar nav, not tabs.
""",
)

C["Button"] = dict(
    group="Actions",
    height=130,
    css="",
    html="""
<div class="actions">
  <button class="btn primary" type="button">Install</button>
  <button class="btn" type="button">More ways ▾</button>
  <button class="btn ghost" type="button">Close</button>
  <button class="btn on" type="button">✓ Saved</button>
  <button class="btn danger" type="button">Delete account</button>
</div>
<div class="actions" style="margin-top:12px">
  <button class="btn compact" type="button">Copy link</button>
  <button class="btn compact primary" type="button">Open in Accretion</button>
  <button class="btn" type="button" disabled>Show more</button>
</div>""",
    readme="""# Button

The store's one button shape: 40px tall (`tap-min`), `radius-md`, `control` text, in five kinds.

## Kinds
- `.btn`: the default, `raised` fill with a `line` edge that turns `accent` on hover.
- `.btn.primary`: the main action of a view (Install, Add source, Open in Accretion). A 135deg gradient from `accent-fill` to `accent-fill-end` with `on-accent` text. One per view.
- `.btn.ghost`: no fill, for Close and Back.
- `.btn.on`: a kept state (Saved, Liked, Following): `good` edge and text, with a check in the label.
- `.btn.danger`: destructive actions, `rose` text and edge. Confirm before acting.
- `.compact` (34px, 13px text) for dense rows; `[disabled]` at `opacity-disabled`.

## Wording
Verbs in sentence case: "Install", "Add source", "Copy link", "Show more". A menu opener ends in ▾.

## Counterparts
App: `AccretionButtonStyle(prominent:ghost:on:compact:)`, which also dims to `opacity-pressed` and scales to 0.96 while held.

## Refined
The site's primary gradient runs `accent` to a 55% mix with `accent-2`; in dark that gives white text 4.2:1 and 3.0:1. `accent-fill` and `accent-fill-end` keep the look at 4.5:1 or more.
""",
)

C["Chip"] = dict(
    group="Actions",
    height=80,
    css="",
    html="""
<div class="chips" role="tablist" aria-label="Categories">
  <button class="chip" role="tab" aria-selected="true">All <span>4,268</span></button>
  <button class="chip" role="tab" aria-selected="false">Games <span>1,021</span></button>
  <button class="chip" role="tab" aria-selected="false">Utilities <span>434</span></button>
  <button class="chip" role="tab" aria-selected="false">Photo &amp; Video <span>341</span></button>
  <button class="chip" role="tab" aria-selected="false">Entertainment <span>213</span></button>
  <button class="chip" role="tab" aria-selected="false">Developer <span>96</span></button>
</div>""",
    readme="""# Chip

A pill that filters a list by category, with the count in mono beside the name.

## Use
- `chip-label` text on `surface` with a `line` edge, `radius-pill`; the count in 11px mono `muted`.
- The selected chip inverts: `fg` fill, `bg` text. Exactly one is selected; mark it with `aria-selected="true"` in a `tablist`.
- The categories, in order: All, Games, Utilities, Photo & Video, Entertainment, Social, Lifestyle, Developer, Other.
- On phones the row scrolls sideways; with a mouse it wraps.
""",
)

C["Toggle"] = dict(
    group="Actions",
    height=80,
    css="",
    html="""
<div class="actions" style="align-items:center">
  <button class="toggle" type="button" aria-pressed="false">Fits my iOS</button>
  <button class="toggle" type="button" aria-pressed="true">✓ Fits iOS 18.1</button>
  <label><span class="sr">Sort</span><select class="select"><option>Recently updated</option><option>Most popular</option><option>Newest apps</option><option>Name A–Z</option><option>Largest</option></select></label>
</div>""",
    readme="""# Toggle

An on/off filter button (Fits my iOS), shown beside the sort menu above the app grid.

## Use
- Off: `muted` text on `surface`, `line` edge, `radius-md`.
- On: `good` text and a `good`-tinted fill, with a check and the specific value in the label ("✓ Fits iOS 18.1").
- Use `aria-pressed`. A toggle filters; for an action use a Button.
- The sort `select` sits beside it with the five sorts, in this order: Recently updated, Most popular, Newest apps, Name A–Z, Largest.
""",
)

C["Input"] = dict(
    group="Forms",
    height=306,
    css=".form{display:grid;gap:8px;max-width:520px}",
    html="""
<form class="form" onsubmit="return false">
  <label class="label" for="n">Display name</label>
  <input class="input" id="n" value="nova">
  <label class="label" for="b">Bio</label>
  <textarea class="input" id="b" rows="2" placeholder="A line about you"></textarea>
  <label class="label" for="s">Show my posts to</label>
  <select class="select" id="s"><option>Everyone</option><option>Signed-in people</option></select>
  <p class="form-msg" role="status">Saved.</p>
</form>""",
    readme="""# Input

Text fields, text areas and selects in forms (account settings, sign in, the composer, Install any IPA).

## Use
- Label above the field in the `eyebrow` mono style (12px, uppercase, `muted`).
- Field: `surface` fill, `line-strong` edge, `radius-md`, 10px 12px padding, inheriting `body` text. Focus turns the edge `accent`.
- Messages after saving go in `.form-msg` (`link` colour, `role="status"`); errors say what to do next in plain words.
- URLs, keys and file names go in the `code` mono style.

## Refined
The site's fields use a `line` edge (1.3:1 against the page); `line-strong` makes the edge 3:1.
""",
)

C["Badge"] = dict(
    group="Status",
    height=80,
    css="",
    html="""
<div class="actions" style="align-items:center">
  <span class="badge">New</span>
  <span class="badge">Update</span>
  <span class="badge hot">Hot</span>
  <span class="badge core">Core</span>
  <span class="badge mod">Accretion Mod</span>
  <span class="badge supporter">Supporter</span>
  <span class="badge role-admin">Admin</span>
  <span class="badge role-mod">Mod</span>
  <span class="badge hidden-badge">Hidden</span>
</div>""",
    readme="""# Badge

A small uppercase mono label beside a name: New, Update, Hot, Core, Accretion Mod, Supporter, roles.

## Use
- `badge` text style, `radius-xs`, the colour on a 14% tint of itself. The word carries the meaning; colour only reinforces it.
- Tones: New and Update in `good`; Hot in `link`; Core and Accretion Mod in `accent-text`; Supporter and Admin in `rose`; Mod in `good`; Hidden in `warn`.
- One or two words. Never a badge without words, and at most two on one row.

## Counterparts
App: `AccretionBadge(text:color:)`.

## Refined
The site tints at 18 to 22% with 600 weight (faked, since only 400 and 500 load). This system uses 14% and 500, and text tokens that read at 4.5:1 or more on the tint in both themes.
""",
)

C["LiveDot"] = dict(
    group="Status",
    height=110,
    css=".stack{display:grid;gap:12px}",
    html="""
<div class="stack">
  <p class="eyebrow"><span class="live" aria-hidden="true"></span> live index · 2026-10-15 13:12 UTC</p>
  <p class="eyebrow"><span class="live warn" aria-hidden="true"></span> index 14 h old</p>
  <p class="eyebrow"><span class="live bad" aria-hidden="true"></span> index over a day old</p>
</div>""",
    readme="""# LiveDot

An 8px status dot with a ring that pulses outward every 2.4 s, beside the eyebrow line that says what it means.

## Use
- `good`: the store index rebuilt within 8 hours (it rebuilds every 6). `warn`: within a day. `bad`: older.
- Always next to words that state the status (the build time, "index 14 h old"); the dot is `aria-hidden`.
- Still with Reduce Motion.

## Counterparts
App: `LiveDot(tone:)` with `LiveDot.Tone.freshness(_:)` for the same thresholds.
""",
)

C["Rating"] = dict(
    group="Status",
    height=80,
    css="",
    html="""
<div class="actions" style="align-items:center">
  <div class="stars" role="radiogroup" aria-label="Your rating">
    <button class="star on" role="radio" aria-checked="false" aria-label="1 star">★</button><button class="star on" role="radio" aria-checked="false" aria-label="2 stars">★</button><button class="star on" role="radio" aria-checked="false" aria-label="3 stars">★</button><button class="star on" role="radio" aria-checked="true" aria-label="4 stars">★</button><button class="star" role="radio" aria-checked="false" aria-label="5 stars">★</button>
  </div>
  <span class="muted small">4.2 · 18 ratings</span>
</div>""",
    readme="""# Rating

Five stars for rating an app, with the average and count beside them.

## Use
- 24px ★ glyphs; filled in `star`, empty in `line-strong`. Hover and focus preview the fill.
- A radiogroup with one radio per star, labelled "1 star" to "5 stars".
- Always show the number and count as text ("4.2 · 18 ratings").

## Refined
The site's empty stars use `line` (1.3:1) and the filled `#f5b83b` reads 1.8:1 on white. This system uses `line-strong` and a darker `star` in light.
""",
)

C["StatTile"] = dict(
    group="Data",
    height=330,
    css=".stack{display:grid;gap:16px}.stats{max-width:420px}",
    html="""
<div class="stack">
  <dl class="stats">
    <div><dt>apps</dt><dd>4,268</dd></div>
    <div><dt>sources</dt><dd>163</dd></div>
    <div><dt>updated 7d</dt><dd>868</dd></div>
    <div><dt>new 30d</dt><dd>382</dd></div>
  </dl>
  <div class="st-grid">
    <div class="st-tile"><span class="st-label">Dead links purged</span><span class="st-value">8,782</span><p class="st-note">since the last full scan</p></div>
    <div class="st-tile"><span class="st-label">Updated 7d</span><span class="st-value good">868</span><p class="st-note">20% of all apps</p></div>
    <div class="st-tile"><span class="st-label">Failed spec</span><span class="st-value warn">6,613</span><p class="st-note">listings skipped</p></div>
  </div>
</div>""",
    readme="""# StatTile

A number with a mono label: the hero's four tiles (apps, sources, updated 7d, new 30d) and the Status page's grid.

## Use
- Hero tiles (`.stats`): a 2-by-2 grid, label in the `label` style, number at 26px Sora in the headline gradient (`fg` to `headline-end`).
- Status tiles (`.st-tile`): the `stat` style; colour the number only when it is a judgement (`good` for healthy, `warn` for needs attention), with a note under it.
- Numbers use tabular figures and thousands separators.
- On desktop the hero hides its tiles because the live index card shows the same numbers.
""",
)

C["Fact"] = dict(
    group="Data",
    height=120,
    css="",
    html="""
<dl class="facts">
  <div><dt>Version</dt><dd>4.0.2</dd></div>
  <div><dt>Size</dt><dd>38 MB</dd></div>
  <div><dt>Updated</dt><dd>2 days ago</dd></div>
  <div><dt>Needs</dt><dd>iOS 15.0</dd></div>
  <div><dt>Bundle ID</dt><dd>com.example.pixellab</dd></div>
</dl>""",
    readme="""# Fact

One label-and-value cell in an app page's facts grid: Version, Size, Updated, Needs, Bundle ID, Source.

## Use
- Label in 10.5px mono uppercase `muted`; value in `body-strong`. A missing value shows "–".
- Cells are `surface` with a `line` edge and `radius-lg`, in a grid of at least 140px columns.
- Values wrap anywhere (bundle IDs are long) and use tabular figures.

## Counterparts
App: `AccretionFact(label:value:)`.
""",
)

C["Section"] = dict(
    group="Containers",
    height=250,
    css="",
    html="""
<section class="sec"><h2>What's new</h2><p class="prose">Faster search on large sources.
Fixed a crash when opening an app with no screenshots.</p></section>
<section class="sec"><h2>About</h2><p class="prose">Pixel Lab is a pixel-art editor with layers, palettes and animation preview.</p></section>""",
    readme="""# Section

The card that holds one part of a page (What's new, Screenshots, About, Versions, Permissions, Info), headed by a small mono label.

## Use
- `surface` with a `line` edge, `radius-xl`, 16px 18px padding; stacked 12px apart.
- Heading in the `label` style (uppercase, `muted`). Content below in `body`; long text keeps its line breaks and stays under 75ch.
- Don't nest sections; use rows or facts inside one.

## Counterparts
App: `AccretionSection(_ title:content:)` and the `.accretionCard()` modifier.
""",
)

C["Dialog"] = dict(
    group="Containers",
    height=400,
    css="",
    html="""
<div class="add" role="dialog" aria-labelledby="t" style="margin:0 auto">
  <form class="add-inner" onsubmit="return false">
    <h2 id="t">Add Accretion to your app</h2>
    <p class="muted">Pick a list, then open it in your app or copy the link.</p>
    <div class="seg" role="radiogroup" aria-label="Which list">
      <label><input type="radio" name="list" checked> <span><b>Full</b> every source</span></label>
      <label><input type="radio" name="list"> <span><b>Core</b> hand-picked, lighter</span></label>
    </div>
    <code class="url">https://getaccretion.app/source.json</code>
    <div class="actions">
      <a class="btn primary" href="#">Open in Accretion</a><a class="btn" href="#">Open in AltStore</a><button class="btn" type="button">Copy link</button>
    </div>
    <button class="btn ghost" type="button" style="justify-self:end">Close</button>
  </form>
</div>""",
    readme="""# Dialog

A modal card for a short task: add the source, more ways to install, the download screen, picking an installer.

## Use
- A native `<dialog>` opened with `showModal()`: `surface`, `line` edge, `radius-2xl`, at most `form-max` wide, 22px padding; the page behind gets `scrim` and a 4px blur.
- Title in `section-title`, one `muted` sentence saying what to do, then the choices, then actions with one primary. Close is a ghost button at the end.
- Choose-one options use the segmented `.seg` grid; a link to copy goes in a `.url` well (`code` style on `raised`, select-all).
- The preview shows it inline; on the page it floats over the scrim.
""",
)

C["Toast"] = dict(
    group="Containers",
    height=80,
    css="",
    html="""
<div class="actions"><div class="toast" role="status">IPA link copied</div><div class="toast" role="status">Saved</div></div>""",
    readme="""# Toast

A short confirmation that floats at the bottom centre for a moment after an action (copied, saved, reported).

## Use
- Inverted: `fg` fill, `bg` text, `radius-md`, 14px semibold. One at a time, `role="status"`.
- Two or three words that name what happened ("IPA link copied"). No buttons in it; nothing that needs reading twice.
- It rises 20px and fades in over 0.2 s, then fades out.
""",
)

C["EmptyState"] = dict(
    group="Containers",
    height=280,
    css="",
    html=f"""
<div class="empty-state">
  {svg("heart")}
  <h3>No saved apps yet</h3>
  <p>Tap Save on any app to keep it here. You'll see when it updates.</p>
  <a class="btn" href="#">Browse apps</a>
</div>""",
    readme="""# EmptyState

What a list shows when it has nothing in it yet: an outline glyph, a title, one helpful sentence, and an action when there is one.

## Use
- 40px glyph in `muted` outline, title in `section-title`, message in `muted`, at most 40ch, centred.
- Say what will appear here and how to get it ("Tap Save on any app to keep it here"). Never just "No results".
- A search with no results also offers the closest matches below.

## Counterparts
App: `AccretionEmptyState(title:message:systemImage:actions:)` with an SF Symbol. The site's `.empty` is the text-only form.
""",
)

C["AppCard"] = dict(
    group="Store",
    height=200,
    css="",
    html=f"""
<div class="grid">
  <a class="card" href="#"><img class="icon" src="{ICON}" alt=""><div class="card-body"><div class="card-name"><span>Accretion</span><span class="badge core">Core</span></div><div class="card-dev">GETAccretion</div><div class="card-meta"><span class="v">v1.0.25</span><span>18 MB</span><span>today</span></div></div></a>
  <a class="card" href="#"><span class="icon ph" aria-hidden="true">P</span><div class="card-body"><div class="card-name"><span>Pixel Lab</span><span class="badge">New</span></div><div class="card-dev">Example Studio</div><div class="card-meta"><span class="v">v4.0.2</span><span>38 MB</span><span>2d ago</span></div></div></a>
  <a class="card" href="#"><span class="icon ph" aria-hidden="true">R</span><div class="card-body"><div class="card-name"><span>Retro Arcade Collection Deluxe</span></div><div class="card-dev">Example Games</div><div class="card-meta"><span class="v">v2.3</span><span>212 MB</span><span>3w ago</span></div></div></a>
</div>""",
    readme="""# AppCard

One app in the All apps grid: icon, name with a badge, developer, and a mono meta line (version, size, last update).

## Use
- `surface` card, `line` edge turning `accent` on hover (with a 1px lift unless Reduce Motion), `radius-xl`, 13px padding.
- Icon at `icon-card` with `radius-icon`. With no icon, the first letter in Sora on `raised` (`.icon.ph`).
- Name in `body-strong`, one line with ellipsis; at most one badge after it.
- Meta in the `meta` style: the version in `link`, then size and age.
- Grid columns are at least `card-min` wide, 12px apart; 60 cards a page.

## Counterparts
App: `StoreAppCard` in `DiscoverView.swift`.
""",
)

C["Shelf"] = dict(
    group="Store",
    height=340,
    css=".shelf{max-width:520px}",
    html="""
<section class="shelf">
  <div class="shelf-head"><h2>Most popular<span>this week</span></h2><div class="shelf-tools"><a href="#">See all</a><div class="shelf-nav"><button type="button" aria-label="Previous page">‹</button><button type="button" aria-label="Next page">›</button></div></div></div>
  <ol class="shelf-list">
    <li><a class="row" href="#"><span class="row-rank">1</span><span class="icon ph row-icon" aria-hidden="true">P</span><span class="row-body"><span class="row-name">Pixel Lab</span><span class="row-meta"><span class="badge">New</span>Graphics · v4.0.2</span></span><span class="row-go" aria-hidden="true">›</span></a></li>
    <li><a class="row" href="#"><span class="row-rank">2</span><span class="icon ph row-icon" aria-hidden="true">T</span><span class="row-body"><span class="row-name">Tide Player</span><span class="row-meta">Music · v1.9</span></span><span class="row-go" aria-hidden="true">›</span></a></li>
    <li><a class="row" href="#"><span class="row-rank">3</span><span class="icon ph row-icon" aria-hidden="true">N</span><span class="row-body"><span class="row-name">Notes Plus</span><span class="row-meta"><span class="badge mod">Accretion Mod</span>Productivity · v7.1</span></span><span class="row-go" aria-hidden="true">›</span></a></li>
    <li><a class="row" href="#"><span class="row-rank">4</span><span class="icon ph row-icon" aria-hidden="true">R</span><span class="row-body"><span class="row-name">Retro Arcade</span><span class="row-meta">Games · v2.3</span></span><span class="row-go" aria-hidden="true">›</span></a></li>
  </ol>
</section>""",
    readme="""# Shelf

A titled, ranked list of apps on the home page (Most popular, Fresh today, New this month, Games), paged sideways.

## Use
- Heading in `section-title` with a `muted` mono note ("this week"); See all and the page arrows on the right. Arrows show only with a mouse.
- Rows: rank in the `rank` style, icon at `icon-row` with a `line` edge, name in `body-strong` (turns `accent-text` on hover), meta in `meta` with an optional badge, and a `muted` › at the end. Rows are split by `line` hairlines.
- 5 rows a page, up to 20 apps. Shelves sit in columns at least `shelf-min` wide, 28px apart; a shelf with one or two apps becomes a full-width strip.
- Shelf order on home: Most popular, Made by Accretion, Updates for your saved apps, Fresh today, New this month, From Accretion Core, Games, community shelves, Utilities.

## Counterparts
App: `StoreShelfView` and `StoreAppRow`.
""",
)

C["AppHeader"] = dict(
    group="Store",
    height=230,
    css="",
    html="""
<header class="d-head">
  <span class="icon ph d-icon" aria-hidden="true">P</span>
  <div class="d-main">
    <h1 class="d-name">Pixel Lab</h1>
    <p class="d-dev">Example Studio · <span class="badge">Update</span></p>
    <div class="actions"><button class="btn primary" type="button">Install</button><button class="btn" type="button">More ways ▾</button><button class="btn" type="button">♡ Save</button><button class="btn ghost" type="button">Share</button></div>
  </div>
</header>""",
    readme="""# AppHeader

The top of an app page: big icon, name, developer, and the install actions, with a soft light in the app's own colour.

## Use
- `surface` panel, `line` edge, `radius-2xl`, 22px padding. A radial light in `--tint` (the app's icon colour, else `accent`) at 30% sits top right.
- Icon at `icon-hero` with `radius-icon`; name in `app-title`; developer in `muted`.
- Actions in this order: Install (primary, opens the chosen installer), More ways ▾ (the InstallWays dialog), Save, Share. Below it, "Need a signing certificate?" with links in `small`.
- Under 560px the icon drops to 80px and the name to 22px.

## Consumer provides
The app, its tint colour (`style="--tint: …"`) and the chosen installer.
""",
)

C["InstallWays"] = dict(
    group="Store",
    height=464,
    css=".ways{max-width:520px}",
    html=f"""
<ul class="ways" aria-label="More ways to install">
  <li><a class="way" href="#"><span class="way-ic logo"><img src="{LOGO["accretion"]}" alt=""></span><span class="way-txt"><b>Accretion</b><span class="muted small">Our app: signs and installs with your own certificate.</span></span><span class="way-go" aria-hidden="true">›</span></a></li>
  <li><a class="way" href="#"><span class="way-ic logo"><img src="{LOGO["feather"]}" alt=""></span><span class="way-txt"><b>Feather</b><span class="muted small">Signs and installs with your own certificate (2.0 or newer).</span></span><span class="way-go" aria-hidden="true">›</span></a></li>
  <li><a class="way" href="#"><span class="way-ic logo"><img src="{LOGO["altstore"]}" alt=""></span><span class="way-txt"><b>AltStore</b><span class="muted small">Signs with your Apple ID, refreshes every 7 days.</span></span><span class="way-go" aria-hidden="true">›</span></a></li>
  <li><a class="way" href="#"><span class="way-ic logo"><img src="{LOGO["sidestore"]}" alt=""></span><span class="way-txt"><b>SideStore</b><span class="muted small">Signs with your Apple ID, refreshes on the phone.</span></span><span class="way-go" aria-hidden="true">›</span></a></li>
  <li><a class="way" href="#"><span class="way-ic">{svg("download")}</span><span class="way-txt"><b>Download IPA</b><span class="muted small">Save the file and sign it yourself.</span></span><span class="way-go" aria-hidden="true">›</span></a></li>
  <li><a class="way" href="#"><span class="way-ic">{svg("copy")}</span><span class="way-txt"><b>Copy IPA link</b></span><span class="way-go" aria-hidden="true">›</span></a></li>
  <li><a class="way" href="#"><span class="way-ic logo"><img src="{LOGO["signulous"]}" alt=""></span><span class="way-txt"><b>Signulous</b><span class="muted small">Install apps from your iPhone for a year, no computer needed.</span></span><span class="way-go" aria-hidden="true">›</span></a></li>
</ul>""",
    readme="""# InstallWays

The list of every way to get an app (installers, Download IPA, Copy IPA link, certificates), one row each, inside the More ways dialog.

## Use
- One `surface` list with `line` dividers and `radius-xl`; each row has a 32px icon, a bold name, an optional `muted` note, and a ›.
- Installers show their own logo (`assets/Installers`, 32px, with a faint ring). Actions use the stroke glyphs (`assets/Icons`: download, copy, cert) in `accent-text` on a 16% `accent` tint.
- Notes say how each one signs, in one short sentence: "Signs with your Apple ID, refreshes every 7 days."
- Order: installers (Accretion, Feather, AltStore, SideStore, TrollStore), then the file actions, then certificate sellers from `support.json` with their own note.

## Counterparts
App: the install sheet.
""",
)

C["Avatar"] = dict(
    group="Community",
    height=100,
    css="",
    html="""
<div class="actions" style="align-items:center">
  <span class="avatar" style="--c:var(--avatar-violet);width:40px;height:40px">N</span>
  <span class="avatar" style="--c:var(--avatar-cyan);width:40px;height:40px">K</span>
  <span class="avatar" style="--c:var(--avatar-green);width:40px;height:40px">M</span>
  <span class="avatar" style="--c:var(--avatar-amber);width:40px;height:40px">A</span>
  <span class="avatar" style="--c:var(--avatar-rose);width:40px;height:40px">S</span>
  <span class="avatar" style="--c:var(--avatar-blue);width:40px;height:40px">J</span>
  <span class="avatar" style="--c:var(--avatar-pink);width:40px;height:40px">E</span>
  <span class="avatar" style="--c:var(--avatar-lime);width:40px;height:40px">L</span>
  <span class="avatar" style="--c:var(--avatar-violet);width:64px;height:64px;font-size:26px">N</span>
</div>""",
    readme="""# Avatar

A person's round initial in the colour they picked: one of the eight `avatar-*` tokens, lit from the top left.

## Use
- Set `--c` to one avatar token and the size inline (28px in lists, 40px in posts, 64 to 88px on a profile). Initials in Sora 700 at about 40% of the size.
- Initials in `avatar-ink`. No photos: the store keeps profiles to a name and a colour.
- The colour picker shows the eight as 32px `swatch` circles; the chosen one has an `fg` ring.

## Refined
The site draws white initials with a text shadow, 1.5:1 to 4.2:1 on these colours. `avatar-ink` reads at 4.5:1 or more on all eight; the gradient's dark end is lighter (80% of the colour, was 60%) to keep it.
""",
)

C["Post"] = dict(
    group="Community",
    height=290,
    css="",
    html="""
<article class="post">
  <span class="avatar" style="--c:var(--avatar-cyan);width:40px;height:40px">K</span>
  <div class="post-main">
    <div class="post-head"><a class="post-name" href="#">Kai</a><span class="badge supporter">Supporter</span><span class="post-user">@kai</span><span class="post-time">· 2h</span></div>
    <p class="post-body">The new version fixed the export crash for me. Signing with Accretion worked first try.</p>
    <a class="app-chip" href="#"><span class="icon ph chip-icon" aria-hidden="true">P</span><span>Pixel Lab</span></a>
    <div class="post-acts"><button class="act" type="button">Reply</button><button class="act like on" type="button" aria-pressed="true">♥ 12</button><button class="act" type="button">Report</button></div>
  </div>
</article>
<article class="post hidden-post">
  <span class="avatar" style="--c:var(--avatar-amber);width:40px;height:40px">A</span>
  <div class="post-main">
    <div class="post-head"><a class="post-name" href="#">Ari</a><span class="badge hidden-badge">Hidden</span><span class="post-time">· 1d</span></div>
    <p class="post-body">Hidden by a moderator.</p>
    <div class="post-acts"><button class="act mod" type="button">Unhide</button></div>
  </div>
</article>""",
    readme="""# Post

One community post or reply: avatar, name and handle, the text, an optional app chip, and actions (Reply, Like, Report).

## Use
- Avatar at 40px, then name in `body-strong`, badges, `@handle` and age in `muted` 13px.
- Text keeps its line breaks and wraps anywhere. An app it mentions shows as an `app-chip` (26px icon and name).
- Actions are text buttons in `muted` that light up on `raised` when hovered; a liked post's ♥ is `rose`; moderator actions are `warn`.
- A hidden post stays in place at `opacity-hidden` with a Hidden badge, so threads still read.
- Replies indent 48px (22px on phones).

## Counterparts
App: `CommunityFeedView` and `FeedThreadView` in `CommunityViews.swift`.
""",
)

TEMPLATE = """<!-- @dsCard group="{group}" height={height} -->
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{name}</title>
<style>body{{padding:16px}}{css}</style>
</head>
<body>{html}
</body>
</html>
"""

for name, c in C.items():
    d = ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "preview.html").write_text(TEMPLATE.format(name=name, **c), encoding="utf-8", newline="\n")
    (d / "README.md").write_text(c["readme"].lstrip(), encoding="utf-8", newline="\n")
print(len(C), "components")
