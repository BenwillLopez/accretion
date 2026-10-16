Accretion is one store across two surfaces: the web store at getaccretion.app and the iOS app (a fork of Feather). Both must look and read the same, 1:1: same colours, buttons, sections and words. Build anything new from these tokens and components, and change both surfaces together.

## Content fundamentals

**Voice.** Plain, short and concrete, like a well-run index. State what something does and what it costs you (time, a certificate, a refresh) in one sentence. No hype, no exclamation marks, no "simply" or "just".

- Speak to the reader as "you"; Accretion speaks as "we" or "our" only about itself ("Our app: signs and installs with your own certificate.").
- Sentence case everywhere: headings, buttons, nav ("Add source", "Sign your own apps", "More ways to install").
- Numbers are real and specific, with separators: "4,268 apps", "160+ sources", "refreshes every 7 days". Ages read "2d ago", "3w ago"; build times in UTC ("2026-10-15 13:12 UTC").
- Buttons are verbs: Install, Add source, Copy link, Show more, Save. A menu opener ends in ▾ ("More ways ▾"); Back starts with ←.
- Join facts with a middle dot: "Graphics · v4.0.2", "live index · 2026-10-15". An empty value is an en dash "–".
- Confirmations name what happened in two or three words: "IPA link copied", "Saved".
- Empty states say what will appear and how: "Tap Save on any app to keep it here."
- Be honest about risk without alarm: "Third-party apps are not reviewed, so install what you trust."
- Release notes and What's new posts say what changed in plain words ("Install server: clearer test results"), never how a signing or install problem was solved.

Real lines to model: the headline "Every source, pulled into one."; the lede "Apps from 160+ public AltStore and SideStore sources, merged and cleaned. One entry per app, always the newest version."; the install note "Signs with your Apple ID, refreshes every 7 days."

**Emoji.** Almost none. The only emoji in the product is ✍️ on the "Sign your own apps" link. Text glyphs carry meaning instead: › (open), ▾ (menu), ← (back), ★ (rating), ♥ (like, support), ✓ (a kept state).

## Visual foundations

**Dark first.** Dark is the default theme and the brand's face; light follows the system setting or a manual switch. Every token has both values; check both.

**Colour.** Neutral violet-black grounds (`bg`, `surface`, `raised`) with two brand hues: violet `accent` and cyan `accent-2`.
- Text is `fg`, secondary text `muted`. Violet as text is `accent-text`; links and version numbers are `link`. Never set body text in `accent` or `accent-2`.
- Primary actions use the `accent-fill` → `accent-fill-end` gradient with `on-accent` text. One primary per view.
- Status: `good` (working, new, saved), `warn` (behind, needs attention), `bad` (down). Always with a word; colour only reinforces it. Support, likes and destructive actions use `rose`.
- Hairlines are `line` and are decorative; the edge of a text field, select or segmented choice is `line-strong`.

**Gradients, and only these:** the primary button (`accent-fill` → `accent-fill-end`, 135deg); the headline and stat numbers as text (`fg` at 30% → `headline-end`, 100deg); bars and chart lines (`accent` → `accent-2`); the ambient lights. No gradient cards, no gradient borders.

**The ground.** Every page sits on the Backdrop: `bg`, a 1px `grid-line` every `grid-pitch` (28px), and two soft lights (`glow-accent`, `glow-accent-2`) drifting over it. Content lives on `surface` cards above it.

**Type.** Three families, each with one job.
- Sora (`display`, 600 and 700) for headings and numbers: `headline` (hero only, in the text gradient), `page-title`, `app-title`, `stat`, `section-title`, `subhead`, `wordmark`.
- The system UI font (`body`; SF Pro on Apple devices) for reading and controls: `body` at 15px/1.5 is the base; `body-strong` for names; `control` for buttons and nav; `small` for helper lines.
- JetBrains Mono (`mono`, 400 and 500) for data and labels: uppercase `label` and `eyebrow` with wide tracking, `meta` lines, `badge`, `code` for URLs and keys, `rank`. Numbers use tabular figures.
Load only 400 and 500 of the mono and 600 and 700 of Sora; don't ask for weights that aren't loaded.

**Shape.** Borders, not shadows: cards are `surface` with a 1px `line` edge and no drop shadow. Corners follow the radius scale: `radius-xs` badges, `radius-sm` small controls, `radius-md` buttons and fields, `radius-lg` tiles and rows, `radius-xl` cards and sections, `radius-2xl` panels and dialogs, `radius-pill` chips. App icons use `radius-icon` (23% of their size) at `icon-chip`, `icon-row`, `icon-card` or `icon-hero`.

**Space and layout.** The spacing scale runs `space-2` to `space-40`. Gaps are mostly `space-8` to `space-12`; card padding 13 to 18px; panels 22px. Pages: home up to `page-max` with side padding from `space-16` (phones) to `space-40`; views and app pages `content-max`; reading pages `prose-max`; forms and dialogs `form-max`. Buttons are at least `tap-min` tall. Shelves flow into 1 to 4 columns at least `shelf-min` wide; the app grid uses `card-min` columns.

**States.** Hover: a `line` edge turns `accent` (cards mix 60% toward it). Focus: a 2px `accent-2` outline offset 2px on everything focusable; fields turn their edge `accent`. Selected: chips invert to `fg`; nav and tabs go `fg` (on `raised`, or over an `accent` underline). On: `good` text and edge with a ✓. Disabled: `opacity-disabled`. Hidden by a moderator: `opacity-hidden`.

**Motion.** Small and slow. Cards lift 1px over 0.15 s on hover; the live dot pulses every 2.4 s; the ambient lights drift over 40 s; toasts rise and fade over 0.2 s. In the app, buttons dim to `opacity-pressed` and shrink to 0.96 on a spring (response 0.25, damping 0.7). With Reduce Motion everything moving stops; the app also stills the lights in Low Power Mode.

**Imagery.** The store shows app icons and app screenshots only (screenshots 360px tall, `radius-xl`, `line` edge, snapping sideways). Brand imagery is the ringed-star mark on a starfield (`assets/Logos`). No stock photos or illustrations.

## Iconography

- **Brand mark:** the app icon, a bright star inside tilted violet-to-pink-to-cream rings (`assets/Logos/accretion-icon.png`). In the top bar it sits at 30px with `radius-sm` beside the `wordmark`. There is no separate vector logo; the wordmark is set in Sora 700, not drawn.
- **Web glyphs:** a handful of 24px inline SVGs drawn in the text colour (`currentColor`). Filled: search, heart, bell. Stroked at 2px with round caps and joins: download, copy, cert. Copies are in `assets/Icons`; there is no icon font.
- **App glyphs:** SF Symbols, at matching weight, in the same colour tokens.
- **Installer and seller logos:** each third-party installer's own icon at 32px (`assets/Installers`), used only to identify that installer. Never recolour or crop them.
- **Text glyphs** stand in for small icons: › ▾ ← ★ ♥ ✓.

## Platform parity

| Site (`site/style.css`) | App (`AccretionTheme.swift`) | This system |
|---|---|---|
| `--bg`, `--surface`, … `--bad` | `AccretionTheme.bg` … `.bad` | colour tokens of the same names |
| `--display`, `--body`, `--mono` | `Font.accretionDisplay`, `.system`, `Font.accretionMono` | `--font-display`, `--font-body`, `--font-mono` |
| `--radius` (14px) | `AccretionTheme.radius` | `radius-xl` |
| `.btn`, `.btn.primary`, `.ghost`, `.on` | `AccretionButtonStyle` | Button |
| `.badge` | `AccretionBadge` | Badge |
| `.sec` | `AccretionSection`, `.accretionCard()` | Section |
| `.facts div` | `AccretionFact` | Fact |
| `.live` | `LiveDot` | LiveDot |
| `body` grid + `body::before` | `.accretionBackground()` | Backdrop |
| `.empty` | `AccretionEmptyState` | EmptyState |

Colours reach both surfaces from one file, `design/tokens.json` in the store repo, through `scripts/design_tokens.py` (the CSS block and `AccretionTokens.swift`). A token added or changed here lands there first.

## Changes from the live site

These tokens refine what the code ships today, so text and controls pass WCAG AA in both themes. The site and app keep their current values until `design/tokens.json` and the hard-coded colours below are updated.

| Token or rule | Live code | Here | Why |
|---|---|---|---|
| `link` (new) | `accent-2` as text | light `#0a6880` | `#0e8fb0` is 3.5:1 on light grounds |
| `good`, `warn`, `bad` (light) | `#078a5e`, `#b76a00`, `#c2410c` | `#066d4a`, `#8c5100`, `#aa390b` | under 4.5:1 on grounds or badge tints |
| `accent-text` (new) | `accent` as text | dark `#a07af7` | 3.6:1 on its badge tint in dark |
| `accent-fill`, `accent-fill-end` | `accent` → mix `#5c93f2` | dark `#7c4dee` → `#3a6fe6` | white button text was 4.2:1 and 3.0:1 |
| `rose`, `rose-fill` (new) | hard-coded `#f43f5e` | per-theme `rose`; `#e11d48` fill | 3.4:1 in light; white count 3.7:1 |
| `star` (light) | `#f5b83b` | `#b87f09` | 1.8:1 on white |
| `line-strong` (new) | fields use `line` | `#6458af` / `#8f7ed2` | field edges were 1.3:1 |
| `avatar-ink` (new) | white initials | `#0f0e1a` | white was 1.5:1 to 4.2:1 |
| Badge tint and weight | 18–22%, 600 | 14%, 500 | 600 isn't loaded, so it's faked |
| Radii | 15 values, 5–26px | 8 steps + `radius-icon` | one scale |
| Spacing, type | 11.5px meta, 650 names | 12px, 600 | one scale; app already uses these |

Also out of step, left as is: the README index card (`assets/Images`) draws its own 24px grid, `#0e0e1a` tiles with 9px corners, and the system fonts instead of Sora and JetBrains Mono.

## Not synced

From `GETAccretion/getaccretion.github.io@076e820` and `GETAccretion/accretion-app@d95d01c`. The store has no component library (one vanilla-JS file per layer), so the components here are static renditions of its classes in `components/bundle.css`, with no JS bundle. Not carded yet: sign-in provider buttons (their colours are the providers' own), Status page bars and growth chart, source list rows, version list and permissions, screenshot strip, composer, profile card, notifications list, moderation reports and demand lists, support wallets and certificate list, download screen, sign-guide steps, QR plate (`qr-plate`, `qr-ink`), footer.

## In this repo

- The live colours still come from `design/tokens.json` (one level up): `scripts/design_tokens.py` writes them into `site/style.css` and the app's `AccretionTokens.swift`. This folder's `tokens.json` is the full design-system spec (type, spacing, radius, layout, components) and must agree with it; change both together.
- See every component in both themes: `python design/system/tools/preview.py`, then open `design/system/_preview/sheet.html` (git-ignored).
- `tools/gen_components.py` rewrites `components/*/README.md` and `preview.html` from the store's own markup.
- Fonts are Sora and JetBrains Mono under the SIL Open Font License 1.1 (`fonts/*-OFL.txt`), the same files the app bundles.
