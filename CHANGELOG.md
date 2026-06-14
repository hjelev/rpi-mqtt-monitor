# Changelog

## v1.4.0

### ✨ New Features

#### CPU voltage on non-Pi hosts
- `voltage` now reads CPU core voltage from **hwmon (lm-sensors)** when `vcgencmd`
  is not available, so the sensor works on x86 / Ubuntu hosts with a supported
  Super-I/O driver exposing a `Vcore` rail (e.g. via `sensors-detect`).
- When neither `vcgencmd` nor an hwmon Vcore sensor is present (typical on x86
  mini-PCs with no Super-I/O voltage chip), the sensor no longer reports a
  misleading `0 V` — it reports no value (shown as **unavailable** in Home
  Assistant when `use_availability` is enabled).

#### Interactive configurator
- New `rpi-mqtt-monitor --config` (`-c`) launches a **terminal UI for editing `config.py`**.
- Navigate settings with the **↑/↓** arrows; each setting shows its description and default value.
- Press **Enter** to edit — booleans toggle; numbers and strings open an inline editor pre-filled
  with the current value (**Esc** cancels). Press **s** to save, **q** to quit.
- Edits are written back **preserving comments, ordering, formatting, inline comments and the
  existing quote style**; complex settings (lists, the output function) are shown read-only with a
  note to edit them in the file.

#### IP address sensors
- New opt-in sensors expose the device's network addresses: **Local IPv4**, **Local IPv6**,
  **External IPv4**, and **External IPv6**.
- Local addresses are detected locally via a UDP socket (no traffic sent); external
  addresses are resolved through an outbound HTTPS call to `api.ipify.org` / `api6.ipify.org`.
- All four are **disabled by default**; the installer now prompts to enable the local and/or
  external IP sensors.

#### SSD health monitoring
- New per-drive **SSD health** sensors gathered from `smartctl` (`smartmontools`): **SMART overall
  status**, **wear / life used (%)**, **power-on hours**, and **data written (TB)**.
- Works with both **NVMe** and **SATA SSDs** — NVMe values come from the uniform SMART health log;
  SATA wear and data-written are best-effort from the vendor attribute table.
- Installer **autodetects non-rotating drives** and prompts to install `smartmontools` and enable
  the sensors.
- `smartctl` needs root: the installer also adds a passwordless `sudoers` drop-in so the sensors
  populate under **cron** as well as the systemd service.

### ⚙️ New config keys
`local_ipv4`, `local_ipv6`, `external_ipv4`, `external_ipv6`, `ssd_health`

## v1.3.3 (2026-06-13)

### ✨ New Features

#### NVIDIA & AMD GPU monitoring
- GPU monitoring now supports **NVIDIA** and **AMD** alongside Intel.
- **NVIDIA** sensors via the native `pynvml` library (`nvidia-ml-py`): **Utilization %**,
  **Memory %**, **Frequency (MHz)**, **Power (W)**, **Temperature (°C)**.
- **AMD** sensors read straight from **sysfs** (`/sys/class/drm`, in-kernel `amdgpu` driver) —
  no external tools: **Utilization %**, **Memory %**, **Frequency (MHz)**, **Power (W)**,
  **Temperature (°C)**.
- Unlike Intel (`intel_gpu_top`, root-only), NVIDIA and AMD reads **do not require root**, so
  they also populate under cron.
- Installer now **autodetects the GPU vendor** (`lspci` / `nvidia-smi` / `amdgpu`) and prompts
  to enable the matching sensors, installing only what each vendor needs.

### 🛠 Improvements
- **Intel GPU sensor** now works with older `intel-gpu-tools` builds that don't support the
  `-m` flag.

### 🐛 Bug Fixes
- Fixed **on-screen display (`-d`) rendering**: the model name carried a trailing NUL byte on
  Raspberry Pi (pulling the box border left) and a leading space on other platforms (shifting
  the Model/Manufacturer rows one character right). Both values are now cleaned at the source,
  which also tidies the MQTT payloads.

### ⚙️ New config keys
`nvidia_gpu_util`, `nvidia_gpu_mem`, `nvidia_gpu_freq`, `nvidia_gpu_power`, `nvidia_gpu_temp`,
`amd_gpu_util`, `amd_gpu_mem`, `amd_gpu_freq`, `amd_gpu_power`, `amd_gpu_temp`

## v1.3.2 (2026-06-13)

### ✨ New Features
- **Track free space on multiple paths/drives** via the new `used_space_paths` option — each
  entry (`{'name': ..., 'path': ...}`) becomes its own "used space" sensor.

### 🛠 Improvements
- Disk usage is now measured with **`df`**, improving support for multiple mounts.

### ⚙️ New config keys
`used_space_paths`

## v1.3.1 (2026-06-12)

### 🛠 Improvements
- Improved **display / monitor on-off control**.
- Published the **documentation site** under `docs/`.

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
