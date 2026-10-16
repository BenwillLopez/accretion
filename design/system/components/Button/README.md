# Button

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
