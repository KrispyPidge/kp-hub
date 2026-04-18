#!/usr/bin/env python3
"""
update-hub-status.py — KrispyPidgeon Hub heartbeat aggregator.

Reads each local app's state file, builds a combined status.json matching
the v2 spec schema, and pushes it to the kp-hub repo.

SCAFFOLD STATUS: not yet wired to real app state. Each reader returns
placeholder data. Drop in real cache-file reads as each app comes online.

Schedule: every 15 min via Windows Task Scheduler (see README).

Spec: ../KrispyPidgeon_Hub_v2_LiveStatus_Spec.md §2 (heartbeat contract).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Optional deps (pip install icalendar recurring-ical-events)
try:
    from icalendar import Calendar
    import recurring_ical_events
    ICAL_AVAILABLE = True
except ImportError:
    ICAL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_DIR = Path(__file__).resolve().parent.parent  # kp-hub/
STATUS_FILE = REPO_DIR / "status.json"

# Public Google Calendar ICS for KrispyPidgeon stream schedule.
ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "379d6186770e506184270e1ee02c0778db609888e564d221a5d2906a6c61fa74"
    "%40group.calendar.google.com/public/basic.ics"
)
ICS_LOOKAHEAD_DAYS = 21

# Per-spec local app state locations. Fill in as apps come online.
# Examples (uncomment when ready):
# STREAMCLIPPER_RUNS = Path("C:/Users/djbla/OneDrive/Documents/Claude/Projects/Vibe Coding Chris Brain/streamclipper/runs.json")
# HIVEMIND_CACHE     = Path("C:/Users/djbla/OneDrive/Documents/Claude/Projects/Vibe Coding Chris Brain/hivemind/cache.json")
# THUMB_LAST_RUN     = Path("C:/Users/djbla/OneDrive/Documents/Claude/Projects/Vibe Coding Chris Brain/thumbnail-generator/last_run.json")
# CONTENT_LEDGER     = Path("C:/Users/djbla/OneDrive/Documents/Claude/Projects/Vibe Coding Chris Brain/content-pipeline/ledger.json")


def utc_iso(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # tolerate trailing Z and missing tz
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def fmt_age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        h, m = divmod(seconds // 60, 60)
        return f"{h}h {m}m"
    return f"{seconds // 86400}d"


# ---------------------------------------------------------------------------
# Per-app readers — STUBS. Replace bodies with real state-file reads.
# Each reader must return a dict matching the schema in the spec, OR None
# (which renders the tile grey via the staleness rule on the client).
# ---------------------------------------------------------------------------

STREAMCLIPPER_HISTORY = Path("C:/Users/djbla/streamclip/dashboard/batch_history.json")
HIVEMIND_CACHE       = Path("C:/Users/djbla/OneDrive/Documents/Claude/Projects/Vibe Coding Chris Brain/content-pipeline/hivemind-cache.json")
THUMB_OUTPUT_DIR     = Path("C:/Users/djbla/OneDrive/Documents/Claude/Projects/Vibe Coding Chris Brain/thumbnail-generator/output")
CONTENT_LEDGER_DIR   = Path("C:/Users/djbla/OneDrive/Documents/Claude/Projects/Vibe Coding Chris Brain/content-pipeline/ledger")
WATCHLIST_FILE       = Path("C:/Users/djbla/OneDrive/Documents/Claude/Projects/Vibe Coding Chris Brain/content-pipeline/watchlist.json")

# kp-supervisor — local launcher service. Queried for live process state.
SUPERVISOR_URL = "http://localhost:8090/apps"


def fetch_supervisor_state() -> dict | None:
    """Return {key: {state, port, ...}} or None if the supervisor is offline."""
    try:
        req = urllib.request.Request(SUPERVISOR_URL, headers={"User-Agent": "kp-hub/1.0"})
        with urllib.request.urlopen(req, timeout=2) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"[hub] supervisor unreachable ({e}) — skipping live state", file=sys.stderr)
        return None


# Populated once per run by build_status(); read by the per-app readers.
_LIVE_STATE: dict | None = None


def live(key: str) -> dict | None:
    """Shortcut: supervisor's entry for one app, or None."""
    if not _LIVE_STATE:
        return None
    return _LIVE_STATE.get(key)


def read_streamclipper() -> dict | None:
    if not STREAMCLIPPER_HISTORY.exists():
        # Even with no history, reflect live process state if we have it.
        lv = live("streamclipper")
        if lv and lv.get("state") == "running":
            return {"state": "green", "message": f"Running · :{lv.get('port', 8420)} · no batch history yet"}
        return None
    data = json.loads(STREAMCLIPPER_HISTORY.read_text(encoding="utf-8"))
    runs = data.get("processed", [])
    if not runs and not live("streamclipper"):
        return None
    latest = max(runs, key=lambda r: r.get("processed_at", "")) if runs else {}
    last_run = parse_iso(latest.get("processed_at"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    clips_7d = sum(
        r.get("segments", 0) for r in runs
        if (parse_iso(r.get("processed_at")) or datetime.min.replace(tzinfo=timezone.utc)) > cutoff
    )
    age_s = (datetime.now(timezone.utc) - last_run).total_seconds() if last_run else 0

    lv = live("streamclipper")
    is_running = bool(lv and lv.get("state") == "running")
    port = (lv or {}).get("port", 8420)
    if is_running:
        head = f"Running · :{port}"
        state = "green"
    else:
        head = "Idle"
        state = "amber"
    tail = f"last run {fmt_age(age_s)} ago · {clips_7d} clips/7d" if last_run else "no runs yet"

    return {
        "state": state,
        "last_run_at": utc_iso(last_run) if last_run else None,
        "message": f"{head} · {tail}",
        "metric": {"label": "clips last 7d", "value": clips_7d},
    }


def read_thumbnail_generator() -> dict | None:
    lv = live("thumbnail_generator")
    is_running = bool(lv and lv.get("state") == "running")
    port = (lv or {}).get("port", 8421)

    pngs: list[Path] = []
    if THUMB_OUTPUT_DIR.exists():
        pngs = list(THUMB_OUTPUT_DIR.glob("*.png"))

    if not pngs and not is_running:
        return None

    if pngs:
        latest = max(pngs, key=lambda p: p.stat().st_mtime)
        mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=timezone.utc)
        age_s = (datetime.now(timezone.utc) - mtime).total_seconds()
        stem = latest.stem.replace("thumb_", "", 1)
        game = stem.replace("_", " ").title()
        tail = f"last: {game} thumb {fmt_age(age_s)} ago"
    else:
        mtime = None
        game = None
        tail = "no thumbnails generated yet"

    if is_running:
        head = f"Running · :{port}"
        state = "green"
    else:
        head = "Idle · ready to launch"
        state = "grey"

    block: dict = {
        "state": state,
        "message": f"{head} · {tail}",
    }
    if mtime is not None:
        block["last_run_at"] = utc_iso(mtime)
    if game is not None:
        block["metric"] = {"label": "last thumbnail", "value": game}
    return block


def _hivemind_reason(top: dict) -> str:
    bd = top.get("breakdown") or {}
    twitch = top.get("twitch") or {}
    bits: list[str] = []
    if bd.get("socialBuzz", 0) >= 70:
        bits.append("strong social buzz")
    if bd.get("newsCoverage", 0) >= 70:
        bits.append("heavy news coverage")
    if bd.get("updateSignal", 0) >= 70:
        bits.append("recent patch/event signal")
    if twitch.get("viewers"):
        bits.append(f"{twitch['viewers']:,} live Twitch viewers")
    if bd.get("twitchOpportunity", 0) >= 70:
        bits.append("low streamer competition")
    return ". ".join(s.capitalize() for s in bits) + "." if bits else "High composite score across signals."


def read_hivemind() -> dict | None:
    if not HIVEMIND_CACHE.exists():
        return None
    data = json.loads(HIVEMIND_CACHE.read_text(encoding="utf-8"))
    last_refresh = data.get("lastRefresh")
    opps = data.get("opportunities", [])
    if not opps:
        return None
    opps_sorted = sorted(opps, key=lambda o: -(o.get("score") or 0))
    # Prefer Steam-backed picks (real games) over generic Twitch categories
    steam_backed = [o for o in opps_sorted if o.get("appId")]
    top = steam_backed[0] if steam_backed else opps_sorted[0]
    hot_count = sum(1 for o in opps if (o.get("score") or 0) >= 30)
    age_s = (datetime.now(timezone.utc) - (parse_iso(last_refresh) or datetime.now(timezone.utc))).total_seconds()
    fresh = age_s < 6 * 3600
    return {
        "state": "green" if fresh else "amber",
        "last_run_at": last_refresh,
        "message": f"{'Fresh' if fresh else 'Stale'} · cache {fmt_age(age_s)} old · {hot_count} picks \u226530",
        "metric": {"label": "hot picks (\u226530)", "value": hot_count},
        "top_pick": {
            "game": top.get("game"),
            "score": top.get("score"),
            "reason": _hivemind_reason(top),
            "image": top.get("headerImage"),
            "breakdown": top.get("breakdown") or {},
            "twitch": top.get("twitch") or {},
        },
    }


def read_stream_prep_autopilot() -> dict | None:
    # Not yet implemented as a service — leave the tile as designed.
    return None


def read_content_pipeline() -> dict | None:
    if not CONTENT_LEDGER_DIR.exists():
        return None
    files = list(CONTENT_LEDGER_DIR.glob("*.json"))
    if not files:
        return None
    counts = {"ideas": 0, "scheduled": 0, "live": 0}
    last_updated = ""
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        s = (d.get("status") or "").lower()
        if s == "draft":
            counts["ideas"] += 1
        elif s == "scheduled":
            counts["scheduled"] += 1
        elif s == "live":
            counts["live"] += 1
        u = d.get("updatedAt") or d.get("createdAt") or ""
        if u > last_updated:
            last_updated = u
    return {
        "state": "amber",
        "message": f"Paused · {counts['ideas']} ideas · {counts['scheduled']} scheduled · {counts['live']} live",
        "counts": counts,
        "last_run_at": last_updated or None,
    }


# ---------------------------------------------------------------------------
# Calendar — fetch + parse the public ICS, return the soonest future event.
# ---------------------------------------------------------------------------

def fetch_next_stream() -> dict | None:
    if not ICAL_AVAILABLE:
        print("[hub] icalendar not installed — skipping next-stream lookup", file=sys.stderr)
        return None
    try:
        req = urllib.request.Request(ICS_URL, headers={"User-Agent": "kp-hub/1.0"})
        text = urllib.request.urlopen(req, timeout=15).read()
        cal = Calendar.from_ical(text)
        now = datetime.now(timezone.utc)
        events = recurring_ical_events.of(cal).between(
            now, now + timedelta(days=ICS_LOOKAHEAD_DAYS)
        )
        events.sort(key=lambda e: e["DTSTART"].dt)
        for ev in events:
            dt = ev["DTSTART"].dt
            if hasattr(dt, "astimezone"):
                dt_utc = dt.astimezone(timezone.utc)
            else:
                # all-day event — treat as midnight UTC
                dt_utc = datetime.combine(dt, datetime.min.time(), tzinfo=timezone.utc)
            if dt_utc <= now:
                continue
            return {
                "starts_at": utc_iso(dt_utc),
                "summary": str(ev.get("SUMMARY", "Stream")),
            }
    except Exception as e:
        print(f"[hub] next-stream fetch failed: {e}", file=sys.stderr)
    return None


# ---------------------------------------------------------------------------
# Aggregate + write
# ---------------------------------------------------------------------------

def build_watchlist_top3() -> list[dict] | None:
    """Read watchlist.json and cross-reference with hivemind-cache for live scores.

    Returns the top 3 tracked items (by live Hivemind score desc) plus untracked
    items if there's room. Untracked entries get score=None and are ordered last.
    """
    if not WATCHLIST_FILE.exists():
        return None
    try:
        wl = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[hub] watchlist parse failed: {e}", file=sys.stderr)
        return None

    items = wl.get("items") or []
    if not items:
        return []

    score_map: dict[str, dict] = {}
    if HIVEMIND_CACHE.exists():
        try:
            cache = json.loads(HIVEMIND_CACHE.read_text(encoding="utf-8"))
            for opp in cache.get("opportunities", []):
                key = str(opp.get("game", "")).strip().lower()
                if key and key not in score_map:
                    score_map[key] = opp
        except Exception:
            pass

    enriched: list[dict] = []
    for it in items:
        name = str(it.get("game", "")).strip()
        key = name.lower()
        live = score_map.get(key)
        entry = {
            "game": name,
            "score": (live.get("score") if live else None),
            "image": (it.get("headerImage") or (live.get("headerImage") if live else None)),
            "tracked": live is not None,
        }
        if live:
            tw = live.get("twitch") or {}
            entry["twitch_viewers"] = tw.get("viewers")
            entry["twitch_ratio"] = tw.get("ratio")
        enriched.append(entry)

    enriched.sort(
        key=lambda x: (
            0 if x["tracked"] else 1,
            -(x["score"] or 0),
            x["game"].lower(),
        )
    )
    return enriched[:3]


def build_status() -> dict:
    global _LIVE_STATE
    _LIVE_STATE = fetch_supervisor_state()

    apps: dict[str, dict] = {}
    readers = {
        "streamclipper":         read_streamclipper,
        "thumbnail_generator":   read_thumbnail_generator,
        "hivemind":              read_hivemind,
        "stream_prep_autopilot": read_stream_prep_autopilot,
        "content_pipeline":      read_content_pipeline,
    }
    for key, reader in readers.items():
        try:
            block = reader()
        except Exception as e:
            block = {"state": "red", "message": f"reader error: {e}"}
        if block is not None:
            apps[key] = block

    out: dict = {
        "updated_at": utc_iso(),
        "supervisor_reachable": _LIVE_STATE is not None,
        "apps": apps,
    }
    next_stream = fetch_next_stream()
    if next_stream:
        out["next_stream"] = next_stream
    wl = build_watchlist_top3()
    if wl is not None:
        out["watchlist_top3"] = wl
    return out


def write_status(status: dict) -> None:
    STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[hub] wrote {STATUS_FILE} ({len(status.get('apps', {}))} apps)")


def git_push() -> None:
    """Mirror the podcast-feed push pattern: pull → add → commit → push."""
    env = os.environ.copy()
    def run(*cmd):
        subprocess.run(cmd, cwd=REPO_DIR, env=env, check=True)
    try:
        run("git", "pull", "origin", "main", "--rebase", "--autostash")
        run("git", "add", "status.json")
        # nothing to commit? exit cleanly
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=REPO_DIR, env=env
        )
        if diff.returncode == 0:
            print("[hub] no status changes — skipping push")
            return
        run("git", "commit", "-m", f"Update hub status {utc_iso()}")
        run("git", "push", "origin", "main")
        print("[hub] pushed status update")
    except subprocess.CalledProcessError as e:
        print(f"[hub] git push failed: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    status = build_status()
    write_status(status)
    if "--no-push" not in sys.argv:
        git_push()


if __name__ == "__main__":
    main()
