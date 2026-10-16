# Post

One community post or reply: avatar, name and handle, the text, an optional app chip, and actions (Reply, Like, Report).

## Use
- Avatar at 40px, then name in `body-strong`, badges, `@handle` and age in `muted` 13px.
- Text keeps its line breaks and wraps anywhere. An app it mentions shows as an `app-chip` (26px icon and name).
- Actions are text buttons in `muted` that light up on `raised` when hovered; a liked post's ♥ is `rose`; moderator actions are `warn`.
- A hidden post stays in place at `opacity-hidden` with a Hidden badge, so threads still read.
- Replies indent 48px (22px on phones).

## Counterparts
App: `CommunityFeedView` and `FeedThreadView` in `CommunityViews.swift`.
