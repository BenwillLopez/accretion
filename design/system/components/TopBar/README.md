# TopBar

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
