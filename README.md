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

The `<script>` block at the bottom of `index.html` contains the `loadStatus()`
skeleton with all fetches stubbed and the call commented out. To activate:

1. Uncomment `loadStatus()` + `setInterval(loadStatus, 120_000)` at the bottom
   of `index.html`.
2. Fill in the per-app readers in `scripts/update-hub-status.py`.
3. Schedule the aggregator (every 15 min) — see below.

See `../KrispyPidgeon_Hub_v2_LiveStatus_Spec.md` for the full contract.

## Schedule (when ready)

Windows Task Scheduler — run every 15 min:

```
schtasks /create /tn "KP Hub Heartbeat" /tr "python C:\Users\djbla\dev\chris-brain\kp-hub\scripts\update-hub-status.py" /sc minute /mo 15
```

## Push pattern

Mirrors the podcast-feed flow: `git pull --rebase` → edit `status.json` →
commit → push. The aggregator does this automatically.
