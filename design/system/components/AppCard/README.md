# AppCard

One app in the All apps grid: icon, name with a badge, developer, and a mono meta line (version, size, last update).

## Use
- `surface` card, `line` edge turning `accent` on hover (with a 1px lift unless Reduce Motion), `radius-xl`, 13px padding.
- Icon at `icon-card` with `radius-icon`. With no icon, the first letter in Sora on `raised` (`.icon.ph`).
- Name in `body-strong`, one line with ellipsis; at most one badge after it.
- Meta in the `meta` style: the version in `link`, then size and age.
- Grid columns are at least `card-min` wide, 12px apart; 60 cards a page.

## Counterparts
App: `StoreAppCard` in `DiscoverView.swift`.
