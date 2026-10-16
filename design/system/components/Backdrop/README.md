# Backdrop

The page background every Accretion screen sits on: `bg`, a faint 1px grid every `grid-pitch`, and two soft lights drifting over it.

## Use
- Put it on the page body, once. Content sits on `surface` cards above it; never put a backdrop inside a card.
- Paint order is fixed: colour, then the grid (`grid-line`), then the lights (`glow-accent` at 30% 25%, radius 42vmax; `glow-accent-2` at 75% 70%, radius 36vmax; both fade out by 70%).
- On the site the lights are a fixed `body::before`, 20vmax larger than the screen, moving on a 40 s `drift` loop (ease-in-out, alternating). The preview shows them still.
- With Reduce Motion (and, in the app, Low Power Mode) the lights stay still. Never animate the grid.

## Counterparts
- Site: `body` background plus `body::before` in `site/style.css`.
- App: `.accretionBackground()` (`AccretionGrid` and `AccretionAmbientGlow`, drawn at 15 fps).
