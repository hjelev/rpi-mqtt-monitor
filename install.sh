#!/bin/bash

# ── Colours ───────────────────────────────────────────────────
R='\e[0m'; BOLD='\e[1m'
CYAN='\e[0;36m';  BCYAN='\e[1;36m'
GREEN='\e[0;32m'; BGREEN='\e[1;32m'
YELLOW='\e[0;33m'; RED='\e[0;31m'

# ── Box geometry ──────────────────────────────────────────────
W=62
LINE_D=$(printf '═%.0s' {1..62})
LINE_S=$(printf '─%.0s' {1..62})

_center() {
    local t="$1" w="$2" len l r
    len=${#t}; l=$(( (w-len)/2 )); r=$(( w-len-l ))
    [ $l -lt 0 ] && l=0; [ $r -lt 0 ] && r=0
    printf "%*s%s%*s" $l "" "$t" $r ""
}

# Box content line — accounts for multibyte chars in %-Ns padding
_bline() {
    local s="$1" blen vlen extra
    blen=${#s}
    vlen=$(printf '%s' "$s" | wc -m)
    extra=$(( blen - vlen ))
    printf "${BCYAN}║${R}  %-$(( 60 + extra ))s${BCYAN}║${R}\n" "$s"
}

# Section header — single-line box
printm() {
    local t="$1" rpad=$(( W - ${#1} - 2 ))
    printf "\n${CYAN}┌${LINE_S}┐${R}\n"
    printf "${CYAN}│${R}  ${BOLD}%s${R}%*s${CYAN}│${R}\n" "$t" $rpad ""
    printf "${CYAN}└${LINE_S}┘${R}\n\n"
}

print_green() { printf "  ${BGREEN}✓${R}  %s\n" "$1"; }
print_yellow() { printf "  ${YELLOW}⚠${R}  %s\n" "$1"; }
print_info()   { printf "  ${BCYAN}▶${R}  %s\n" "$1"; }
print_err()    { printf "  ${RED}✗${R}  %s\n" "$1"; }
ask()          { printf "  ${CYAN}→${R}  %s" "$1"; }

# ── Globals ───────────────────────────────────────────────────
# Set to 1 by features that only work under the systemd service (display control,
# Intel GPU monitoring) so the scheduling step can recommend the service over cron.
service_recommended=0

# ── Prerequisites ─────────────────────────────────────────────
find_python() {
    if python3 --version &>/dev/null; then
        python=$(which python3)
        pip="python3-pip"
        pip_run='pip3'
    else
        python=$(which python)
        pip="python-pip"
        pip_run='pip'
    fi

    if [[ "$python" == *"python"* ]]; then
        print_green "Found: $python"
    else
        print_yellow "Python not found — exiting."
        exit 1
    fi
}

check_and_install_pip() {
    pip_ver=$(${python} -m pip --version 2>&1)
    if [[ "$pip_ver" == *"No"* ]]; then
        print_info "pip not found — installing..."
        sudo apt install -y $pip
    else
        print_green "Found: $pip"
    fi
}

# ── Virtual environment ───────────────────────────────────────
create_venv() {
    printm "Creating virtual environment"

    if ! dpkg -l 2>/dev/null | grep -q python3-venv; then
        print_info "python3-venv not found — installing..."
        sudo apt-get install -y python3-venv
    else
        print_green "Found: python3-venv"
    fi

    ${python} -m venv rpi_mon_env
    print_green "Virtual environment created"

    source rpi_mon_env/bin/activate
    if python3 --version &>/dev/null; then
        python=$(which python3)
    else
        python=$(which python)
    fi
    print_green "Virtual environment activated"
}

install_requirements() {
    printm "Installing requirements"
    $pip_run install -r requirements.txt
    print_green "Requirements installed"
    deactivate
    print_green "Virtual environment deactivated"
}

# ── Configuration ─────────────────────────────────────────────
mqtt_configuration() {
    printm "MQTT Settings"

    ask "MQTT host: "
    read HOST
    sed -i "s/ip address or host/${HOST}/" src/config.py

    ask "MQTT user: "
    read USER
    sed -i "s/username/${USER}/" src/config.py

    ask "MQTT password: "
    read PASS
    sed -i "s/\"password/\"${PASS}/" src/config.py

    ask "Use SSL/TLS for the MQTT connection? [y/N] "
    read SSL
    printf "\n"
    default_port=1883
    tls_on=0
    if [[ "$SSL" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        sed -i "s/mqtt_tls = False/mqtt_tls = True/" src/config.py
        tls_on=1
        default_port=8883
        print_info "TLS enabled — for a self-signed broker cert, set mqtt_tls_ca_certs or mqtt_tls_insecure in src/config.py."
    fi

    ask "Use WebSockets for the MQTT connection? [y/N] "
    read WS
    printf "\n"
    if [[ "$WS" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        sed -i "s/mqtt_websockets = False/mqtt_websockets = True/" src/config.py
        if [ "$tls_on" = "1" ]; then default_port=8084; else default_port=9001; fi
        ask "WebSocket path (default: /mqtt): "
        read WSPATH
        if [ -z "$WSPATH" ]; then WSPATH=/mqtt; fi
        sed -i "s|mqtt_websocket_path = .*|mqtt_websocket_path = '${WSPATH}'|" src/config.py
    fi

    ask "MQTT port (default: ${default_port}): "
    read PORT
    if [ -z "$PORT" ]; then PORT=${default_port}; fi
    sed -i "s/1883/${PORT}/" src/config.py

    ask "MQTT topic prefix (default: rpi-MQTT-monitor): "
    read TOPIC
    if [ -z "$TOPIC" ]; then TOPIC=rpi-MQTT-monitor; fi
    sed -i "s/rpi-MQTT-monitor/${TOPIC}/" src/config.py

    ask "MQTT UNS structure (default: empty): "
    read UNS
    if [[ -n "$UNS" && ! "$UNS" =~ /$ ]]; then UNS="${UNS}/"; fi
    sed -i "s/mqtt_uns_structure = .*/mqtt_uns_structure = '${UNS}'/" src/config.py

    ask "Enable display/monitor control? [y/N] "
    read CONTROL
    printf "\n"
    if [[ "$CONTROL" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        configure_display_control
    fi
    finish_message="MQTT broker"
}

# Enable display control and set up the backend that set_display_power() will use
# at runtime (xset for X11, wlr-randr for wlroots Wayland, vcgencmd for Raspberry
# Pi, ddcutil for GNOME/generic Wayland). Mirrors that function's backend priority.
configure_display_control() {
    sed -i "s/display_control = False/display_control = True/g" src/config.py
    service_recommended=1

    local session="${XDG_SESSION_TYPE:-unknown}"
    print_info "Detected session type: ${session}"

    if [ "$session" = "x11" ] || { [ "$session" != "wayland" ] && [ -n "${DISPLAY:-}" ]; }; then
        ensure_backend_tool "X11/DPMS" xset x11-xserver-utils
    elif command -v wlr-randr >/dev/null 2>&1; then
        print_green "wlr-randr found — wlroots Wayland backend ready"
    elif command -v vcgencmd >/dev/null 2>&1; then
        print_green "vcgencmd found — Raspberry Pi backend ready"
    else
        setup_ddcutil
    fi
}

# If <cmd> is present the backend is ready; otherwise offer to install <pkg>.
ensure_backend_tool() {
    local label="$1" cmd="$2" pkg="$3"
    if command -v "$cmd" >/dev/null 2>&1; then
        print_green "${cmd} found — ${label} backend ready"
        return
    fi
    ask "${cmd} not found. Install ${pkg} for the ${label} backend? [Y/n] "
    read yn
    printf "\n"
    case $yn in
        [Nn]*) print_yellow "Skipped — install ${pkg} manually for display control to work." ;;
        *) sudo apt-get update && sudo apt-get install -y "$pkg" \
               && print_green "${pkg} installed" ;;
    esac
}

# Generic fallback: ddcutil over DDC/CI. Needs the i2c-dev module and i2c group
# membership (mirrors the manual steps in the README).
setup_ddcutil() {
    print_info "No native backend detected — ddcutil (DDC/CI over i2c) is the fallback"
    ask "Install ddcutil and configure i2c access? [Y/n] "
    read yn
    printf "\n"
    case $yn in
        [Nn]*) print_yellow "Skipped — see the README ddcutil section for manual setup."
               return ;;
    esac
    sudo apt-get update && sudo apt-get install -y ddcutil
    echo i2c-dev | sudo tee /etc/modules-load.d/i2c-dev.conf >/dev/null
    sudo modprobe i2c-dev
    sudo usermod -aG i2c "$(whoami)"
    print_green "ddcutil installed and $(whoami) added to the i2c group"
    print_yellow "Log out/in (or reboot) for i2c group membership to take effect."
    print_yellow "Enable DDC/CI in your monitor's OSD menu, then verify with: ddcutil detect"
}

# Optional Intel GPU monitoring: installs intel-gpu-tools and enables the GPU sensors.
# intel_gpu_top needs root, so the sensors only report when running as the service.
configure_intel_gpu() {
    ask "Enable Intel GPU monitoring (installs intel-gpu-tools)? [y/N] "
    read GPU
    printf "\n"
    if [[ "$GPU" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        print_info "Installing Intel GPU tools..."
        sudo apt-get update && sudo apt-get install -y intel-media-va-driver-non-free vainfo intel-gpu-tools
        sed -i "s/intel_gpu_render = False/intel_gpu_render = True/" src/config.py
        sed -i "s/intel_gpu_video = False/intel_gpu_video = True/" src/config.py
        sed -i "s/intel_gpu_freq = False/intel_gpu_freq = True/" src/config.py
        sed -i "s/intel_gpu_power = False/intel_gpu_power = True/" src/config.py
        service_recommended=1
        print_green "Intel GPU monitoring enabled"
        print_yellow "intel_gpu_top needs root — run as the systemd service for GPU sensors to report."
    fi
}

hass_api_configuration() {
    printm "Home Assistant API Settings"

    ask "Home Assistant API URL (default: http://localhost:8123): "
    read HA_URL
    if [ -z "$HA_URL" ]; then HA_URL="http://localhost:8123"; fi
    sed -i "s|your_hass_host|${HA_URL}|" src/config.py

    ask "Home Assistant API token: "
    read HA_TOKEN
    printf "\n"
    sed -i "s|your_hass_token|${HA_TOKEN}|" src/config.py
    hass_api=" --hass_api"
    finish_message="Home Assistant API"
}

update_config() {
    if [ -f src/config.py ]; then
        ask "src/config.py already exists. Replace it? [y/N] "
        read yn
        printf "\n"
        case $yn in
            [Yy]*) ;;
            *) return ;;
        esac
    fi

    print_green "Copying config.py.example to config.py"
    cp src/config.py.example src/config.py

    user=$(whoami)
    sed -i "s/os_user_to_be_replaced/${user}/" src/config.py

    printf "\n"
    printf "  ${BOLD}Select connection type:${R}\n"
    printf "  ${CYAN}[1]${R}  Home Assistant API\n"
    printf "  ${CYAN}[2]${R}  MQTT  ${CYAN}(default)${R}\n\n"
    ask "Your choice [1 or 2]: "
    read choice
    printf "\n"

    case $choice in
        1)  hass_api_configuration ;;
        2|"") mqtt_configuration ;;
        *)  print_yellow "Invalid choice — defaulting to MQTT."
            mqtt_configuration ;;
    esac

    configure_intel_gpu

    print_green "config.py updated with provided settings"

    local_version=$(git describe --tags 2>/dev/null || echo "")
    if [ -n "$local_version" ]; then
        sed -i "s/version = .*/version = '${local_version}'/" src/config.py
    fi
}

# ── Scheduling ────────────────────────────────────────────────
set_cron() {
    printm "Setting up cron job"
    cwd=$(pwd)
    crontab -l 2>/dev/null > tempcron
    if grep -q rpi-cpu2mqtt.py tempcron; then
        cronfound=$(grep rpi-cpu2mqtt.py tempcron)
        print_warn "A cron job for rpi-cpu2mqtt.py already exists — skipping."
        print_warn "To recreate it, remove the entry below and re-run the installer:"
        printf "\n     ${CYAN}%s${R}\n\n" "${cronfound}"
    else
        ask "How often should the script run? (minutes, default: 2): "
        read MIN
        printf "\n"
        if [ -z "$MIN" ]; then MIN=2; fi
        local entry="*/${MIN} * * * * cd ${cwd}; ${python} ${cwd}/src/rpi-cpu2mqtt.py${hass_api}"
        print_info "Adding to crontab: ${entry}"
        echo "$entry" >> tempcron
        crontab tempcron
        print_green "Cron job created (runs every ${MIN} minute(s))"
    fi
    rm -f tempcron
}

set_service() {
    printm "Setting up systemd service"

    if [ -f /etc/systemd/system/rpi-mqtt-monitor.service ]; then
        ask "Service file already exists. Replace it? [y/N] "
        read yn
        printf "\n"
        case $yn in
            [Yy]*) sudo rm /etc/systemd/system/rpi-mqtt-monitor.service ;;
            *) return ;;
        esac
    fi

    ask "How often should the script run? (seconds, default: 120): "
    read MIN
    printf "\n"
    if [ -z "$MIN" ]; then MIN=120; fi
    sed -i "s/service_sleep_time = 120/service_sleep_time = ${MIN}/" src/config.py

    cwd=$(pwd)
    user=$(whoami)
    exec_start="${python} ${cwd}/src/rpi-cpu2mqtt.py --service${hass_api}"
    print_info "Installing service file..."
    sudo cp "${cwd}/rpi-mqtt-monitor.service" /etc/systemd/system/
    sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=${cwd}|" /etc/systemd/system/rpi-mqtt-monitor.service
    sudo sed -i "s|User=YOUR_USER|User=root|" /etc/systemd/system/rpi-mqtt-monitor.service
    sudo sed -i "s|ExecStart=.*|ExecStart=${exec_start}|" /etc/systemd/system/rpi-mqtt-monitor.service
    home_dir=$(eval echo ~"$user")
    sudo sed -i "s|Environment=\"HOME=/home/username\"|Environment=\"HOME=${home_dir}\"|" /etc/systemd/system/rpi-mqtt-monitor.service
    sudo systemctl daemon-reload
    sudo systemctl enable rpi-mqtt-monitor.service
    sudo systemctl start rpi-mqtt-monitor.service
    sudo service rpi-mqtt-monitor restart
    print_green "Service enabled and started (interval: ${MIN}s)"
    git config --global --add safe.directory "${cwd}"
    # The service runs as root (set above); root's git needs the repo marked as a
    # safe directory too, otherwise version checks and the update button fail with
    # a 'dubious ownership' error on the user-owned repo.
    sudo git config --global --add safe.directory "${cwd}"
}

# ── Shortcut ──────────────────────────────────────────────────
create_shortcut() {
    printm "Creating command shortcut"
    cwd=$(pwd)

    if [ ! -d "/usr/local/bin" ]; then
        sudo mkdir -p /usr/local/bin
        print_green "/usr/local/bin created"
    fi

    echo "${python} ${cwd}/src/rpi-cpu2mqtt.py \$@" > rpi-mqtt-monitor
    sudo mv rpi-mqtt-monitor /usr/local/bin/
    sudo chmod +x /usr/local/bin/rpi-mqtt-monitor
    print_green "Shortcut installed: rpi-mqtt-monitor"
}

# ── Main ──────────────────────────────────────────────────────
main() {
    printf "\n${BCYAN}╔${LINE_D}╗${R}\n"
    printf "${BCYAN}║${R}${BOLD}%s${R}${BCYAN}║${R}\n" \
        "$(_center 'Installing rpi-mqtt-monitor' $W)"
    printf "${BCYAN}╚${LINE_D}╝${R}\n\n"

    printm "Checking prerequisites"
    find_python
    check_and_install_pip
    create_venv
    install_requirements
    update_config
    create_shortcut

    printf "\n"
    if [ "$service_recommended" = "1" ]; then
        print_info "Display control needs the systemd service to receive MQTT commands (cron cannot)."
    fi
    printf "  ${BOLD}Select scheduling method:${R}\n"
    printf "  ${CYAN}[c]${R}  Cron job\n"
    if [ "$service_recommended" = "1" ]; then
        printf "  ${CYAN}[s]${R}  Systemd service  ${CYAN}(recommended)${R}\n\n"
    else
        printf "  ${CYAN}[s]${R}  Systemd service\n\n"
    fi
    while true; do
        ask "Your choice [c or s]: "
        read cs
        printf "\n"
        case $cs in
            [Cc]*) set_cron; break ;;
            [Ss]*) set_service; break ;;
            "") if [ "$service_recommended" = "1" ]; then set_service; break;
                else print_yellow "Please enter c for cron or s for service."; fi ;;
            *) print_yellow "Please enter c for cron or s for service." ;;
        esac
    done

    printf "\n${BCYAN}╔${LINE_D}╗${R}\n"
    printf "${BCYAN}║${R}${BOLD}%s${R}${BCYAN}║${R}\n" \
        "$(_center 'Installation Complete' $W)"
    printf "${BCYAN}╠${LINE_D}╣${R}\n"
    _bline "rpi-mqtt-monitor is running and sending data to"
    _bline "your ${finish_message}."
    printf "${BCYAN}║${R}%62s${BCYAN}║${R}\n" ""
    _bline "Run  rpi-mqtt-monitor -h  to see all available options."
    printf "${BCYAN}║${R}%62s${BCYAN}║${R}\n" ""
    printf "${BCYAN}╚${LINE_D}╝${R}\n\n"
}

main
