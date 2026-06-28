#!/usr/bin/env python3
"""Deskbuddy Configurator — local build system & feature manager"""

import os, json, subprocess, threading, queue, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_DIR = Path(__file__).parent
CONFIG_FILE  = PROJECT_DIR / "deskbuddy_config.json"
SECRETS_H    = PROJECT_DIR / "include" / "secrets.h"
PIO_INI      = PROJECT_DIR / "platformio.ini"

DEFAULT_CONFIG = {
    "wifi_ssid":   "",
    "wifi_pass":   "",
    "device_ip":   "192.168.2.17",
    "location":    "Amsterdam",
    "lat":         52.3676,
    "lng":         4.9041,
    "timezone":    "europe_central",
    "units":       "metric",
    "region":      "europe",
    "nickname":    "",
    "modules": {
        "sticky_notes_api":  False,
        "get_note_api":      False,
        "ha_sensors":        False,
        "ha_webhooks":       False,
        "ha_scenes":         False,
        "ha_now_playing":    False,
        "habit_tracker":     False,
        "hydration_tracker": False,
        "context_clock":     False,
        "wfh_commute":       False,
        "eye_break":         False,
        "movement_reminder": False,
        "lunar_phase":       False,
        "daily_quote":       False,
        "ghost_mode":        False,
        "ambient_color":     False,
        "tamagotchi":        False,
    }
}

# ── Build state ─────────────────────────────────────────────────────────────
_build_queue  = queue.Queue()
_build_lock   = threading.Lock()
_build_active = False

def _run_pio(args: list[str]):
    global _build_active
    with _build_lock:
        if _build_active:
            return
        _build_active = True

    while not _build_queue.empty():
        try: _build_queue.get_nowait()
        except: pass

    def worker():
        global _build_active
        try:
            cmd = ["pio"] + args
            proc = subprocess.Popen(
                cmd, cwd=str(PROJECT_DIR),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
            for line in proc.stdout:
                _build_queue.put({"t": "line", "v": line.rstrip()})
            proc.wait()
            status = "success" if proc.returncode == 0 else "error"
            _build_queue.put({"t": "done", "v": status})
        except Exception as e:
            _build_queue.put({"t": "line", "v": f"ERROR: {e}"})
            _build_queue.put({"t": "done", "v": "error"})
        finally:
            _build_active = False

    threading.Thread(target=worker, daemon=True).start()

# ── Config helpers ───────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            cfg = json.loads(json.dumps(DEFAULT_CONFIG))
            cfg.update({k: v for k, v in saved.items() if k != "modules"})
            cfg["modules"].update(saved.get("modules", {}))
            return cfg
        except: pass
    return json.loads(json.dumps(DEFAULT_CONFIG))

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    _patch_secrets_h(cfg)
    _patch_pio_ini(cfg)

def _patch_secrets_h(cfg: dict):
    ssid = cfg.get("wifi_ssid", "")
    pwd  = cfg.get("wifi_pass", "")
    lat  = cfg.get("lat", 52.3676)
    lng  = cfg.get("lng", 4.9041)
    loc  = cfg.get("location", "Amsterdam")
    content = (
        "#pragma once\n\n"
        f'#define WIFI_SSID "{ssid}"\n'
        f'#define WIFI_PASS "{pwd}"\n\n'
        f"#define DEFAULT_LAT      {lat:.4f}f\n"
        f"#define DEFAULT_LNG      {lng:.4f}f\n"
        f'#define DEFAULT_LOCATION "{loc}"\n'
    )
    SECRETS_H.write_text(content)

def _patch_pio_ini(cfg: dict):
    if not PIO_INI.exists():
        return
    lines = PIO_INI.read_text().splitlines()
    # Remove existing build_flags and feature defines
    lines = [l for l in lines if not l.strip().startswith("-DFEATURE_")]
    # Remove trailing empty build_flags line
    if lines and lines[-1].strip() == "build_flags =":
        lines = lines[:-1]

    flags = []
    for mod, enabled in cfg.get("modules", {}).items():
        if enabled:
            flags.append(f"    -DFEATURE_{mod.upper()}")

    if flags:
        lines.append("build_flags =")
        lines.extend(flags)

    PIO_INI.write_text("\n".join(lines) + "\n")

# ── HTTP handler ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # silence access log

    def send_json(self, code: int, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/config":
            self.send_json(200, load_config())

        elif path == "/api/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while True:
                    try:
                        msg = _build_queue.get(timeout=25)
                        data = f"data: {json.dumps(msg)}\n\n"
                        self.wfile.write(data.encode())
                        self.wfile.flush()
                        if msg.get("t") == "done":
                            break
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/config":
            cfg = self.read_body()
            save_config(cfg)
            self.send_json(200, {"ok": True})

        elif path == "/api/build":
            _run_pio(["run"])
            self.send_json(200, {"ok": True})

        elif path == "/api/flash":
            _run_pio(["run", "--target", "upload"])
            self.send_json(200, {"ok": True})

        else:
            self.send_json(404, {"error": "not found"})


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


# ── HTML ─────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Deskbuddy Configurator</title>
<style>
:root{
  --bg:#0b1018;--bg2:#111827;--panel:#171b22;--panel2:#1e2433;
  --border:#2d3748;--border2:#3d4f6a;
  --text:#edf2f7;--dim:#94a3b8;
  --accent:#38bdf8;--accent2:#0ea5e9;
  --green:#34d399;--yellow:#fbbf24;--red:#f87171;--purple:#a78bfa;--pink:#f472b6;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif;display:flex;flex-direction:column;min-height:100vh;}

/* ── TOP BAR ── */
.topbar{background:linear-gradient(135deg,#0b1220,#141f30);border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;gap:16px;height:56px;flex-shrink:0;}
.topbar-logo{font-size:18px;font-weight:800;background:linear-gradient(135deg,#dbeafe,var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;}
.topbar-sep{flex:1;}
.topbar-badge{font-size:11px;color:var(--dim);background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:999px;padding:4px 12px;}
.topbar-link{font-size:12px;font-weight:600;color:var(--accent);text-decoration:none;background:rgba(56,189,248,.08);border:1px solid rgba(56,189,248,.25);border-radius:8px;padding:6px 14px;transition:background .15s;}
.topbar-link:hover{background:rgba(56,189,248,.15);}
.nav-tabs{display:flex;gap:4px;}
.nav-tab{background:none;border:none;color:var(--dim);padding:8px 16px;border-radius:8px;cursor:pointer;font:13px/1 system-ui;transition:all .15s;}
.nav-tab:hover{color:var(--text);}
.nav-tab.active{background:rgba(56,189,248,.1);color:var(--accent);font-weight:600;}

/* ── LAYOUT ── */
.body{display:flex;flex:1;overflow:hidden;}
.main{flex:1;overflow-y:auto;padding:28px 28px 200px;}

/* ── SECTION HEADERS ── */
.sec{margin-bottom:36px;}
.sec-head{display:flex;align-items:center;gap:12px;margin-bottom:18px;}
.sec-title{font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);white-space:nowrap;}
.sec-line{flex:1;height:1px;background:var(--border);}

/* ── MODULE GRID ── */
.module-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;}

/* ── MODULE CARD ── */
.mod-card{background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:18px;transition:all .18s;}
.mod-card:hover{border-color:var(--border2);}
.mod-card.builtin{border-color:rgba(52,211,153,.3);background:rgba(52,211,153,.03);}
.mod-card.soon{opacity:.55;}
.mod-top{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:10px;}
.mod-header{display:flex;align-items:center;gap:10px;min-width:0;}
.mod-icon{font-size:22px;flex-shrink:0;line-height:1;}
.mod-title{font-size:14px;font-weight:700;}
.mod-action{display:flex;align-items:center;gap:6px;flex-shrink:0;}
.mod-tags{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;}
.tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:10px;color:var(--dim);background:rgba(255,255,255,.04);border:1px solid var(--border);}
.tag.page{color:#a78bfa;border-color:rgba(167,139,250,.3);}
.tag.widget{color:#38bdf8;border-color:rgba(56,189,248,.3);}
.tag.api{color:#34d399;border-color:rgba(52,211,153,.3);}
.tag.easy{color:#34d399;}
.tag.medium{color:#fbbf24;}
.tag.hard{color:#f87171;}
.mod-desc{font-size:12px;color:var(--dim);line-height:1.5;}
.badge-soon{font-size:10px;font-weight:700;color:var(--dim);background:rgba(255,255,255,.06);border:1px solid var(--border);border-radius:999px;padding:2px 8px;}
.badge-builtin{font-size:10px;font-weight:700;color:var(--green);background:rgba(52,211,153,.1);border:1px solid rgba(52,211,153,.3);border-radius:999px;padding:2px 8px;}
.btn-webui{display:inline-block;font-size:11px;font-weight:600;color:var(--accent);background:rgba(56,189,248,.08);border:1px solid rgba(56,189,248,.2);border-radius:7px;padding:4px 10px;text-decoration:none;white-space:nowrap;transition:background .15s;}
.btn-webui:hover{background:rgba(56,189,248,.18);}

/* ── BASE MODULES ── */
.base-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;}
.base-card{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px;display:flex;align-items:center;gap:10px;}
.base-card-icon{font-size:20px;}
.base-card-title{font-size:13px;font-weight:600;color:var(--dim);}
.base-card-note{font-size:11px;color:var(--border2);margin-top:2px;}
.base-dot{width:8px;height:8px;border-radius:50%;background:var(--green);flex-shrink:0;}

/* ── HA HOW IT WORKS BOX ── */
.info-box{background:var(--panel2);border:1px solid rgba(56,189,248,.2);border-radius:14px;padding:18px 20px;margin-bottom:20px;}
.info-box h3{font-size:13px;font-weight:700;color:var(--accent);margin-bottom:10px;}
.info-box ul{list-style:none;display:flex;flex-direction:column;gap:7px;}
.info-box li{font-size:12px;color:var(--dim);line-height:1.5;padding-left:16px;position:relative;}
.info-box li::before{content:'→';position:absolute;left:0;color:var(--accent);}
.info-box code{background:rgba(255,255,255,.07);border-radius:4px;padding:1px 5px;font-size:11px;color:var(--text);}

/* ── SETTINGS ── */
.settings-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
.field{display:flex;flex-direction:column;gap:6px;}
.field.full{grid-column:1/-1;}
.field label{font-size:12px;font-weight:600;color:var(--dim);letter-spacing:.02em;}
.field input,.field select{background:var(--panel);border:1px solid var(--border);border-radius:10px;color:var(--text);padding:10px 12px;font:14px/1 system-ui;width:100%;transition:border-color .15s;}
.field input:focus,.field select:focus{outline:none;border-color:var(--accent);}
.field input[type=password]{letter-spacing:.05em;}
.field-hint{font-size:11px;color:var(--border2);margin-top:2px;}
.device-link-row{display:flex;align-items:center;gap:10px;margin-top:6px;}
.device-link-row a{font-size:12px;color:var(--accent);text-decoration:none;padding:6px 12px;background:rgba(56,189,248,.08);border:1px solid rgba(56,189,248,.2);border-radius:8px;}
.device-link-row a:hover{background:rgba(56,189,248,.18);}

/* ── BOTTOM BUILD BAR ── */
.build-bar{position:fixed;bottom:0;left:0;right:0;background:rgba(10,15,24,.97);backdrop-filter:blur(16px);border-top:1px solid var(--border2);z-index:200;}
.build-bar-top{display:flex;align-items:center;gap:12px;padding:12px 24px;}
.build-status{font-size:13px;color:var(--dim);flex:1;}
.build-status strong{color:var(--text);}
.build-status.ok strong{color:var(--green);}
.build-status.err strong{color:var(--red);}
.build-status.running strong{color:var(--accent);}
.btn{border:none;border-radius:10px;padding:10px 22px;font:600 13px/1 system-ui;cursor:pointer;transition:all .15s;display:flex;align-items:center;gap:8px;}
.btn-save{background:var(--panel);color:var(--dim);border:1px solid var(--border);}
.btn-save:hover{border-color:var(--text);color:var(--text);}
.btn-build{background:var(--panel2);color:var(--accent);border:1px solid rgba(56,189,248,.3);}
.btn-build:hover{background:rgba(56,189,248,.1);}
.btn-flash{background:var(--accent);color:#001018;}
.btn-flash:hover{background:var(--accent2);}
.btn:disabled{opacity:.4;cursor:not-allowed;}
.terminal-toggle{background:none;border:none;color:var(--dim);cursor:pointer;font-size:12px;padding:4px 8px;border-radius:6px;}
.terminal-toggle:hover{color:var(--text);}

/* ── TERMINAL ── */
.terminal{max-height:0;overflow:hidden;transition:max-height .3s ease;}
.terminal.open{max-height:300px;}
.terminal-inner{height:300px;overflow-y:auto;padding:12px 24px;font:12px/1.6 'Cascadia Code','Fira Code',ui-monospace,monospace;border-top:1px solid var(--border);}
.terminal-inner::-webkit-scrollbar{width:4px;}
.terminal-inner::-webkit-scrollbar-track{background:transparent;}
.terminal-inner::-webkit-scrollbar-thumb{background:var(--border);}
.tl{display:block;}
.tl.err{color:var(--red);}
.tl.ok{color:var(--green);}
.tl.warn{color:var(--yellow);}
.tl.dim{color:var(--border2);}

@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;animation:spin .7s linear infinite;}

@media(max-width:700px){
  .settings-grid{grid-template-columns:1fr;}
  .module-grid,.base-grid{grid-template-columns:1fr;}
  .build-bar-top{flex-wrap:wrap;}
}
</style>
</head>
<body>

<div class="topbar">
  <div class="topbar-logo">🖥 Deskbuddy</div>
  <div class="nav-tabs">
    <button class="nav-tab active" onclick="showTab('modules')">Features</button>
    <button class="nav-tab" onclick="showTab('settings')">Settings</button>
  </div>
  <div class="topbar-sep"></div>
  <a class="topbar-link" id="webuiLink" href="#" target="_blank">Open Device UI ↗</a>
  <div class="topbar-badge" id="topBadge">Loading…</div>
</div>

<div class="body">
<div class="main" id="mainContent">

  <!-- FEATURES TAB -->
  <div id="tab-modules">

    <div class="sec">
      <div class="sec-head"><span class="sec-title">Always included — base firmware</span><span class="sec-line"></span></div>
      <div class="base-grid">
        <div class="base-card"><div class="base-dot"></div><div class="base-card-icon">🕐</div><div class="base-card-info"><div class="base-card-title">Clock & NTP</div><div class="base-card-note">Time, date, sunrise/sunset</div></div></div>
        <div class="base-card"><div class="base-dot"></div><div class="base-card-icon">🌤</div><div class="base-card-info"><div class="base-card-title">Weather</div><div class="base-card-note">Open-Meteo, no API key</div></div></div>
        <div class="base-card"><div class="base-dot"></div><div class="base-card-icon">⏱</div><div class="base-card-info"><div class="base-card-title">Focus timer</div><div class="base-card-note">6 configurable presets</div></div></div>
        <div class="base-card"><div class="base-dot"></div><div class="base-card-icon">📝</div><div class="base-card-info"><div class="base-card-title">Notes page</div><div class="base-card-note">Synced from web UI</div></div></div>
        <div class="base-card"><div class="base-dot"></div><div class="base-card-icon">📶</div><div class="base-card-info"><div class="base-card-title">Status page</div><div class="base-card-note">WiFi, uptime, IP — tap ⓘ</div></div></div>
        <div class="base-card"><div class="base-dot"></div><div class="base-card-icon">🎨</div><div class="base-card-info"><div class="base-card-title">Theme system</div><div class="base-card-note">12 accents, 10 backgrounds</div></div></div>
        <div class="base-card"><div class="base-dot"></div><div class="base-card-icon">🧩</div><div class="base-card-info"><div class="base-card-title">Widget layout</div><div class="base-card-note">Drag & drop in web UI</div></div></div>
      </div>
    </div>

    <div class="sec">
      <div class="sec-head"><span class="sec-title">🏠 Home Assistant</span><span class="sec-line"></span></div>
      <div class="info-box">
        <h3>How HA integration works</h3>
        <ul>
          <li>Enter your HA URL and a <strong>long-lived access token</strong> in the Device UI → Home Assistant panel.</li>
          <li>The ESP32 polls <code>GET /api/states/{entity_id}</code> every 30 s — no cloud, no HACS, pure LAN.</li>
          <li>Up to <strong>4 sensors</strong> shown on the HA tab (temp, humidity, any entity). Value + unit displayed automatically.</li>
          <li>Up to <strong>4 controls</strong> (switch / light / scene / script) — tap on screen to toggle or trigger.</li>
          <li>To get a token: HA → Profile → Long-Lived Access Tokens → Create token.</li>
        </ul>
      </div>
      <div class="module-grid" id="grid-ha"></div>
    </div>

    <div class="sec">
      <div class="sec-head"><span class="sec-title">📌 Notes & Quick API</span><span class="sec-line"></span></div>
      <div class="module-grid" id="grid-notes"></div>
    </div>

    <div class="sec">
      <div class="sec-head"><span class="sec-title">🎯 Productivity</span><span class="sec-line"></span></div>
      <div class="module-grid" id="grid-productivity"></div>
    </div>

    <div class="sec">
      <div class="sec-head"><span class="sec-title">✨ Creative & Wild</span><span class="sec-line"></span></div>
      <div class="module-grid" id="grid-creative"></div>
    </div>

  </div><!-- /tab-modules -->

  <!-- SETTINGS TAB -->
  <div id="tab-settings" style="display:none">
    <div class="sec">
      <div class="sec-head"><span class="sec-title">Device</span><span class="sec-line"></span></div>
      <div class="settings-grid">
        <div class="field full">
          <label>Device IP address</label>
          <input id="s-ip" type="text" placeholder="192.168.x.x" autocomplete="off">
          <div class="field-hint">The IP shown on the device status page. Used to generate the Device UI link above.</div>
          <div class="device-link-row"><a id="settingsDeviceLink" href="#" target="_blank">Open Device UI ↗</a></div>
        </div>
      </div>
    </div>
    <div class="sec">
      <div class="sec-head"><span class="sec-title">WiFi — written to firmware on compile</span><span class="sec-line"></span></div>
      <div class="settings-grid">
        <div class="field"><label>Network (SSID)</label><input id="s-ssid" type="text" autocomplete="off"></div>
        <div class="field"><label>Password</label><input id="s-pass" type="password" autocomplete="off"></div>
      </div>
    </div>
    <div class="sec">
      <div class="sec-head"><span class="sec-title">Location — written to firmware on compile</span><span class="sec-line"></span></div>
      <div class="settings-grid">
        <div class="field full"><label>Location name</label><input id="s-location" type="text" placeholder="e.g. Amsterdam"></div>
        <div class="field"><label>Latitude</label><input id="s-lat" type="number" step="0.0001"></div>
        <div class="field"><label>Longitude</label><input id="s-lng" type="number" step="0.0001"></div>
      </div>
    </div>
    <div class="sec">
      <div class="sec-head"><span class="sec-title">Display defaults — also configurable live in Device UI</span><span class="sec-line"></span></div>
      <div class="settings-grid">
        <div class="field"><label>Buddy nickname</label><input id="s-nickname" type="text" maxlength="24" placeholder="Optional display name"></div>
        <div class="field"><label>Timezone</label><select id="s-timezone">
          <optgroup label="Europe">
            <option value="europe_west">Western Europe (PT/ES)</option>
            <option value="uk">United Kingdom</option>
            <option value="europe_central">Central Europe (NL/DE/FR/BE)</option>
            <option value="europe_east">Eastern Europe (PL/RO/GR)</option>
          </optgroup>
          <optgroup label="Americas">
            <option value="us_eastern">US Eastern</option>
            <option value="us_central">US Central</option>
            <option value="us_pacific">US Pacific</option>
            <option value="brazil_east">Brazil East</option>
          </optgroup>
          <optgroup label="Asia & Pacific">
            <option value="india">India</option>
            <option value="china">China</option>
            <option value="asia_tokyo">Japan</option>
            <option value="australia_sydney">Australia East</option>
          </optgroup>
        </select></div>
        <div class="field"><label>Units</label><select id="s-units">
          <option value="metric">Metric (°C / mm)</option>
          <option value="imperial">Imperial (°F / in)</option>
        </select></div>
        <div class="field"><label>Date format</label><select id="s-region">
          <option value="europe">European — dd.mm.yyyy</option>
          <option value="us">US — mm/dd/yyyy</option>
        </select></div>
      </div>
    </div>
  </div><!-- /tab-settings -->

</div>
</div>

<!-- BUILD BAR -->
<div class="build-bar">
  <div class="build-bar-top">
    <div class="build-status" id="buildStatus"><strong>Ready</strong> — change WiFi/location then compile & flash, or open the Device UI for live settings</div>
    <button class="terminal-toggle" onclick="toggleTerminal()" id="termBtn">▲ Terminal</button>
    <button class="btn btn-save" onclick="saveConfig()">💾 Save config</button>
    <button class="btn btn-build" onclick="triggerBuild('build')" id="btnBuild">⚙ Compile</button>
    <button class="btn btn-flash" onclick="triggerBuild('flash')" id="btnFlash">⚡ Compile & Flash</button>
  </div>
  <div class="terminal" id="terminal">
    <div class="terminal-inner" id="termOutput"></div>
  </div>
</div>

<script>
const MODULES = {
  ha: [
    { id:'ha_sensors', icon:'🌡', title:'HA Sensors & Controls', type:'page', effort:'medium', builtin:true,
      desc:'Dedicated HA tab on the device. Up to 4 sensor entities (temp, humidity, anything) + 4 tap controls (switch/light/scene/script). Polls every 30 s over LAN.',
      webui:'#ha' },
    { id:'ha_webhooks', icon:'🔔', title:'HA Push Webhooks', type:'api', effort:'medium', builtin:false,
      desc:'Register Deskbuddy as a webhook receiver. HA automations push events — washing machine done, doorbell, motion detected.' },
    { id:'ha_now_playing', icon:'🎵', title:'Now Playing Widget', type:'widget', effort:'medium', builtin:false,
      desc:'Show current Spotify/music track + artist via HA media_player entity. Skip/pause with a tap.' },
  ],
  notes: [
    { id:'sticky_notes_api', icon:'📌', title:'Sticky Notes API', type:'api', effort:'easy', builtin:true,
      desc:'POST /api/note sends a note to the display instantly. Up to 3 notes shown. Also readable via GET. Call from curl, scripts, or browser bookmarks.',
      webui:'#quicknote' },
    { id:'get_note_api', icon:'🔗', title:'GET Note (bookmark)', type:'api', effort:'easy', builtin:true,
      desc:'Set a sticky via GET /note?msg=text — save as a browser bookmark for one-click notes from any device on your network.',
      webui:'#quicknote' },
  ],
  productivity: [
    { id:'habit_tracker', icon:'✅', title:'Habit Tracker', type:'page', effort:'medium', builtin:true,
      desc:'Dedicated Habits tab with up to 6 daily habits. Tap to mark done, streaks tracked across days. Configure names + enable/disable in Device UI.',
      webui:'#habits' },
    { id:'hydration_tracker', icon:'💧', title:'Hydration Tracker', type:'widget', effort:'easy', builtin:true,
      desc:'Tap the water drop home widget to log a glass. Shows X/8 progress dots. Resets daily at midnight. Add it via Widget Customization in Device UI.',
      webui:'#widgets' },
    { id:'ambient_color', icon:'🎨', title:'Ambient Color Shift', type:'widget', effort:'medium', builtin:true,
      desc:'Accent color shifts cyan → green as you complete habits. Enable it in the Habit Tracker section of Device UI.',
      webui:'#habits' },
    { id:'context_clock', icon:'🕰', title:'Context Clock', type:'widget', effort:'medium', builtin:false,
      desc:'Clock shows "Focus block · 1h 12m left" based on your work schedule instead of raw time.' },
    { id:'wfh_commute', icon:'🚶', title:'WFH Commute Ritual', type:'widget', effort:'easy', builtin:false,
      desc:'10-min commute ritual timer at day-start. Psychologically separates home mode from work mode.' },
    { id:'eye_break', icon:'👁', title:'Eye Break (20-20-20)', type:'widget', effort:'easy', builtin:false,
      desc:'Every 20 min: look 20 feet away for 20 seconds. Gentle alert, tap to dismiss.' },
    { id:'movement_reminder', icon:'🏃', title:'Movement Reminder', type:'widget', effort:'easy', builtin:false,
      desc:'Stand up / move reminder after configurable sit time (default 50 min). Tap to snooze.' },
  ],
  creative: [
    { id:'lunar_phase', icon:'🌙', title:'Lunar Phase Widget', type:'widget', effort:'easy', builtin:false,
      desc:'Calculates current moon phase locally — no API needed. Pixel-art moon in the correct phase.' },
    { id:'daily_quote', icon:'💬', title:'Daily Quote', type:'widget', effort:'easy', builtin:false,
      desc:'Rotating quote each morning from NVS. Stoic philosophy, productivity wisdom, your own list. Zero network.' },
    { id:'ghost_mode', icon:'🕯', title:'Ghost Mode', type:'widget', effort:'easy', builtin:false,
      desc:'Long-press dim: only tiny clock remains, rest goes almost dark. For deep focus.' },
    { id:'tamagotchi', icon:'🐣', title:'Tamagotchi Desk Pet', type:'widget', effort:'hard', builtin:false,
      desc:'Pixel-art creature fed by completing habits. Sleeps during focus sessions, sad if you miss days.' },
  ],
};

let config = {};
let termOpen = false;
let building = false;

function deviceUrl() {
  const ip = (config.device_ip || '').trim();
  return ip ? 'http://' + ip : '#';
}

function updateDeviceLinks() {
  const url = deviceUrl();
  document.getElementById('webuiLink').href = url;
  document.getElementById('settingsDeviceLink').href = url;
}

function renderModules() {
  for (const [cat, mods] of Object.entries(MODULES)) {
    const grid = document.getElementById('grid-' + cat);
    if (!grid) continue;
    grid.innerHTML = '';
    for (const m of mods) {
      const typeClass = {'page':'page','widget':'widget','api':'api'}[m.type] || '';
      const effortLabel = {'easy':'⚡ Quick win','medium':'🔧 Medium','hard':'🏗 Complex'}[m.effort] || '';

      let actionHtml = '';
      if (m.builtin) {
        const anchor = m.webui || '';
        const href = deviceUrl() + anchor;
        actionHtml = `
          <span class="badge-builtin">Built in</span>
          <a class="btn-webui" href="${href}" target="_blank">Configure ↗</a>`;
      } else {
        actionHtml = `<span class="badge-soon">Coming soon</span>`;
      }

      grid.innerHTML += `
        <div class="mod-card ${m.builtin ? 'builtin' : 'soon'}" id="card-${m.id}">
          <div class="mod-top">
            <div class="mod-header">
              <div class="mod-icon">${m.icon}</div>
              <div class="mod-title">${m.title}</div>
            </div>
            <div class="mod-action">${actionHtml}</div>
          </div>
          <div class="mod-tags">
            <span class="tag ${typeClass}">${m.type}</span>
            <span class="tag">${effortLabel}</span>
          </div>
          <div class="mod-desc">${m.desc}</div>
        </div>`;
    }
  }
}

function loadSettingsUI() {
  document.getElementById('s-ip').value       = config.device_ip  || '';
  document.getElementById('s-ssid').value     = config.wifi_ssid  || '';
  document.getElementById('s-pass').value     = config.wifi_pass  || '';
  document.getElementById('s-location').value = config.location   || '';
  document.getElementById('s-lat').value      = config.lat        || '';
  document.getElementById('s-lng').value      = config.lng        || '';
  document.getElementById('s-nickname').value = config.nickname   || '';
  document.getElementById('s-timezone').value = config.timezone   || 'europe_central';
  document.getElementById('s-units').value    = config.units      || 'metric';
  document.getElementById('s-region').value   = config.region     || 'europe';
  updateDeviceLinks();
}

function collectSettings() {
  config.device_ip  = document.getElementById('s-ip').value.trim();
  config.wifi_ssid  = document.getElementById('s-ssid').value;
  config.wifi_pass  = document.getElementById('s-pass').value;
  config.location   = document.getElementById('s-location').value;
  config.lat        = parseFloat(document.getElementById('s-lat').value) || 52.52;
  config.lng        = parseFloat(document.getElementById('s-lng').value) || 13.405;
  config.nickname   = document.getElementById('s-nickname').value;
  config.timezone   = document.getElementById('s-timezone').value;
  config.units      = document.getElementById('s-units').value;
  config.region     = document.getElementById('s-region').value;
  updateDeviceLinks();
}

document.getElementById('s-ip').addEventListener('input', function() {
  config.device_ip = this.value.trim();
  updateDeviceLinks();
  renderModules();
});

async function saveConfig() {
  collectSettings();
  const r = await fetch('/api/config', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(config) });
  const btn = document.querySelector('.btn-save');
  btn.textContent = r.ok ? '✓ Saved' : '✗ Error';
  setTimeout(() => btn.textContent = '💾 Save config', 1800);
}

function triggerBuild(mode) {
  if (building) return;
  collectSettings();
  fetch('/api/config', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(config) })
    .then(() => {
      termOpen = true;
      document.getElementById('terminal').classList.add('open');
      document.getElementById('termBtn').textContent = '▼ Terminal';
      clearTerminal();
      building = true;
      setBuildUI(true);
      setStatus('running', mode === 'flash' ? 'Compiling & flashing…' : 'Compiling…');
      fetch(mode === 'flash' ? '/api/flash' : '/api/build', { method:'POST' }).then(() => {
        const es = new EventSource('/api/stream');
        es.onmessage = e => {
          const msg = JSON.parse(e.data);
          if (msg.t === 'line') appendLine(msg.v);
          if (msg.t === 'done') {
            es.close(); building = false; setBuildUI(false);
            if (msg.v === 'success') setStatus('ok', mode === 'flash' ? 'Flashed successfully ✓' : 'Compiled successfully ✓');
            else setStatus('err', 'Build failed — check terminal');
          }
        };
        es.onerror = () => { es.close(); building = false; setBuildUI(false); setStatus('err', 'Stream error'); };
      });
    });
}

function setBuildUI(busy) {
  document.getElementById('btnBuild').disabled = busy;
  document.getElementById('btnFlash').disabled = busy;
  document.getElementById('btnBuild').innerHTML = busy ? `<span class="spin">⚙</span> Compiling…` : `⚙ Compile`;
  document.getElementById('btnFlash').innerHTML = busy ? `<span class="spin">⚡</span> Working…` : `⚡ Compile & Flash`;
}

function setStatus(cls, msg) {
  const el = document.getElementById('buildStatus');
  el.className = 'build-status ' + cls;
  el.innerHTML = `<strong>${msg}</strong>`;
}

function appendLine(text) {
  const out = document.getElementById('termOutput');
  const span = document.createElement('span');
  span.className = 'tl';
  const lower = text.toLowerCase();
  if (lower.includes('error') && !lower.includes('no error')) span.classList.add('err');
  else if (lower.includes('warning')) span.classList.add('warn');
  else if (lower.includes('success') || lower.includes('[success]')) span.classList.add('ok');
  else if (/^(Downloading|Unpacking|Compiling|Archiving|Linking|Indexing)/.test(text)) span.classList.add('dim');
  span.textContent = text;
  out.appendChild(span);
  out.scrollTop = out.scrollHeight;
}

function clearTerminal() { document.getElementById('termOutput').innerHTML = ''; }

function toggleTerminal() {
  termOpen = !termOpen;
  document.getElementById('terminal').classList.toggle('open', termOpen);
  document.getElementById('termBtn').textContent = termOpen ? '▼ Terminal' : '▲ Terminal';
}

function showTab(name) {
  ['modules','settings'].forEach(t => {
    document.getElementById('tab-'+t).style.display = t===name ? '' : 'none';
  });
  document.querySelectorAll('.nav-tab').forEach(b => {
    b.classList.toggle('active', b.getAttribute('onclick').includes("'"+name+"'"));
  });
}

function updateBadge() {
  const built = Object.values(MODULES).flat().filter(m => m.builtin).length;
  document.getElementById('topBadge').textContent = `${built} features built in`;
}

fetch('/api/config')
  .then(r => r.json())
  .then(cfg => {
    config = cfg;
    renderModules();
    loadSettingsUI();
    updateBadge();
    setStatus('', 'Ready — open Device UI for live settings, or compile & flash for WiFi/location changes');
  });
</script>
</body>
</html>"""

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = 5000
    server = ThreadedHTTPServer(("", port), Handler)
    print(f"\n  🖥  Deskbuddy Configurator")
    print(f"  ──────────────────────────────")
    print(f"  Open → http://localhost:{port}")
    print(f"  Stop → Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
