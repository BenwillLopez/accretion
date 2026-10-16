# Shelf

A titled, ranked list of apps on the home page (Most popular, Fresh today, New this month, Games), paged sideways.

## Use
- Heading in `section-title` with a `muted` mono note ("this week"); See all and the page arrows on the right. Arrows show only with a mouse.
- Rows: rank in the `rank` style, icon at `icon-row` with a `line` edge, name in `body-strong` (turns `accent-text` on hover), meta in `meta` with an optional badge, and a `muted` › at the end. Rows are split by `line` hairlines.
- 5 rows a page, up to 20 apps. Shelves sit in columns at least `shelf-min` wide, 28px apart; a shelf with one or two apps becomes a full-width strip.
- Shelf order on home: Most popular, Made by Accretion, Updates for your saved apps, Fresh today, New this month, From Accretion Core, Games, community shelves, Utilities.

## Counterparts
App: `StoreShelfView` and `StoreAppRow`.
