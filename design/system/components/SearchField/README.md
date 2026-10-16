# SearchField

The store's search: one field for app names, developers and bundle IDs, with a `/` shortcut hint.

## Use
- A `surface` field with a `line-strong` edge, `radius-md`, 17px search glyph in `muted`. Focus turns the edge `accent` (second row).
- Placeholder wording: "Search apps, developers, bundle IDs".
- The `/` hint (`kbd`) shows only where there is a keyboard (`@media (hover: none)` hides it).
- Keep a visually hidden label ("Search apps").

## Refined
The site draws the edge in `line` (1.3:1) at 11px radius; this system uses `line-strong` (3:1) and `radius-md`.
