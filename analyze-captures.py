#!/usr/bin/env python3
"""Analyze captured APSystems EMA app traffic to find the real-time data channel."""

import json
import sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime


def load_entries(capture_dir: Path) -> list[dict]:
    entries = []
    for f in sorted(capture_dir.glob("*.json")):
        if f.name == "summary.json":
            continue
        with open(f) as fh:
            entry = json.load(fh)
            entry["_file"] = f.name
            entries.append(entry)
    return entries


def analyze(entries: list[dict]):
    print("=" * 70)
    print("APSYSTEMS EMA TRAFFIC ANALYSIS")
    print("=" * 70)
    print(f"Total captured entries: {len(entries)}")
    print()

    # --- 1. Unique endpoints ---
    endpoints = defaultdict(list)
    for e in entries:
        if e.get("type") in ("request", "response") and "url" in e:
            url = e["url"].split("?")[0]
            method = e.get("method", "?")
            endpoints[f"{method} {url}"].append(e)

    print("-" * 70)
    print("UNIQUE ENDPOINTS (sorted by hit count)")
    print("-" * 70)
    for ep, hits in sorted(endpoints.items(), key=lambda x: -len(x[1])):
        print(f"  [{len(hits):3d} hits] {ep}")
    print()

    # --- 2. Real-time candidates ---
    print("-" * 70)
    print("REAL-TIME CANDIDATES")
    print("-" * 70)

    # 2a. WebSocket
    ws_entries = [e for e in entries if e.get("websocket_upgrade") or e.get("websocket") or e.get("type") == "websocket_message"]
    if ws_entries:
        print(f"  [WebSocket] {len(ws_entries)} WebSocket-related entries:")
        for e in ws_entries[:20]:
            print(f"    {e.get('_file', '')}: {e.get('url', '?')}")
            if e.get("content"):
                print(f"      content: {str(e.get('content', ''))[:200]}")
    else:
        print("  [WebSocket] None detected")

    # 2b. Long-lived connections (>10s)
    long = [e for e in entries if e.get("long_lived")]
    if long:
        print(f"\n  [Long-lived] {len(long)} responses > 10s:")
        for e in long[:20]:
            print(f"    {e.get('duration_ms', '?')}ms - {e.get('url', '?')}")
    else:
        print("\n  [Long-lived] None detected")

    # 2c. SSE
    sse = [e for e in entries if e.get("sse")]
    if sse:
        print(f"\n  [SSE] {len(sse)} Server-Sent Events responses:")
        for e in sse[:20]:
            print(f"    {e.get('url', '?')}")
    else:
        print("\n  [SSE] None detected")

    # 2d. High-frequency polling (same endpoint called >5 times)
    print("\n  [High-frequency polling]")
    freq_found = False
    for ep, hits in sorted(endpoints.items(), key=lambda x: -len(x[1])):
        if len(hits) >= 5:
            timestamps = []
            for h in hits:
                try:
                    ts = datetime.fromisoformat(h["timestamp"])
                    timestamps.append(ts.timestamp())
                except (KeyError, ValueError):
                    pass
            if len(timestamps) >= 2:
                intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                avg_interval = sum(intervals) / len(intervals)
                if avg_interval < 60:
                    freq_found = True
                    print(f"    {ep}")
                    print(f"      {len(hits)} calls, avg interval: {avg_interval:.1f}s, min: {min(intervals):.1f}s, max: {max(intervals):.1f}s")
    if not freq_found:
        print("    None detected (no endpoint with avg interval < 60s)")

    print()

    # --- 3. Battery data sources ---
    print("-" * 70)
    print("BATTERY DATA SOURCES")
    print("-" * 70)
    battery = [e for e in entries if e.get("battery_keywords")]
    if battery:
        seen_urls = set()
        for e in battery:
            url = e.get("url", "?").split("?")[0]
            if url not in seen_urls:
                seen_urls.add(url)
                keywords = e.get("battery_keywords", [])
                print(f"  {url}")
                print(f"    keywords: {keywords}")
                # Show a sample response body
                body = e.get("response_body", "")
                if body:
                    print(f"    sample: {body[:300]}")
    else:
        print("  No battery-related data found in responses")
    print()

    # --- 4. Authentication patterns ---
    print("-" * 70)
    print("AUTHENTICATION PATTERNS")
    print("-" * 70)
    auth_headers = defaultdict(set)
    for e in entries:
        if e.get("type") == "request":
            for h in ["Authorization", "Cookie", "token", "tokenId", "X-Requested-With"]:
                val = e.get("headers", {}).get(h)
                if val:
                    auth_headers[h].add(val[:100])
    for h, vals in auth_headers.items():
        print(f"  {h}: {len(vals)} unique value(s)")
        for v in list(vals)[:3]:
            print(f"    {v}")
    print()

    # --- 5. Non-standard ports ---
    print("-" * 70)
    print("NON-STANDARD PORTS (potential custom protocols)")
    print("-" * 70)
    ports = set()
    for e in entries:
        url = e.get("url", "")
        if ":" in url.split("//")[-1].split("/")[0]:
            try:
                port = url.split("//")[-1].split("/")[0].split(":")[-1]
                if port not in ("80", "443", "8080"):
                    ports.add(port)
            except (IndexError, ValueError):
                pass
    if ports:
        for p in sorted(ports):
            print(f"  Port {p}")
    else:
        print("  None detected (only standard ports 80, 443)")
    print()

    # --- 6. Summary from mitmproxy ---
    summary_file = Path("./capture/summary.json")
    if summary_file.exists():
        print("-" * 70)
        print("ENDPOINT FREQUENCY SUMMARY (from mitmproxy)")
        print("-" * 70)
        with open(summary_file) as f:
            summary = json.load(f)
        for ep, info in sorted(summary.get("endpoint_frequency", {}).items(),
                               key=lambda x: x[1]["hit_count"], reverse=True):
            print(f"  [{info['hit_count']:3d} hits] avg interval: {info['avg_interval_seconds']}s - {ep}")
        print()


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <capture_dir>")
        sys.exit(1)

    capture_dir = Path(sys.argv[1])
    if not capture_dir.exists():
        print(f"Error: {capture_dir} does not exist")
        sys.exit(1)

    entries = load_entries(capture_dir)
    if not entries:
        print("No capture entries found. Run the lab first.")
        sys.exit(1)

    analyze(entries)


if __name__ == "__main__":
    main()
