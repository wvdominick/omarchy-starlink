#!/usr/bin/env python3
"""Query the Starlink dish local gRPC API and print one JSON object.

Uses curl's HTTP/2 support and a small protobuf codec so there are no
Python gRPC packages to install. Talks to the dish on the LAN only.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOSTS = ("192.168.100.1:9200", "dishy.starlink.com:9200")
CURL = "/usr/bin/curl"
CACHE_DIR = Path.home() / ".cache/omarchy/starlink"
MAP_CACHE = CACHE_DIR / "obstruction-map.json"
KEEP_DAYS = 8
# Below this is chatter/idle, not "using the link".
IDLE_BPS = 1_000_000
# A minute only counts as a speed sample if the link was actually busy.
MINUTE_ACTIVE_S = 10
BUCKET_ACTIVE_S = 8
SPARK_ACTIVE_S = 4

# SpaceX.API.Device.Request oneof field numbers
REQ_GET_STATUS = 1004
REQ_GET_HISTORY = 1007
REQ_GET_OBSTRUCTION_MAP = 2008

# SpaceX.API.Device.Response oneof field numbers
RESP_DISH_STATUS = 2004
RESP_DISH_HISTORY = 2006
RESP_DISH_MAP = 2008

DISABLEMENT = {
    0: "UNKNOWN",
    1: "OKAY",
    2: "NO_ACTIVE_ACCOUNT",
    3: "TOO_FAR_FROM_SERVICE_ADDRESS",
    4: "IN_OCEAN",
    6: "BLOCKED_COUNTRY",
    7: "DATA_OVERAGE",
    8: "CELL_DISABLED",
    10: "ROAM_RESTRICTED",
    11: "UNKNOWN_LOCATION",
    12: "ACCOUNT_DISABLED",
    13: "UNSUPPORTED_VERSION",
    14: "MOVING_TOO_FAST",
    15: "AVIATION_LIMIT",
    16: "BLOCKED_AREA",
}

OUTAGE_CAUSE = {
    0: "UNKNOWN",
    1: "BOOTING",
    2: "STOWED",
    3: "THERMAL_SHUTDOWN",
    4: "NO_SCHEDULE",
    5: "NO_SATS",
    6: "OBSTRUCTED",
    7: "NO_DOWNLINK",
    8: "NO_PINGS",
    9: "ACTUATOR",
    10: "CABLE_TEST",
    11: "SLEEPING",
    13: "SKY_SEARCH",
    14: "INHIBIT_RF",
}

SOFTWARE_UPDATE = {
    0: "UNKNOWN",
    1: "IDLE",
    2: "FETCHING",
    3: "PRE_CHECK",
    4: "WRITING",
    5: "POST_CHECK",
    6: "REBOOT_REQUIRED",
    7: "DISABLED",
    8: "FAULTED",
}

MOBILITY = {0: "STATIONARY", 1: "NOMADIC", 2: "MOBILE"}
CLASS_OF_SERVICE = {
    0: "UNKNOWN",
    1: "CONSUMER",
    2: "BUSINESS",
    3: "BUSINESS_PLUS",
    4: "COMMERCIAL_AVIATION",
}
HAS_ACTUATORS = {0: "UNKNOWN", 1: "YES", 2: "NO"}
ACTUATOR_STATE = {
    0: "IDLE",
    1: "FULL_TILT",
    2: "ROTATE",
    3: "TILT",
    4: "UNWRAP+",
    5: "UNWRAP-",
    6: "TILT_TO_STOW",
    7: "FAULTED",
    8: "WAIT_STATIC",
    9: "DRIVE_MOBILE",
    10: "MOBILE_WAIT",
}
ATTITUDE = {
    0: "RESET",
    1: "UNCONVERGED",
    2: "CONVERGED",
    3: "FAULTED",
    4: "INVALID",
}

ALERT_NAMES = {
    1: "Motors stuck",
    2: "Thermal shutdown",
    3: "Thermal throttle",
    4: "Unexpected location",
    5: "Mast not near vertical",
    6: "Slow ethernet",
    7: "Roaming",
    8: "Install pending",
    9: "Heating",
    10: "Power supply thermal throttle",
    11: "Power save idle",
    14: "Telemetry stale",
    16: "Low motor current",
    17: "Lower signal than predicted",
    18: "Slow ethernet (100 Mbps)",
    19: "Obstruction map reset",
    20: "Water detected on dish",
    21: "Water detected on router",
    22: "Router port slow",
    23: "No ethernet link",
}

# Informational alerts that should not paint the bar red/amber.
ALERT_NOISE = {9, 11, 19}

DEVICE_INFO = {
    1: "str",
    2: "str",
    3: "str",
    4: "str",
    8: "u64",
    15: "str",
}
DEVICE_STATE = {1: "u64"}
OBSTRUCTION = {
    1: "f32",
    4: "f32",
    5: "bool",
    6: "f32",
    7: "f32",
    8: "bool",
    9: "f32",
    10: "u32",
}
ALERTS = {n: "bool" for n in ALERT_NAMES}
GPS = {1: "bool", 2: "u32", 3: "bool", 4: "bool", 5: "u32"}
OUTAGE = {1: "u32", 2: "u64", 3: "u64", 4: "bool"}
READY = {1: "bool", 2: "bool", 3: "bool", 4: "bool", 5: "bool", 6: "bool"}
UPDATE_STATS = {1: "u32", 2: "f32", 3: "bool"}
ALIGNMENT = {
    1: "u32",
    2: "u32",
    3: "f32",
    4: "f32",
    5: "f32",
    6: "u32",
    7: "f32",
    8: "f32",
    9: "f32",
}
INIT_DUR = {n: "u32" for n in range(1, 11)}
STATUS_MSG = {
    1: DEVICE_INFO,
    2: DEVICE_STATE,
    1002: "f32",
    1003: "f32",
    1004: OBSTRUCTION,
    1005: ALERTS,
    1007: "f32",
    1008: "f32",
    1009: "f32",
    1010: "bool",
    1011: "f32",
    1012: "f32",
    1014: OUTAGE,
    1015: GPS,
    1016: "i32",
    1017: "u32",
    1018: "bool",
    1019: READY,
    1020: "u32",
    1021: "u32",
    1022: "bool",
    1023: "u32",
    1024: "u32",
    1026: UPDATE_STATS,
    1027: ALIGNMENT,
    1028: INIT_DUR,
    1040: "str",
}
HISTORY_MSG = {
    1: "u64",
    1001: "packed_f32",
    1002: "packed_f32",
    1003: "packed_f32",
    1004: "packed_f32",
    1010: "packed_f32",
}
MAP_MSG = {1: "u32", 2: "u32", 3: "packed_f32"}
RESPONSE_STATUS = {3: "u64", RESP_DISH_STATUS: STATUS_MSG}
RESPONSE_HISTORY = {3: "u64", RESP_DISH_HISTORY: HISTORY_MSG}
RESPONSE_MAP = {3: "u64", RESP_DISH_MAP: MAP_MSG}


def encode_varint(n: int) -> bytes:
    out = bytearray()
    n = int(n)
    while True:
        bits = n & 0x7F
        n >>= 7
        if n:
            out.append(bits | 0x80)
        else:
            out.append(bits)
            break
    return bytes(out)


def decode_varint(buf: bytes, i: int) -> tuple[int, int]:
    n = 0
    shift = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not (b & 0x80):
            return n, i
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")
    raise ValueError("truncated varint")


def as_i32(n: int) -> int:
    n &= 0xFFFFFFFF
    return n - 0x100000000 if n >= 0x80000000 else n


def as_i64(n: int) -> int:
    n &= 0xFFFFFFFFFFFFFFFF
    return n - 0x10000000000000000 if n >= 0x8000000000000000 else n


def decode_message(buf: bytes, schema: dict) -> dict:
    i = 0
    out: dict = {}
    while i < len(buf):
        tag, i = decode_varint(buf, i)
        field = tag >> 3
        wire = tag & 7
        spec = schema.get(field)
        if wire == 0:
            raw, i = decode_varint(buf, i)
            if spec == "bool":
                val: object = bool(raw)
            elif spec == "i32":
                val = as_i32(raw)
            else:
                val = raw
        elif wire == 1:
            if i + 8 > len(buf):
                break
            val = struct.unpack_from("<d", buf, i)[0]
            i += 8
        elif wire == 5:
            if i + 4 > len(buf):
                break
            val = struct.unpack_from("<f", buf, i)[0]
            i += 4
        elif wire == 2:
            n, i = decode_varint(buf, i)
            blob = buf[i : i + n]
            i += n
            if isinstance(spec, dict):
                val = decode_message(blob, spec)
            elif spec == "str":
                val = blob.decode("utf-8", "replace")
            elif spec == "packed_f32":
                count = len(blob) // 4
                val = list(struct.unpack("<" + "f" * count, blob[: count * 4])) if count else []
            else:
                val = blob
        else:
            break
        prev = out.get(field)
        if prev is None:
            out[field] = val
        elif isinstance(prev, list):
            prev.append(val)
        else:
            out[field] = [prev, val]
    return out


def grpc_request(field: int) -> bytes:
    inner = encode_varint((field << 3) | 2) + b"\x00"
    return b"\x00" + struct.pack(">I", len(inner)) + inner


def parse_grpc_status(headers: str) -> tuple[int, str]:
    status = 0
    message = ""
    for line in headers.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "grpc-status":
            try:
                status = int(value.strip() or "0")
            except ValueError:
                status = 2
        elif key.strip().lower() == "grpc-message":
            message = value.strip()
    return status, message


def curl_handle(host: str, payload: bytes, timeout: float) -> tuple[str, bytes]:
    proc = subprocess.run(
        [
            CURL,
            "-sS",
            "--http2-prior-knowledge",
            "--max-time",
            f"{timeout:.1f}",
            "-D",
            "-",
            "-o",
            "-",
            "-H",
            "Content-Type: application/grpc",
            "-H",
            "TE: trailers",
            "-H",
            "grpc-accept-encoding: identity",
            "--data-binary",
            "@-",
            f"http://{host}/SpaceX.API.Device.Device/Handle",
        ],
        input=payload,
        capture_output=True,
        timeout=timeout + 1.5,
    )
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip() or f"curl exit {proc.returncode}"
        raise RuntimeError(err)
    raw = proc.stdout
    split = raw.find(b"\r\n\r\n")
    if split < 0:
        raise RuntimeError("no HTTP headers in dish response")
    headers = raw[:split].decode("utf-8", "replace")
    body = raw[split + 4 :]
    grpc_status, grpc_message = parse_grpc_status(headers)
    if grpc_status != 0:
        raise RuntimeError(grpc_message or f"grpc-status {grpc_status}")
    return headers, body


def decode_frame(body: bytes, schema: dict) -> dict:
    if len(body) < 5:
        raise RuntimeError("empty gRPC frame")
    compressed = body[0]
    length = struct.unpack(">I", body[1:5])[0]
    msg = body[5 : 5 + length]
    if compressed:
        raise RuntimeError("compressed gRPC frames are not supported")
    if len(msg) < length:
        raise RuntimeError("truncated gRPC frame")
    return decode_message(msg, schema)


def f32(msg: dict, field: int, default: float | None = None) -> float | None:
    val = msg.get(field, default)
    if val is None:
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return default
    return n if math.isfinite(n) else default


def u(msg: dict, field: int, default: int | None = None) -> int | None:
    val = msg.get(field, default)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def b(msg: dict, field: int) -> bool:
    return bool(msg.get(field))


def s(msg: dict, field: int, default: str = "") -> str:
    val = msg.get(field, default)
    return str(val) if val is not None else default


def sane_float(val: float | None, lo: float, hi: float) -> float | None:
    if val is None or not math.isfinite(val) or val < lo or val > hi:
        return None
    return val


def round_or_none(val: float | None, digits: int) -> float | None:
    if val is None or not math.isfinite(val):
        return None
    return round(val, digits)


def unwrap_ring(values: list, current: int) -> list:
    if not values:
        return []
    n = len(values)
    start = int(current) % n
    return list(values[start:]) + list(values[:start])


def downsample(values: list, count: int) -> list:
    if count <= 0 or not values:
        return []
    if len(values) <= count:
        return list(values)
    last = len(values) - 1
    out = []
    for i in range(count):
        idx = round(i * last / (count - 1)) if count > 1 else last
        out.append(values[idx])
    return out


def clean_series(values: list, digits: int) -> list:
    out = []
    for val in values:
        try:
            n = float(val)
        except (TypeError, ValueError):
            out.append(None)
            continue
        if not math.isfinite(n):
            out.append(None)
        else:
            out.append(round(n, digits))
    return out


def downsample_grid(snr: list, rows: int, cols: int, target: int) -> tuple[int, int, list]:
    if rows <= 0 or cols <= 0 or not snr:
        return 0, 0, []
    if rows <= target and cols <= target:
        return rows, cols, list(snr[: rows * cols])
    out = []
    for y in range(target):
        y0 = y * rows // target
        y1 = max(y0 + 1, (y + 1) * rows // target)
        for x in range(target):
            x0 = x * cols // target
            x1 = max(x0 + 1, (x + 1) * cols // target)
            worst = None
            for yy in range(y0, y1):
                base = yy * cols
                for xx in range(x0, x1):
                    idx = base + xx
                    if idx >= len(snr):
                        continue
                    val = snr[idx]
                    try:
                        n = float(val)
                    except (TypeError, ValueError):
                        continue
                    if not math.isfinite(n) or n < 0:
                        continue
                    if worst is None or n < worst:
                        worst = n
            out.append(-1.0 if worst is None else round(worst, 3))
    return target, target, out


def collect_alerts(alerts: dict) -> list[str]:
    names = []
    if not isinstance(alerts, dict):
        return names
    for field, name in ALERT_NAMES.items():
        if field in ALERT_NOISE:
            continue
        if alerts.get(field):
            names.append(name)
    return names


def derive_state(status: dict) -> tuple[str, str]:
    if status.get("outage"):
        cause = str(status["outage"].get("cause") or "OUTAGE")
        return cause.replace("_", " ").title().replace(" ", ""), cause.replace("_", " ").title()
    if status.get("currentlyObstructed"):
        return "OBSTRUCTED", "Dish is currently obstructed"
    code = status.get("disablement") or "OKAY"
    if code not in ("", "OKAY", "UNKNOWN"):
        return "DISABLED", code.replace("_", " ").title()
    if status.get("stowRequested"):
        return "STOWED", "Stow requested"
    if status.get("snrAboveNoiseFloor") is False:
        return "SEARCHING", "Signal below noise floor"
    return "CONNECTED", "Online"


def parse_status(msg: dict) -> dict:
    info = msg.get(1) or {}
    state = msg.get(2) or {}
    obst = msg.get(1004) or {}
    alerts = msg.get(1005) or {}
    gps = msg.get(1015) or {}
    outage_msg = msg.get(1014) or {}
    align = msg.get(1027) or {}
    update = msg.get(1026) or {}

    outage = None
    if outage_msg:
        cause = OUTAGE_CAUSE.get(int(outage_msg.get(1) or 0), "UNKNOWN")
        outage = {
            "cause": cause,
            "durationNs": u(outage_msg, 3, 0) or 0,
        }

    ping = sane_float(f32(msg, 1009), 0, 5000)
    down = sane_float(f32(msg, 1007), 0, 1e12)
    up = sane_float(f32(msg, 1008), 0, 1e12)
    drop = sane_float(f32(msg, 1003), 0, 1)
    fraction = sane_float(f32(obst, 1), 0, 1)
    az = sane_float(f32(align, 4), -360, 360)
    if az is None:
        az = sane_float(f32(msg, 1011), -360, 360)
    el = sane_float(f32(align, 5), -90, 90)
    if el is None:
        el = sane_float(f32(msg, 1012), -90, 90)
    tilt = sane_float(f32(align, 3), -180, 180)

    status = {
        "deviceId": s(info, 1),
        "hardware": s(info, 2),
        "software": s(info, 3),
        "country": s(info, 4),
        "bootcount": u(info, 8, 0) or 0,
        "uptimeS": u(state, 1, 0) or 0,
        "downBps": round_or_none(down, 1),
        "upBps": round_or_none(up, 1),
        "pingMs": round_or_none(ping, 1),
        "dropRate": round_or_none(drop, 4),
        "obstructionPct": round((fraction or 0) * 100, 2),
        "currentlyObstructed": b(obst, 5),
        "timeObstructedS": round_or_none(sane_float(f32(obst, 9), 0, 1e7), 2),
        "snrAboveNoiseFloor": b(msg, 1018) if 1018 in msg else None,
        "snrPersistentlyLow": b(msg, 1022) if 1022 in msg else None,
        "azDeg": round_or_none(az, 1),
        "elDeg": round_or_none(el, 1),
        "tiltDeg": round_or_none(tilt, 1),
        "desiredAzDeg": round_or_none(sane_float(f32(align, 8), -360, 360), 1),
        "desiredElDeg": round_or_none(sane_float(f32(align, 9), -90, 90), 1),
        "attitude": ATTITUDE.get(int(align.get(6) or 0), "UNKNOWN") if align else "",
        "actuatorState": ACTUATOR_STATE.get(int(align.get(2) or 0), "IDLE") if align else "",
        "gpsValid": b(gps, 1) if gps else None,
        "gpsSats": u(gps, 2, 0) or 0,
        "ethMbps": u(msg, 1016, 0) or 0,
        "stowRequested": b(msg, 1010),
        "mobility": MOBILITY.get(int(msg.get(1017) or 0), "STATIONARY"),
        "classOfService": CLASS_OF_SERVICE.get(int(msg.get(1020) or 0), "UNKNOWN"),
        "hasActuators": HAS_ACTUATORS.get(int(msg.get(1023) or 0), "UNKNOWN"),
        "softwareUpdate": SOFTWARE_UPDATE.get(int((update.get(1) if update else None) or msg.get(1021) or 0), "UNKNOWN"),
        "disablement": DISABLEMENT.get(int(msg.get(1024) or 0), "UNKNOWN"),
        "routerId": s(msg, 1040),
        "alerts": collect_alerts(alerts if isinstance(alerts, dict) else {}),
        "outage": outage,
    }
    state_name, reason = derive_state(status)
    status["state"] = state_name
    status["stateReason"] = reason
    return status


def parse_history(msg: dict) -> dict:
    current = int(msg.get(1) or 0)
    ping = unwrap_ring(msg.get(1002) or [], current)
    drop = unwrap_ring(msg.get(1001) or [], current)
    down = unwrap_ring(msg.get(1003) or [], current)
    up = unwrap_ring(msg.get(1004) or [], current)
    return {
        "current": current,
        "count": max(len(ping), len(down), len(up), len(drop)),
        "ping": ping,
        "drop": drop,
        "down": down,
        "up": up,
        "pingSpark": clean_series(downsample(ping, 90), 2),
        "downSpark": clean_series(downsample(down, 90), 1),
        "upSpark": clean_series(downsample(up, 90), 1),
    }


def finite(val) -> float | None:
    try:
        n = float(val)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def analyzed_speed(samples: list, min_active: int) -> float | None:
    """Average active download, dropping the fastest 10% so short spikes do not win."""
    active = sorted(
        n for n in (finite(x) for x in samples) if n is not None and n >= IDLE_BPS
    )
    if len(active) < min_active:
        return None
    if len(active) >= 10:
        active = active[: max(min_active, len(active) - max(1, len(active) // 10))]
    return sum(active) / len(active)


def db_connect() -> sqlite3.Connection:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DIR / "samples.sqlite"), timeout=6)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS samples (
            ts INTEGER PRIMARY KEY,
            dish_index INTEGER NOT NULL,
            down REAL,
            up REAL,
            ping REAL,
            drop_rate REAL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_dish ON samples(dish_index)")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )"""
    )
    return conn


def meta_get(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def meta_set(conn: sqlite3.Connection, key: str, value: object) -> None:
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, str(value)))


def ingest_samples(conn: sqlite3.Connection, hist: dict, now: datetime) -> int:
    down = hist.get("down") or []
    ping = hist.get("ping") or []
    up = hist.get("up") or []
    drop = hist.get("drop") or []
    current = int(hist.get("current") or 0)
    n = max(len(down), len(ping), len(up))
    if n == 0 or current <= 0:
        return 0
    last = int(meta_get(conn, "lastDishIndex", "0") or 0)
    start_index = current - n + 1
    now_ts = int(now.timestamp())
    added = 0
    for i in range(n):
        idx = start_index + i
        if idx <= last:
            continue
        ts = now_ts - (n - 1 - i)
        conn.execute(
            "INSERT OR REPLACE INTO samples(ts, dish_index, down, up, ping, drop_rate) VALUES (?, ?, ?, ?, ?, ?)",
            (
                ts,
                idx,
                finite(down[i]) if i < len(down) else None,
                finite(up[i]) if i < len(up) else None,
                finite(ping[i]) if i < len(ping) else None,
                finite(drop[i]) if i < len(drop) else None,
            ),
        )
        added += 1
    if current > last:
        meta_set(conn, "lastDishIndex", current)
    conn.execute("DELETE FROM samples WHERE ts < ?", (now_ts - KEEP_DAYS * 86400,))
    conn.commit()
    return added


def load_rows(conn: sqlite3.Connection, start_ts: int) -> list[tuple[int, float | None, float | None]]:
    return conn.execute(
        "SELECT ts, down, ping FROM samples WHERE ts >= ? ORDER BY ts",
        (int(start_ts),),
    ).fetchall()


def bucketize(rows: list, start: int, end: int, step: int, min_active: int) -> tuple[list, list]:
    groups: dict[int, dict[str, list]] = {}
    for ts, down, ping in rows:
        if ts < start or ts >= end:
            continue
        key = start + ((int(ts) - start) // step) * step
        bucket = groups.get(key)
        if bucket is None:
            bucket = {"down": [], "ping": []}
            groups[key] = bucket
        if down is not None:
            bucket["down"].append(down)
        if ping is not None:
            bucket["ping"].append(ping)
    down_out = []
    ping_out = []
    t = start
    while t < end:
        bucket = groups.get(t)
        if bucket:
            speed = analyzed_speed(bucket["down"], min_active)
            down_out.append(round(speed / 1e6, 2) if speed is not None else None)
            ping_vals = [p for p in bucket["ping"] if finite(p) is not None and 0 <= p <= 5000]
            ping_med = median(ping_vals)
            ping_out.append(round(ping_med, 1) if ping_med is not None else None)
        else:
            down_out.append(None)
            ping_out.append(None)
        t += step
    return down_out, ping_out


def analyze(conn: sqlite3.Connection, now: datetime, current_ping: float | None) -> tuple[dict, dict]:
    now_ts = int(now.timestamp())
    local_midnight = datetime.combine(now.date(), datetime.min.time(), tzinfo=now.tzinfo)
    day_start = int(local_midnight.timestamp())
    rows = load_rows(conn, min(day_start, now_ts - 900))

    last_minute = [(ts, down, ping) for ts, down, ping in rows if ts >= now_ts - 60]
    speed = analyzed_speed([down for _, down, _ in last_minute], MINUTE_ACTIVE_S)
    last_known = meta_get(conn, "lastSpeedMbps")
    last_known_ts = meta_get(conn, "lastSpeedTs")
    held = speed is None
    if speed is not None:
        speed_mbps = round(speed / 1e6, 2)
        meta_set(conn, "lastSpeedMbps", speed_mbps)
        meta_set(conn, "lastSpeedTs", now_ts)
        conn.commit()
    else:
        try:
            known_ts = int(last_known_ts) if last_known_ts is not None else 0
        except (TypeError, ValueError):
            known_ts = 0
        # Held speed is last busy minute, but never yesterday's leftover.
        if known_ts < day_start:
            speed_mbps = None
        else:
            try:
                speed_mbps = float(last_known) if last_known is not None else None
            except (TypeError, ValueError):
                speed_mbps = None

    spark_start = now_ts - 900
    spark_down, spark_ping = bucketize(rows, spark_start, now_ts + 1, 15, SPARK_ACTIVE_S)
    day_down, day_ping = bucketize(rows, day_start, now_ts + 1, 60, BUCKET_ACTIVE_S)

    day_buckets = []
    speeds = []
    pings = []
    for i, down in enumerate(day_down):
        ping = day_ping[i] if i < len(day_ping) else None
        if down is None and ping is None:
            continue
        minute = int(((day_start + i * 60) - day_start) / 60)
        day_buckets.append({"t": minute, "down": down, "ping": ping})
        if down is not None:
            speeds.append(down)
        if ping is not None:
            pings.append(ping)

    # Last-minute typical speed can beat any finished calendar-minute bucket.
    # Fold it into the current chart column and today's peak immediately.
    cur_minute = max(0, (now_ts - day_start) // 60)
    if speed_mbps is not None:
        if day_buckets and day_buckets[-1]["t"] == cur_minute:
            prev = day_buckets[-1].get("down")
            if prev is None or speed_mbps > prev:
                day_buckets[-1]["down"] = speed_mbps
        else:
            day_buckets.append({
                "t": cur_minute,
                "down": speed_mbps,
                "ping": round_or_none(current_ping, 1),
            })

    today = now.strftime("%Y-%m-%d")
    stored_peak = None
    if meta_get(conn, "todayPeakDate") == today:
        try:
            stored_peak = float(meta_get(conn, "todayPeakMbps"))
        except (TypeError, ValueError):
            stored_peak = None
    peak_candidates = [n for n in (*speeds, speed_mbps, stored_peak) if n is not None]
    peak_mbps = round(max(peak_candidates), 2) if peak_candidates else None
    if peak_mbps is not None:
        meta_set(conn, "todayPeakMbps", peak_mbps)
        meta_set(conn, "todayPeakDate", today)
        conn.commit()

    active = sum(1 for _, down, _ in last_minute if finite(down) is not None and down >= IDLE_BPS)
    scale = 40.0
    if speeds:
        ranked = sorted(speeds)
        p90 = ranked[min(len(ranked) - 1, max(0, int(round((len(ranked) - 1) * 0.9))))]
        scale = max(40.0, float(p90), float(speed_mbps or 0))
    elif speed_mbps:
        scale = max(40.0, float(speed_mbps))
    drop_row = conn.execute(
        "SELECT AVG(COALESCE(drop_rate, 0)) FROM samples WHERE ts >= ?",
        (now_ts - 900,),
    ).fetchone()
    drop_avg = float(drop_row[0]) if drop_row and drop_row[0] is not None else 0.0
    ping_success = round(100.0 * (1.0 - min(1.0, max(0.0, drop_avg))), 1)
    minute = {
        "downMbps": speed_mbps,
        "pingMs": round_or_none(current_ping, 1),
        "held": held,
        "activePct": round(active / max(1, len(last_minute)), 2) if last_minute else 0,
        "samples": len(last_minute),
        "stored": conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0],
        "scaleMbps": round(scale, 1),
        "pingSuccess": ping_success,
        "down": spark_down,
        "ping": spark_ping,
    }
    # Transfer, ping range, peak, and drop time are the local calendar day, not a rolling 24h.
    xfer = conn.execute(
        "SELECT COALESCE(SUM(down), 0), COALESCE(SUM(up), 0) FROM samples WHERE ts >= ?",
        (day_start,),
    ).fetchone()
    down_bytes = int((xfer[0] or 0) / 8)
    up_bytes = int((xfer[1] or 0) / 8)
    ping_row = conn.execute(
        "SELECT MIN(ping), MAX(ping) FROM samples WHERE ts >= ? AND ping IS NOT NULL AND ping >= 0 AND ping <= 5000",
        (day_start,),
    ).fetchone()
    drop_secs = conn.execute(
        "SELECT COUNT(*) FROM samples WHERE ts >= ? AND drop_rate IS NOT NULL AND drop_rate > 0",
        (day_start,),
    ).fetchone()
    ping_min = round_or_none(ping_row[0] if ping_row else None, 1)
    ping_max = round_or_none(ping_row[1] if ping_row else None, 1)
    if current_ping is not None and 0 <= current_ping <= 5000:
        ping_min = current_ping if ping_min is None else min(ping_min, current_ping)
        ping_max = current_ping if ping_max is None else max(ping_max, current_ping)
        ping_min = round_or_none(ping_min, 1)
        ping_max = round_or_none(ping_max, 1)
    day = {
        "date": today,
        "buckets": day_buckets,
        "speedMbps": round(median(speeds), 2) if speeds else None,
        "pingMs": round(median(pings), 1) if pings else None,
        "pingMin": ping_min,
        "pingMax": ping_max,
        "peakMbps": peak_mbps,
        "dropSeconds": int(drop_secs[0] if drop_secs else 0),
        "samples": len(speeds),
        "downBytes": down_bytes,
        "upBytes": up_bytes,
    }
    return minute, day


def parse_map(msg: dict) -> dict:
    rows = int(msg.get(1) or 0)
    cols = int(msg.get(2) or 0)
    snr = msg.get(3) or []
    rows, cols, snr = downsample_grid(snr, rows, cols, 41)
    return {"rows": rows, "cols": cols, "snr": snr}


def normalize_map(data) -> dict | None:
    if not isinstance(data, dict):
        return None
    try:
        rows = int(data.get("rows") or 0)
        cols = int(data.get("cols") or 0)
    except (TypeError, ValueError):
        return None
    snr = data.get("snr")
    if rows <= 0 or cols <= 0 or not isinstance(snr, list) or len(snr) < rows * cols:
        return None
    return {"rows": rows, "cols": cols, "snr": snr[: rows * cols]}


def load_cached_map() -> dict | None:
    try:
        return normalize_map(json.loads(MAP_CACHE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_cached_map(parsed: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = MAP_CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(parsed, separators=(",", ":")), encoding="utf-8")
    tmp.replace(MAP_CACHE)


def fetch_history_and_map(host: str) -> tuple[dict | None, dict | None, str, str]:
    hist = None
    parsed_map = None
    hist_err = ""
    map_err = ""
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_hist = pool.submit(call_dish, [host], REQ_GET_HISTORY, RESPONSE_HISTORY, 8.0)
        fut_map = pool.submit(call_dish, [host], REQ_GET_OBSTRUCTION_MAP, RESPONSE_MAP, 8.0)
        try:
            _, hist_raw = fut_hist.result()
            hist_msg = hist_raw.get(RESP_DISH_HISTORY)
            if isinstance(hist_msg, dict):
                hist = parse_history(hist_msg)
        except Exception as exc:
            hist_err = str(exc)
        try:
            _, map_raw = fut_map.result()
            map_msg = map_raw.get(RESP_DISH_MAP)
            if isinstance(map_msg, dict):
                parsed_map = parse_map(map_msg)
        except Exception as exc:
            map_err = str(exc)
    return hist, parsed_map, hist_err, map_err


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hosts_to_try(explicit: str) -> list[str]:
    env = os.environ.get("STARLINK_DISH_HOST") or os.environ.get("STARLINK_HOST") or ""
    ordered = []
    for host in (explicit, env, *DEFAULT_HOSTS):
        host = str(host or "").strip()
        if not host:
            continue
        if ":" not in host:
            host = host + ":9200"
        if host not in ordered:
            ordered.append(host)
    return ordered


def call_dish(hosts: list[str], field: int, schema: dict, timeout: float) -> tuple[str, dict]:
    errors = []
    for host in hosts:
        try:
            _headers, body = curl_handle(host, grpc_request(field), timeout)
            return host, decode_frame(body, schema)
        except Exception as exc:
            errors.append(f"{host}: {exc}")
    raise RuntimeError("; ".join(errors) or "no dish hosts")


def emit(payload: dict, pretty: bool) -> int:
    json.dump(payload, sys.stdout, separators=(",", ":") if not pretty else None, indent=2 if pretty else None)
    sys.stdout.write("\n")
    return 0 if payload.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Starlink dish stats for the Omarchy bar")
    parser.add_argument("mode", nargs="?", default="status", choices=("status", "details"))
    parser.add_argument("--host", default="", help="Dish gRPC host:port (default 192.168.100.1:9200)")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    hosts = hosts_to_try(args.host)
    now = datetime.now().astimezone()
    report = {
        "ok": False,
        "error": "",
        "host": hosts[0] if hosts else "",
        "fetchedAt": now_iso(),
        "status": None,
        "minute": None,
        "day": None,
        "history": None,
        "map": None,
    }
    try:
        host, raw = call_dish(hosts, REQ_GET_STATUS, RESPONSE_STATUS, 4.0)
        report["host"] = host
        status_msg = raw.get(RESP_DISH_STATUS)
        if not isinstance(status_msg, dict):
            raise RuntimeError("dish did not return status")
        status = parse_status(status_msg)
        report["status"] = status
        report["ok"] = True

        hist = None
        if args.mode == "details":
            hist, parsed_map, hist_err, map_err = fetch_history_and_map(host)
            if hist_err:
                report["historyError"] = hist_err
            if parsed_map:
                report["map"] = parsed_map
                try:
                    save_cached_map(parsed_map)
                except OSError as exc:
                    report["mapCacheError"] = str(exc)
            else:
                cached_map = load_cached_map()
                if cached_map:
                    report["map"] = cached_map
                if map_err:
                    report["mapError"] = map_err
        else:
            try:
                _, hist_raw = call_dish([host], REQ_GET_HISTORY, RESPONSE_HISTORY, 8.0)
                hist_msg = hist_raw.get(RESP_DISH_HISTORY)
                if isinstance(hist_msg, dict):
                    hist = parse_history(hist_msg)
            except Exception as exc:
                report["historyError"] = str(exc)

        try:
            conn = db_connect()
            if hist:
                ingest_samples(conn, hist, now)
            minute, day = analyze(conn, now, status.get("pingMs"))
            report["minute"] = minute
            report["day"] = day
            conn.close()
        except Exception as exc:
            report["storeError"] = str(exc)

        if hist and args.mode == "details":
            report["history"] = {
                "current": hist.get("current"),
                "count": hist.get("count"),
                "ping": hist.get("pingSpark"),
                "down": hist.get("downSpark"),
                "up": hist.get("upSpark"),
            }
    except Exception as exc:
        report["error"] = str(exc)
        report["ok"] = False

    return emit(report, args.pretty)


if __name__ == "__main__":
    raise SystemExit(main())
