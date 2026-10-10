# Security

## What AltSource does and does not do

AltSource republishes app listings from public third-party sources. It does **not** host app
files, and it does **not** review the apps themselves. Each build:

- uses only https links; any http download, icon or screenshot is dropped
- caps the size of every field and removes fields outside the AltStore format
- turns off news notifications from merged sources
- skips everything in [`blocklist.txt`](blocklist.txt)

## Report a harmful source or app

If a source or app distributes malware, steals credentials, or is otherwise harmful:

1. Use **[Report a vulnerability](../../security/advisories/new)** on this repo. Only the
   maintainer can see these reports.
2. Include the source URL, the app's bundle ID, and what you observed.

The source is added to `blocklist.txt`, and the next build removes it, normally within 6 hours.

## Removal requests

If you own an app or source and want it removed, open an issue or a private report as above. It
will be blocked.
