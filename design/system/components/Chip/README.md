# Chip

A pill that filters a list by category, with the count in mono beside the name.

## Use
- `chip-label` text on `surface` with a `line` edge, `radius-pill`; the count in 11px mono `muted`.
- The selected chip inverts: `fg` fill, `bg` text. Exactly one is selected; mark it with `aria-selected="true"` in a `tablist`.
- The categories, in order: All, Games, Utilities, Photo & Video, Entertainment, Social, Lifestyle, Developer, Other.
- On phones the row scrolls sideways; with a mouse it wraps.
