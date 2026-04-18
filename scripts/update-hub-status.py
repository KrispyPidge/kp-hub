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


# ---------------------------------------------------------------------------
# Per-app readers — STUBS. Replace bodies with real state-file reads.
# Each reader must return a dict matching the schema in the spec, OR None
# (which renders the tile grey via the staleness rule on the client).
# ---------------------------------------------------------------------------

def read_streamclipper() -> dict | None:
    # TODO: read StreamClipper's run history file
    # e.g. runs = json.loads(STREAMCLIPPER_RUNS.read_text())
    #      latest = runs[-1]
    #      return {
    #          "state": "green" if latest["status"] == "ok" else "amber",
    #          "last_run_at": latest["finished_at"],
    #          "message": f"{latest['clip_count']} clips from {latest['game']}",
    #          "metric": {"label": "clips last 7d", "value": runs_in_last_7d(runs)},
    #      }
    return None


def read_thumbnail_generator() -> dict | None:
    # TODO: read THUMB_LAST_RUN
    return None


def read_hivemind() -> dict | None:
    # TODO: read HIVEMIND_CACHE, surface top_pick
    return None


def read_stream_prep_autopilot() -> dict | None:
    # TODO: read scheduled-task next-fire timestamp
    # Return {"state": "green", "next_fire_at": "...", "message": "armed"}
    return None


def read_content_pipeline() -> dict | None:
    # TODO: read CONTENT_LEDGER, count by stage
    return None


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

def build_status() -> dict:
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

    out: dict = {"updated_at": utc_iso(), "apps": apps}
    next_stream = fetch_next_stream()
    if next_stream:
        out["next_stream"] = next_stream
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
        run("git", "pull", "origin", "main", "--rebase")
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
