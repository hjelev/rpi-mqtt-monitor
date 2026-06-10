#!/bin/bash
# Description: Remote Installation script for rpi-mqtt-monitor

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

print_header() {
    printf "\n${BCYAN}╔${LINE_D}╗${R}\n"
    printf "${BCYAN}║${R}${BOLD}%s${R}${BCYAN}║${R}\n" "$(_center "$1" $W)"
    printf "${BCYAN}╚${LINE_D}╝${R}\n\n"
}

print_section() {
    local t="$1" rpad=$(( W - ${#1} - 2 ))
    printf "\n${CYAN}┌${LINE_S}┐${R}\n"
    printf "${CYAN}│${R}  ${BOLD}%s${R}%*s${CYAN}│${R}\n" "$t" $rpad ""
    printf "${CYAN}└${LINE_S}┘${R}\n\n"
}

print_ok()   { printf "  ${BGREEN}✓${R}  %s\n" "$1"; }
print_info() { printf "  ${BCYAN}▶${R}  %s\n" "$1"; }
print_warn() { printf "  ${YELLOW}⚠${R}  %s\n" "$1"; }
print_err()  { printf "  ${RED}✗${R}  %s\n" "$1"; }
ask()        { printf "  ${CYAN}→${R}  %s" "$1"; }

# ── Welcome ───────────────────────────────────────────────────
welcome() {
    clear
    printf "${BCYAN}╔${LINE_D}╗${R}\n"
    printf "${BCYAN}║${R}%62s${BCYAN}║${R}\n" ""
    printf "${BCYAN}║${R}${BOLD}%s${R}${BCYAN}║${R}\n" \
        "$(_center 'Raspberry Pi MQTT Monitor' $W)"
    printf "${BCYAN}║${R}${CYAN}%s${R}${BCYAN}║${R}\n" \
        "$(_center 'Installer' $W)"
    printf "${BCYAN}║${R}%62s${BCYAN}║${R}\n" ""
    printf "${BCYAN}╠${LINE_D}╣${R}\n"
    printf "${BCYAN}║${R}  %-60s${BCYAN}║${R}\n" "Monitor CPU, temperature, memory, disk and publish to MQTT."
    printf "${BCYAN}║${R}%62s${BCYAN}║${R}\n" ""
    _bline "This installer will:"
    _bline "   •  Clone the repository"
    _bline "   •  Install required dependencies"
    _bline "   •  Configure your connection settings"
    _bline "   •  Set up a cron job or systemd service"
    printf "${BCYAN}║${R}%62s${BCYAN}║${R}\n" ""
    printf "${BCYAN}╚${LINE_D}╝${R}\n\n"

    ask "Ready to proceed? [y/N] "
    read -r response
    printf "\n"
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        :
    else
        print_info "Installation cancelled."
        printf "\n"
        exit
    fi
}

# ── Uninstall ─────────────────────────────────────────────────
uninstall() {
    print_header "Uninstall rpi-mqtt-monitor"

    ask "Are you sure you want to uninstall rpi-mqtt-monitor? [y/N] "
    read -r response
    printf "\n"
    if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        print_info "Uninstallation cancelled."
        printf "\n"
        exit
    fi

    script_dir=$(dirname "$(realpath "$0")")

    if [ -d "$script_dir" ]; then
        if [ "$(realpath rpi-mqtt-monitor)" == "$script_dir" ]; then
            cd ..
        fi
        sudo rm -rf "$script_dir"
        print_ok "Removed rpi-mqtt-monitor directory."
    else
        print_warn "rpi-mqtt-monitor directory not found."
    fi

    if crontab -l 2>/dev/null | grep -q rpi-cpu2mqtt.py; then
        crontab -l | grep -v rpi-cpu2mqtt.py | crontab -
        print_ok "Removed cron job for rpi-cpu2mqtt.py."
    else
        print_warn "No cron job found for rpi-cpu2mqtt.py."
    fi

    if [ -f /etc/systemd/system/rpi-mqtt-monitor.service ]; then
        sudo systemctl stop rpi-mqtt-monitor.service
        sudo systemctl disable rpi-mqtt-monitor.service
        sudo rm /etc/systemd/system/rpi-mqtt-monitor.service
        sudo systemctl daemon-reload
        print_ok "Removed systemd service for rpi-mqtt-monitor."
    else
        print_warn "No systemd service found for rpi-mqtt-monitor."
    fi

    if command -v git &>/dev/null; then
        ask "Do you want to remove git? [y/N] "
        read -r response
        printf "\n"
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            sudo apt-get remove --purge git
            print_ok "Git has been removed."
        fi
    fi

    printf "\n"
    print_ok "Uninstallation complete."
    printf "\n"
}

# ── Main ──────────────────────────────────────────────────────
main() {
    welcome

    if git --version &>/dev/null; then
        git=$(which git)
    else
        print_info "Git not found — installing..."
        sudo apt-get install -y git
    fi

    print_section "Cloning rpi-mqtt-monitor repository"
    git clone https://github.com/hjelev/rpi-mqtt-monitor.git
    cd rpi-mqtt-monitor
    git pull
    bash install.sh
}

if [[ "$1" == "uninstall" ]]; then
    uninstall
else
    main
fi
