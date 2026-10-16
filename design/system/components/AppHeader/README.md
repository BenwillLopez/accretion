# AppHeader

The top of an app page: big icon, name, developer, and the install actions, with a soft light in the app's own colour.

## Use
- `surface` panel, `line` edge, `radius-2xl`, 22px padding. A radial light in `--tint` (the app's icon colour, else `accent`) at 30% sits top right.
- Icon at `icon-hero` with `radius-icon`; name in `app-title`; developer in `muted`.
- Actions in this order: Install (primary, opens the chosen installer), More ways ▾ (the InstallWays dialog), Save, Share. Below it, "Need a signing certificate?" with links in `small`.
- Under 560px the icon drops to 80px and the name to 22px.

## Consumer provides
The app, its tint colour (`style="--tint: …"`) and the chosen installer.
