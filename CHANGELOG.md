# Changelog

## v1.3.0 (2026-06-12)

A feature-packed release focused on **display control**, **secure/flexible MQTT connectivity**,
**Intel GPU monitoring**, and a substantially improved installer & on-screen display.

### ✨ New Features

#### Display / monitor on-off control
- Turn attached displays **on/off from Home Assistant** via new `Monitor On` / `Monitor Off` buttons.
- Auto-detecting backend that works across environments: **X11** (`xset` DPMS), **wlroots Wayland**
  (`wlr-randr`), **Raspberry Pi** (`vcgencmd`), and **GNOME / generic Wayland** (`ddcutil` over DDC/CI).
- Optional `display_on_command` / `display_off_command` config overrides for custom setups.
- Installer now **detects your display backend and offers to install the required tool and
  permissions** (including `ddcutil` + `i2c-dev` + `i2c` group setup).

#### MQTT over TLS/SSL
- New `mqtt_tls` option to connect to brokers over **SSL (port 8883)**, with `mqtt_tls_ca_certs`
  (self-signed CA) and `mqtt_tls_insecure` options.
- Installer prompts for SSL and auto-suggests port **8883**.

#### MQTT over WebSockets
- New `mqtt_websockets` + `mqtt_websocket_path` options to connect via **MQTT-over-WebSockets**
  (`ws`/`wss`).
- Installer prompts for WebSockets and path, with WebSocket-aware port defaults (**9001** for ws,
  **8084** for wss).

#### Intel GPU monitoring
- Four new sensors from `intel_gpu_top`: **Render/3D busy %**, **Video busy %**, **Frequency (MHz)**,
  and **Power (W)**.
- Installer can install `intel-gpu-tools` and enable the sensors on request.
- *Note:* requires running as the systemd service (root).

### 🛠 Improvements
- **Reworked installer** — new welcome screen, clearer prompts, better error handling, and a smarter
  scheduling step that recommends the **systemd service** when service-only features (display control,
  Intel GPU) are enabled.
- **Improved on-screen display** (`-d`) with refreshed UI, progress bars, and an **update-progress view**.
- Expanded and clarified **README** documentation.

### 🐛 Bug Fixes
- Fixed **restart and shutdown** behavior on Ubuntu.
- **Uninstaller** now removes the symlink in `bin`.
- Various smaller bug fixes across the installer and main script.

### ⚙️ New config keys
`display_control`, `display_on_command`, `display_off_command`, `os_user`, `mqtt_tls`,
`mqtt_tls_ca_certs`, `mqtt_tls_insecure`, `mqtt_websockets`, `mqtt_websocket_path`,
`intel_gpu_render`, `intel_gpu_video`, `intel_gpu_freq`, `intel_gpu_power`

**Full changelog:** `1.2.4..v1.3.0` (16 commits, 2026-03-26 → 2026-06-12)
