# Section

The card that holds one part of a page (What's new, Screenshots, About, Versions, Permissions, Info), headed by a small mono label.

## Use
- `surface` with a `line` edge, `radius-xl`, 16px 18px padding; stacked 12px apart.
- Heading in the `label` style (uppercase, `muted`). Content below in `body`; long text keeps its line breaks and stays under 75ch.
- Don't nest sections; use rows or facts inside one.

## Counterparts
App: `AccretionSection(_ title:content:)` and the `.accretionCard()` modifier.
