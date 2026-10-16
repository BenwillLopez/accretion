# LiveDot

An 8px status dot with a ring that pulses outward every 2.4 s, beside the eyebrow line that says what it means.

## Use
- `good`: the store index rebuilt within 8 hours (it rebuilds every 6). `warn`: within a day. `bad`: older.
- Always next to words that state the status (the build time, "index 14 h old"); the dot is `aria-hidden`.
- Still with Reduce Motion.

## Counterparts
App: `LiveDot(tone:)` with `LiveDot.Tone.freshness(_:)` for the same thresholds.
