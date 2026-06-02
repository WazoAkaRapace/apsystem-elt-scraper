"""mitmproxy addon to capture APSystems EMA app traffic."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from mitmproxy import http, ctx

CAPTURE_DIR = Path("/capture")
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)

APSYSTEMS_DOMAINS = [
    "apsystemsema.com",
    "apsema.com",
    "apsystems.com",
]

# Track connection start times to detect long-lived/real-time connections
conn_start = {}

# Track request frequency per endpoint for real-time detection
endpoint_hits = {}


def is_apsystems(host: str) -> bool:
    return any(d in (host or "") for d in APSYSTEMS_DOMAINS)


def safe_str(data, max_len=5000):
    try:
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
        else:
            text = str(data)
        return text[:max_len]
    except Exception:
        return "<unreadable>"


def write_entry(entry: dict):
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{ts}_{entry.get('type', 'unknown')}.json"
    path = CAPTURE_DIR / filename
    with open(path, "w") as f:
        json.dump(entry, f, indent=2, default=str)
    ctx.log.info(f"[CAPTURE] {entry['type']}: {entry.get('url', entry.get('endpoint', '?'))}")


class APCapture:
    def request(self, flow: http.HTTPFlow):
        if not is_apsystemen(flow.request.pretty_host):
            return

        ts = time.time()
        url = flow.request.pretty_url
        host = flow.request.pretty_host
        method = flow.request.method

        # Track endpoint frequency
        key = f"{method} {host}{flow.request.path.split('?')[0]}"
        endpoint_hits.setdefault(key, []).append(ts)

        entry = {
            "type": "request",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "method": method,
            "host": host,
            "path": flow.request.path,
            "headers": dict(flow.request.headers),
            "body": safe_str(flow.request.get_text()),
        }

        # Flag WebSocket upgrade requests
        if flow.request.headers.get("Upgrade", "").lower() == "websocket":
            entry["websocket_upgrade"] = True
            ctx.log.warn(f"[REALTIME-CANDIDATE] WebSocket upgrade to {url}")

        conn_start[flow.id] = ts
        write_entry(entry)

    def response(self, flow: http.HTTPFlow):
        if not is_apsystemen(flow.request.pretty_host):
            return

        ts = time.time()
        start = conn_start.pop(flow.id, ts)
        duration_ms = round((ts - start) * 1000)

        entry = {
            "type": "response",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": flow.request.pretty_url,
            "method": flow.request.method,
            "host": flow.request.pretty_host,
            "status_code": flow.response.status_code,
            "duration_ms": duration_ms,
            "response_headers": dict(flow.response.headers),
            "response_body": safe_str(flow.response.get_text(), max_len=10000),
        }

        # Flag long-lived connections (potential real-time channel)
        if duration_ms > 10000:
            entry["long_lived"] = True
            ctx.log.warn(f"[REALTIME-CANDIDATE] Long-lived response ({duration_ms}ms) from {flow.request.pretty_url}")

        # Flag specific content types that suggest real-time data
        content_type = flow.response.headers.get("Content-Type", "")
        if "text/event-stream" in content_type:
            entry["sse"] = True
            ctx.log.warn(f"[REALTIME-CANDIDATE] SSE response from {flow.request.pretty_url}")
        if "websocket" in content_type.lower() or "websocket" in flow.response.headers.get("Upgrade", "").lower():
            entry["websocket"] = True
            ctx.log.warn(f"[REALTIME-CANDIDATE] WebSocket response from {flow.request.pretty_url}")

        # Check for battery-related keywords in response
        body = flow.response.get_text() or ""
        battery_keywords = ["SSOC", "chargePower", "dischargePower", "DE0", "DE1", "battery", "soc", "storage"]
        found_keywords = [kw for kw in battery_keywords if kw.lower() in body.lower()]
        if found_keywords:
            entry["battery_keywords"] = found_keywords
            ctx.log.warn(f"[BATTERY-DATA] Found {found_keywords} in {flow.request.pretty_url}")

        write_entry(entry)

    def websocket_message(self, flow: http.HTTPFlow):
        if not is_apsystemen(flow.request.pretty_host):
            return

        msg = flow.websocket.messages[-1]
        entry = {
            "type": "websocket_message",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": flow.request.pretty_url,
            "from_client": msg.from_client,
            "content": safe_str(msg.content, max_len=10000),
        }
        ctx.log.warn(f"[REALTIME-CANDIDATE] WebSocket message on {flow.request.pretty_url}")
        write_entry(entry)

    def done(self):
        # Write endpoint frequency summary
        summary = {
            "type": "summary",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint_frequency": {},
        }
        for endpoint, timestamps in endpoint_hits.items():
            summary["endpoint_frequency"][endpoint] = {
                "hit_count": len(timestamps),
                "first_seen": datetime.fromtimestamp(timestamps[0], tz=timezone.utc).isoformat(),
                "last_seen": datetime.fromtimestamp(timestamps[-1], t=timezone.utc).isoformat(),
                "avg_interval_seconds": round(
                    (timestamps[-1] - timestamps[0]) / max(len(timestamps) - 1, 1), 2
                ) if len(timestamps) > 1 else 0,
            }

        path = CAPTURE_DIR / "summary.json"
        with open(path, "w") as f:
            json.dump(summary, f, indent=2, default=str)
        ctx.log.info(f"[CAPTURE] Summary written to {path}")


addons = [APCapture()]
