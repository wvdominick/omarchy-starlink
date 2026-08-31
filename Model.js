function parseReport(raw) {
  try {
    var data = JSON.parse(String(raw || "{}"))
    if (!data || typeof data !== "object")
      return emptyReport("empty")
    return {
      ok: data.ok !== false,
      error: data.error || "",
      host: data.host || "",
      fetchedAt: data.fetchedAt || "",
      status: data.status && typeof data.status === "object" ? data.status : null,
      minute: data.minute && typeof data.minute === "object" ? data.minute : null,
      day: data.day && typeof data.day === "object" ? data.day : null,
      history: data.history && typeof data.history === "object" ? data.history : null,
      map: data.map && typeof data.map === "object" ? data.map : null
    }
  } catch (e) {
    return emptyReport("bad json")
  }
}

function parseMapCache(raw) {
  try {
    var data = JSON.parse(String(raw || ""))
    if (!data || typeof data !== "object") return null
    var rows = parseInt(data.rows, 10)
    var cols = parseInt(data.cols, 10)
    if (!isFinite(rows) || !isFinite(cols) || rows <= 0 || cols <= 0) return null
    if (!data.snr || !data.snr.length) return null
    return { rows: rows, cols: cols, snr: data.snr }
  } catch (e) {
    return null
  }
}

function emptyReport(error) {
  return {
    ok: false,
    error: error || "",
    status: null,
    minute: null,
    day: null,
    history: null,
    map: null,
    host: "",
    fetchedAt: ""
  }
}

function formatMbps(bps) {
  if (bps === null || bps === undefined || bps === "") return "—"
  var n = Number(bps)
  if (!isFinite(n) || n < 0) return "—"
  return formatMbpsDirect(n / 1e6)
}

function formatMbpsDirect(mbps) {
  if (mbps === null || mbps === undefined || mbps === "") return "—"
  var n = Number(mbps)
  if (!isFinite(n) || n < 0) return "—"
  if (n < 0.05) return n.toFixed(2)
  if (n < 10) return n.toFixed(1)
  return String(Math.round(n))
}

function formatMbpsUnit(bps) {
  var value = formatMbps(bps)
  return value === "—" ? value : value + " Mbps"
}

function formatMbpsUnitDirect(mbps) {
  var value = formatMbpsDirect(mbps)
  return value === "—" ? value : value + " Mbps"
}

function formatBytes(n) {
  n = Number(n)
  if (!isFinite(n) || n < 0) return "—"
  var units = ["B", "KB", "MB", "GB", "TB"]
  var i = 0
  while (n >= 1000 && i < units.length - 1) {
    n /= 1000
    i++
  }
  if (i === 0) return Math.round(n) + " " + units[i]
  if (n < 10) return n.toFixed(1) + " " + units[i]
  if (n < 100) return n.toFixed(1) + " " + units[i]
  return Math.round(n) + " " + units[i]
}

function formatBytesCompact(n) {
  n = Number(n)
  if (!isFinite(n) || n < 0) return "—"
  var units = ["B", "K", "M", "G", "T"]
  var i = 0
  while (n >= 1000 && i < units.length - 1) {
    n /= 1000
    i++
  }
  if (i === 0) return Math.round(n) + units[i]
  if (n < 10) return n.toFixed(1) + units[i]
  return Math.round(n) + units[i]
}

function formatTransfer(day) {
  if (!day) return "—"
  var down = formatBytesCompact(day.downBytes)
  var up = formatBytesCompact(day.upBytes)
  if (down === "—" && up === "—") return "—"
  return down + "↓  " + up + "↑"
}

function formatPingRange(day) {
  if (!day) return "—"
  if (day.pingMin === null || day.pingMin === undefined || day.pingMax === null || day.pingMax === undefined)
    return "—"
  var a = Math.round(Number(day.pingMin))
  var b = Math.round(Number(day.pingMax))
  if (!isFinite(a) || !isFinite(b)) return "—"
  if (a === b) return a + " ms"
  return a + "–" + b + " ms"
}

function formatTodayPingRange(day, liveMs) {
  var min = day && day.pingMin
  var max = day && day.pingMax
  var live = Number(liveMs)
  if (isFinite(live) && live >= 0) {
    if (min === null || min === undefined || live < Number(min)) min = live
    if (max === null || max === undefined || live > Number(max)) max = live
  }
  var range = formatPingRange({ pingMin: min, pingMax: max })
  return range === "—" ? "" : "today " + range
}

function formatTodayPeak(day, minute) {
  var peak = day ? Number(day.peakMbps) : NaN
  var live = minute ? Number(minute.downMbps) : NaN
  var n = null
  if (isFinite(peak) && isFinite(live)) n = Math.max(peak, live)
  else if (isFinite(peak)) n = peak
  else if (isFinite(live)) n = live
  var text = formatMbpsUnitDirect(n)
  return text === "—" ? "" : "Today's peak " + text
}

function formatDuration(seconds) {
  var s = parseInt(seconds, 10)
  if (!isFinite(s) || s <= 0) return "0s"
  if (s < 60) return s + "s"
  var m = Math.floor(s / 60)
  var r = s % 60
  if (m < 60) return r ? (m + "m " + r + "s") : (m + "m")
  var h = Math.floor(m / 60)
  m = m % 60
  return m ? (h + "h " + m + "m") : (h + "h")
}

function formatMs(ms) {
  if (ms === null || ms === undefined || ms === "") return "—"
  var n = Number(ms)
  if (!isFinite(n) || n < 0) return "—"
  if (n < 10) return n.toFixed(1) + " ms"
  return Math.round(n) + " ms"
}

function formatMsCompact(ms) {
  if (ms === null || ms === undefined || ms === "") return "—"
  var n = Number(ms)
  if (!isFinite(n) || n < 0) return "—"
  if (n < 10) return n.toFixed(1) + "ms"
  return Math.round(n) + "ms"
}

function formatUptime(seconds) {
  var s = parseInt(seconds, 10)
  if (!isFinite(s) || s < 0) return "—"
  var d = Math.floor(s / 86400)
  var h = Math.floor((s % 86400) / 3600)
  var m = Math.floor((s % 3600) / 60)
  if (d > 0) return d + "d " + h + "h"
  if (h > 0) return h + "h " + m + "m"
  return m + "m"
}

function formatPct(value) {
  if (value === null || value === undefined || value === "") return "—"
  var n = Number(value)
  if (!isFinite(n) || n < 0) return "—"
  if (n < 0.1) return n.toFixed(2) + "%"
  if (n < 10) return n.toFixed(1) + "%"
  return Math.round(n) + "%"
}

function formatDeg(value) {
  if (value === null || value === undefined || value === "") return "—"
  var n = Number(value)
  if (!isFinite(n)) return "—"
  return (n >= 0 ? "+" : "") + n.toFixed(1) + "°"
}

function formatHour(minute) {
  var h = Math.floor(Number(minute) / 60)
  if (!isFinite(h)) return ""
  var ap = h >= 12 ? "p" : "a"
  h = h % 12
  if (h === 0) h = 12
  return h + ap
}

function icon() {
  return "󰑩"
}

function tone(status, ok) {
  if (!ok) return "off"
  if (!status) return "off"
  var state = String(status.state || "")
  if (state === "CONNECTED") return (status.alerts && status.alerts.length) ? "warn" : "ok"
  if (state === "OBSTRUCTED" || state === "SEARCHING" || state === "SkySearch" || state === "NO_SCHEDULE")
    return "warn"
  return "bad"
}

function stateLabel(status, ok) {
  if (!ok && !status) return "OFFLINE"
  if (!status) return "WAITING"
  return String(status.state || "UNKNOWN")
}

function barSpeedText(minute) {
  if (!minute) return "—"
  var n = formatMbpsDirect(minute.downMbps)
  return n === "—" ? n : n + "↓"
}

function barPingText(status, minute) {
  var ping = status && status.pingMs !== undefined && status.pingMs !== null
    ? status.pingMs
    : (minute ? minute.pingMs : null)
  return formatMsCompact(ping)
}

function barSuccessText(minute) {
  if (!minute || minute.pingSuccess === undefined || minute.pingSuccess === null) return "—"
  var n = Number(minute.pingSuccess)
  if (!isFinite(n)) return "—"
  if (n >= 99.5) return "100%"
  if (n >= 10) return n.toFixed(0) + "%"
  return n.toFixed(1) + "%"
}

function barLine(status, minute, ok) {
  if (!ok) return "offline"
  var state = status ? String(status.state || "") : ""
  if (state && state !== "CONNECTED") return state
  var ping = barPingText(status, minute)
  var success = barSuccessText(minute)
  var speed = barSpeedText(minute)
  var parts = []
  if (ping !== "—") parts.push(ping)
  if (success !== "—") parts.push(success)
  if (speed !== "—") parts.push(speed)
  return parts.join("  ")
}

function pingQuality(ms, status, ok, success) {
  if (!ok) return "off"
  if (status && status.currentlyObstructed) return "bad"
  var state = status ? String(status.state || "") : ""
  if (state && state !== "CONNECTED") return state === "SEARCHING" || state === "OBSTRUCTED" ? "warn" : "bad"
  var hit = Number(success)
  if (isFinite(hit) && hit < 95) return "bad"
  if (isFinite(hit) && hit < 98.5) return "warn"
  var n = Number(ms)
  if (!isFinite(n)) return "off"
  if (n >= 100) return "bad"
  if (n >= 60) return "warn"
  return "ok"
}

function speedFill(minute) {
  if (!minute) return 0
  var speed = Number(minute.downMbps)
  var scale = Number(minute.scaleMbps)
  if (!isFinite(speed) || speed <= 0) return 0
  if (!isFinite(scale) || scale <= 0) scale = 40
  return Math.max(0, Math.min(1, speed / scale))
}

function tooltip(status, ok, error, host, minute, day) {
  if (!ok) return error || "Dish unreachable"
  var state = status ? String(status.state || "") : ""
  if (state && state !== "CONNECTED") return stateLabel(status, ok)
  if (status && status.currentlyObstructed) return "Obstructed"
  return ""
}

function seriesExtent(values, pad) {
  var min = null
  var max = null
  values = values || []
  for (var i = 0; i < values.length; i++) {
    var n = Number(values[i])
    if (!isFinite(n)) continue
    if (min === null || n < min) min = n
    if (max === null || n > max) max = n
  }
  if (min === null) return { min: 0, max: 1 }
  if (min === max) {
    var span = Math.max(Math.abs(min) * 0.1, 1)
    return { min: Math.max(0, min - span), max: max + span }
  }
  pad = pad === undefined ? 0.08 : pad
  var extra = (max - min) * pad
  return { min: Math.max(0, min - extra), max: max + extra }
}

function minuteOfDay(date) {
  date = date || new Date()
  return date.getHours() * 60 + date.getMinutes()
}

function dayDomain(buckets, now) {
  buckets = buckets || []
  var end = minuteOfDay(now)
  if (!buckets.length) return { start: Math.max(0, end - 60), end: end }
  var start = end
  for (var i = 0; i < buckets.length; i++) {
    var t = Number(buckets[i] && buckets[i].t)
    if (!isFinite(t)) continue
    if (t < start) start = t
  }
  if (end - start < 30) start = Math.max(0, end - 30)
  return { start: start, end: Math.max(end, start + 1) }
}

function hourTicks(start, end) {
  var ticks = []
  var first = Math.ceil(start / 60) * 60
  for (var t = first; t <= end; t += 60) ticks.push(t)
  if (!ticks.length) ticks.push(start)
  return ticks
}

if (typeof module !== "undefined") {
  module.exports = {
    parseReport: parseReport,
    parseMapCache: parseMapCache,
    formatMbps: formatMbps,
    formatMbpsDirect: formatMbpsDirect,
    formatMbpsUnit: formatMbpsUnit,
    formatMbpsUnitDirect: formatMbpsUnitDirect,
    formatBytes: formatBytes,
    formatTransfer: formatTransfer,
    formatPingRange: formatPingRange,
    formatTodayPingRange: formatTodayPingRange,
    formatTodayPeak: formatTodayPeak,
    formatDuration: formatDuration,
    formatMs: formatMs,
    formatMsCompact: formatMsCompact,
    formatUptime: formatUptime,
    formatPct: formatPct,
    formatDeg: formatDeg,
    formatHour: formatHour,
    icon: icon,
    tone: tone,
    stateLabel: stateLabel,
    barSpeedText: barSpeedText,
    barPingText: barPingText,
    barSuccessText: barSuccessText,
    barLine: barLine,
    pingQuality: pingQuality,
    speedFill: speedFill,
    tooltip: tooltip,
    seriesExtent: seriesExtent,
    minuteOfDay: minuteOfDay,
    dayDomain: dayDomain,
    hourTicks: hourTicks
  }
}
