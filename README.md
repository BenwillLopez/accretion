# altsource

One AltStore/SideStore source that merges every source it can find and always
serves the newest version of each app.

**Add this URL to the app:**

```
https://raw.githubusercontent.com/benwilllopez/altsource/main/source.json
```

## How it works

| File | What it does |
|---|---|
| `sources.txt` | Your own sources. Edit freely. |
| `discovered.txt` | Sources found automatically. Written by `discover.py`; don't edit. |
| `blocklist.txt` | URLs (or parts of URLs) that are never used. |
| `discover.json` | Where discovery looks: link lists, GitHub repos, GitHub topics. |
| `REPORT.md` | Written on each build: which sources work, how many apps each gave, recent updates. |

- **Build** (`build.yml`, every 6 hours): downloads all sources and keeps one copy of
  each app (by bundle ID): the one with the **highest version**. Ties go to the newest
  release date, then to `sources.txt` over discovered sources. Each app keeps its 3 newest
  versions. If a source is down, its last good copy from `cache/` is used.
- **Discover** (`discover.yml`, every Monday): reads the link lists in `discover.json`,
  scans GitHub repos tagged `altstore-repo`, `sidestore`, etc., and checks every JSON file
  it finds. Only real sources are kept. Mirrors and short links of a source are only added once.
  A source that keeps failing is dropped after 30 days.

## Setup (one time)

1. Create a **public** repo named `altsource` on GitHub.
2. Upload everything in this folder to it, including the hidden `.github` folder.
3. Open **Actions**, then enable workflows if GitHub asks.
4. Run **Actions → Discover sources → Run workflow**. It finds sources and builds
   `source.json`. Wait for the green check.
5. Add the URL above in AltStore or SideStore.

### Optional: wider GitHub search

GitHub's code search needs a personal token. With one, discovery also finds sources in
repos that have no topic tags.

1. Create a fine-grained token at **GitHub → Settings → Developer settings → Personal access
   tokens**. Give it read-only access to public repositories only, with no extra permissions.
2. In the `altsource` repo, go to **Settings → Secrets and variables → Actions** and add the
   token as a secret named `GH_SEARCH_TOKEN`.

## Notes

- An app can only appear once per bundle ID. When two tweaked builds share one ID (for example,
  several YouTube tweaks use `com.google.ios.youtube`), only the highest version is kept. To
  keep a specific tweak, add the sources that carry the other builds to `blocklist.txt`.
- Check `REPORT.md` to see which sources fail and how big `source.json` has become.
