# Deskbuddy Setup Guide

This guide covers both methods of building and flashing Deskbuddy to your ESP32-2432S028.

---

## What you need

- [ESP32-2432S028 board](https://www.aliexpress.com/item/1005010525144441.html) (the "Cheap Yellow Display" / CYD)
- USB-A to USB-micro data cable (not a charge-only cable)
- Python 3.9+ (for the configurator)
- [PlatformIO](https://platformio.org/) (CLI or VS Code extension)

---

## 1. Clone the repo

```bash
git clone https://github.com/RolfKoenders/Deskbuddy.git
cd Deskbuddy
```

---

## 2. Create your secrets file

Deskbuddy keeps WiFi credentials and your location out of version control.

```bash
cp include/secrets.h.example include/secrets.h
```

Open `include/secrets.h` and fill in your values:

```cpp
#define WIFI_SSID "your_wifi_name"
#define WIFI_PASS "your_wifi_password"

#define DEFAULT_LAT      52.3676f   // your latitude
#define DEFAULT_LNG       4.9041f   // your longitude
#define DEFAULT_LOCATION "Amsterdam"
```

You can find coordinates for your city on [Google Maps](https://maps.google.com): right-click any point and copy the coordinates.

> **Note:** `secrets.h` is listed in `.gitignore` and will never be committed.

---

## 3. Flash: PlatformIO CLI

This is the simplest method if you have PlatformIO installed.

```bash
# Build only
pio run

# Build and flash
pio run --target upload

# Open serial monitor (shows IP address on first boot)
pio device monitor
```

---

## 4. Flash: Configurator {#configurator}

The configurator is a local Python web app that lets you manage WiFi credentials, location, optional feature flags, and trigger builds and flashing, all from your browser.

```bash
python3 configurator.py
```

Then open [http://localhost:8765](http://localhost:8765) in your browser.

From there you can:

- Set WiFi SSID and password (written to `secrets.h`, never committed)
- Set your location (city name, latitude, longitude)
- Enable optional feature modules (Home Assistant, habit tracker, etc.)
- Click **Build** to compile, or **Build & Flash** to compile and upload

The configurator calls `pio run --target upload` under the hood, so PlatformIO must be installed and your board must be connected by USB.

---

## 5. First boot

After a successful flash:

1. The display turns on and shows a splash/sync screen
2. The device connects to WiFi and syncs time via NTP
3. Weather data is fetched from [Open-Meteo](https://open-meteo.com/) (free, no API key needed)
4. The home screen appears

The device's local IP address is shown on the **Status page** (swipe or tap the nav bar). You can also see it in the serial monitor output.

---

## 6. Device web UI

Open `http://<device-ip>` in any browser on the same network. From here you can change:

| Setting | Where |
|---------|-------|
| Background theme | Appearance section |
| Accent and text color | Appearance section |
| Home widget layout | Widget customization |
| Location (name, lat, lng) | Location section |
| Timezone | Location section |
| Units (metric / imperial) | Location section |
| Focus timer presets | Timer section |
| Nickname | General section |
| Sleep / dim behavior | Display section |
| Home Assistant config | HA section |

All settings are saved to the device's non-volatile storage (NVS) and survive reboots. No reflashing is needed.

---

## 7. Optional: Arduino IDE (single-file version)

If you prefer Arduino IDE over PlatformIO, use `desk_buddy_github.cpp`. Rename it to a `.ino` file, install the required libraries, and configure `User_Setup.h` for TFT_eSPI.

Required libraries (via Library Manager):
- `TFT_eSPI`
- `ArduinoJson`
- `XPT2046_Touchscreen`

> Note: The Arduino IDE version is a standalone snapshot. It does not include all features from the main PlatformIO build.

---

## Troubleshooting

### Display is black or white after flashing

This should not happen with the PlatformIO build. `LGFX_config.hpp` is preconfigured for the ESP32-2432S028. If you modified the display config, double-check the panel and bus settings.

### Upload fails

- Make sure the board is connected over USB (not a charge-only cable)
- Try holding the **BOOT** button on the board while the upload starts
- Check that the correct port is selected: `pio device list`

### WiFi does not connect

- Check your SSID and password in `secrets.h`
- Make sure the network is 2.4 GHz (the ESP32 does not support 5 GHz)
- Rebuild and reflash after editing `secrets.h`

### Time or weather is wrong

- The correct timezone is set via the device web UI (not hardcoded)
- Weather uses the latitude/longitude from the web UI, update them if you moved or changed your defaults
- Make sure the device has internet access (not blocked by a firewall or guest network)

### Touch position is offset

- Do not change `ts.setRotation(2)` in the source. This value is calibrated for the ESP32-2432S028 and must stay at 2

### I changed `secrets.h` but the device still uses old values

`secrets.h` is compiled into the firmware. Any change to it requires a rebuild and reflash (`pio run --target upload`). Runtime settings (theme, location, etc.) changed via the web UI are saved immediately to NVS without reflashing.
