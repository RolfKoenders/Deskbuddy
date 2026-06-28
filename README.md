# Deskbuddy

A compact ESP32 desk dashboard with a touchscreen display, live weather, Home Assistant integration, habit tracking, a focus timer, and a browser-based configurator. Built for the ESP32-2432S028 ("Cheap Yellow Display").

<!-- Add a photo of your device here -->
<!-- ![Deskbuddy](docs/device.jpg) -->

---

## Hardware

| Part | Link |
|------|------|
| ESP32-2432S028 (2.8" CYD) | [AliExpress](https://www.aliexpress.com/item/1005010525144441.html) |
| 3D printed case | [MakerWorld](https://makerworld.com/en/models/2725262-deskbuddy-your-personal-dashboard) |

The ESP32-2432S028 is a self-contained board with a 240×320 resistive touch display, sold for around €10–15. No wiring or soldering required.

---

## Features

### Pages

| Page | What it shows |
|------|---------------|
| **Home** | Clock, week number, sunrise/sunset times, and 4 configurable widgets |
| **Weather** | Detailed weather: temperature range, rain, wind, UV index, KP index, sun event |
| **Habits** | Daily habit tracker with 6 habits, streaks, and tap-to-check |
| **Home Assistant** | Live values from up to 4 HA sensor entities |
| **Notes** | Sticky note pushed via REST API from any device on your network |
| **Status** | Device IP, WiFi signal, uptime, and display controls |

### Home widgets

Choose any 4 from:

- **Week number** (current ISO week)
- **Focus timer** (configurable countdown with presets)
- **Outdoor temp** (current temperature + daily range)
- **Rain** (precipitation forecast)
- **Wind** (speed and compass direction)
- **UV index** (Low / Moderate / High / Very High / Extreme)
- **KP index** (geomagnetic activity level)
- **Sun event** (next sunrise or sunset, auto-switching)
- **Hydration** (water intake counter, resets at midnight)
- **Habits** (mini habit completion summary)
- **HA Sensors 1–4** (any Home Assistant sensor value with unit)

### Themes

**Backgrounds:** Slate · Deep · Nordic · Forest · Coffee · Soft · Midnight · Graphite · Garnet · Ochre

**Accents:** Standard · Cyan · Ice · White · Mint · Green · Blue · Purple · Pink · Orange · Amber · Red

All theme changes apply instantly via the browser UI.  No reflashing needed.

### Other

- Auto-dimming and manual dim/off sleep modes
- Touch to wake
- NTP time sync with timezone selection (UTC through UTC+12, with DST for Europe, US, AU and more)
- Metric and imperial units
- European and US date/time format
- Per-device nickname displayed in the title bar
- Sticky Notes REST API (`POST /api/note`) to push notes from automations or scripts
- Home Assistant webhook support

---

## Project structure

```
├── src/
│   └── main.cpp              # Firmware (LovyanGFX, PlatformIO)
├── include/
│   ├── LGFX_config.hpp       # Display + touch driver config
│   ├── secrets.h             # Your WiFi + location (gitignored, create from example)
│   └── secrets.h.example     # Template
├── configurator.py           # Local browser-based build & flash tool
├── platformio.ini            # PlatformIO project
└── desk_buddy_github.cpp     # Standalone single-file version for Arduino IDE
```

---

## Getting started

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for the full walkthrough. Quick version:

```bash
# 1. Clone
git clone https://github.com/RolfKoenders/Deskbuddy.git
cd Deskbuddy

# 2. Create your secrets file
cp include/secrets.h.example include/secrets.h
# Edit secrets.h: add WiFi credentials and your city's coordinates

# 3. Flash
pio run --target upload

# 4. Open the device web UI
# Check serial monitor for the IP address, then open it in your browser
```

Or use the **Python configurator** for a browser-based build & flash UI. See [SETUP_GUIDE.md](SETUP_GUIDE.md#configurator).

---

## Device web UI

Once the device is on your network, open its IP address in any browser. From there you can change:

- Theme (background + accent + text color)
- Widget layout (which 4 widgets appear on the home screen)
- Location name, latitude, longitude
- Timezone and units
- Focus timer presets
- Nickname
- Sleep/dim behavior

No reflash required for any of these settings.

---

## Sticky Notes API

Push a note to the device from anywhere on your network:

```bash
# Set a note
curl -X POST http://<device-ip>/api/note \
  -H "Content-Type: application/json" \
  -d '{"text": "Remember to water the plant"}'

# Clear the note
curl -X POST http://<device-ip>/api/note/clear

# Read the current note
curl http://<device-ip>/api/note
```

Works great with Home Assistant automations or a desktop shortcut.

---

## Home Assistant integration

In the device web UI, configure the HA base URL, bearer token, and up to 4 entity IDs. Deskbuddy polls those entities and shows the current state and unit on dedicated home widgets.

---

## Credits

This project started as a fork of [LextZip/Deskbuddy](https://github.com/LextZip/Deskbuddy) (MIT License) and has since been substantially rewritten: display library migrated from TFT_eSPI to LovyanGFX, new widget system, configurator, Home Assistant integration, habit tracker, hydration tracker, and theming system added.

---

## License

MIT
