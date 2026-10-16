# InstallWays

The list of every way to get an app (installers, Download IPA, Copy IPA link, certificates), one row each, inside the More ways dialog.

## Use
- One `surface` list with `line` dividers and `radius-xl`; each row has a 32px icon, a bold name, an optional `muted` note, and a ›.
- Installers show their own logo (`assets/Installers`, 32px, with a faint ring). Actions use the stroke glyphs (`assets/Icons`: download, copy, cert) in `accent-text` on a 16% `accent` tint.
- Notes say how each one signs, in one short sentence: "Signs with your Apple ID, refreshes every 7 days."
- Order: installers (Accretion, Feather, AltStore, SideStore, TrollStore), then the file actions, then certificate sellers from `support.json` with their own note.

## Counterparts
App: the install sheet.
