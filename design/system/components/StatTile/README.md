# StatTile

A number with a mono label: the hero's four tiles (apps, sources, updated 7d, new 30d) and the Status page's grid.

## Use
- Hero tiles (`.stats`): a 2-by-2 grid, label in the `label` style, number at 26px Sora in the headline gradient (`fg` to `headline-end`).
- Status tiles (`.st-tile`): the `stat` style; colour the number only when it is a judgement (`good` for healthy, `warn` for needs attention), with a note under it.
- Numbers use tabular figures and thousands separators.
- On desktop the hero hides its tiles because the live index card shows the same numbers.
