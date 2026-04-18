# kp-hub

Static hub for KrispyPidgeon's production tools. Single HTML file, deployed
via GitHub Pages. No backend.

**Live:** https://krispypidge.github.io/kp-hub

## Layout

- `index.html` — the hub. Vanilla HTML/CSS/JS. Self-contained except for
  Google Fonts. Tile data attributes (`data-app="..."`) match the heartbeat
  schema so v2 wiring drops in cleanly.
- `status.json` — heartbeat file consumed by `loadStatus()` in `index.html`.
  Currently a static placeholder; will be overwritten by the aggregator when
  v2 ships.
- `scripts/update-hub-status.py` — aggregator scaffold. Reads each local app's
  state file, builds `status.json`, pushes to this repo. Stubbed; per-app
  readers return `None` until wired.

## v2 wiring status

`loadStatus()` runs on page load + every 2 min. It reads `status.json` and:

- ✅ **Countdown** — driven by `status.next_stream` (parsed from public GCal ICS
  by the aggregator). Falls back to "next Tuesday 18:30 local" if status.json is
  missing or has no `next_stream` field.
- ⏳ **Tile heartbeats** — only updates tiles for apps present in `status.apps`.
  Currently empty (all readers in `update-hub-status.py` return `None`); tiles
  render as designed until each reader is filled in.
- ⏳ **Twitch live pill** — TODO, embed iframe approach.
- ⏳ **Podcast RSS embed** — TODO, fetch feed.xml client-side.
- ⏳ **Hivemind top pick swap** — TODO, reads from `status.apps.hivemind.top_pick`.

See `../KrispyPidgeon_Hub_v2_LiveStatus_Spec.md` for the full contract.

## Aggregator install

```
pip install -r scripts/requirements.txt
```

Test run (writes status.json, doesn't push):
```
python scripts/update-hub-status.py --no-push
```

## Schedule (when ready)

Windows Task Scheduler — run every 15 min:

```
schtasks /create /tn "KP Hub Heartbeat" /tr "python C:\Users\djbla\dev\chris-brain\kp-hub\scripts\update-hub-status.py" /sc minute /mo 15
```

## Push pattern

Mirrors the podcast-feed flow: `git pull --rebase` → edit `status.json` →
commit → push. The aggregator does this automatically.
