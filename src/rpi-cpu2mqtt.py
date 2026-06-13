# -*- coding: utf-8 -*-
# rpi-mqtt-monitor is a python script to monitor cpu load, temperature, frequency, free space etc.
# on a Raspberry Pi or Ubuntu computer and publish the data to a MQTT server or Home Assistant API.

from __future__ import division
import subprocess
import time
from datetime import datetime
import socket
import paho.mqtt.client as paho
import json
import math
import os
import sys
import shutil
import argparse
import threading
import update
import config
import re
import html
import uuid
import glob
import requests
import configparser
import psutil
#import external sensor lib only if one uses external sensors
if config.ext_sensors:
    # append folder ext_sensor_lib
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ext_sensor_lib')))
    import ds18b20
    from sht21 import SHT21


configlanguage = configparser.ConfigParser()
configlanguage.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'translations.ini'))

def get_translation(key):
    """ get the correct translation"""
    return configlanguage.get(config.language, key, fallback=key)


def check_wifi_signal(format):
    try:
        full_cmd =  "ls /sys/class/ieee80211/*/device/net/"
        interface = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0].strip().decode("utf-8")
        full_cmd = "/sbin/iwconfig {} | grep -i quality".format(interface)
        wifi_signal = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]

        if format == 'dbm':
            wifi_signal = wifi_signal.decode("utf-8").strip().split(' ')[4].split('=')[1]
        else:
            wifi_signal = wifi_signal.decode("utf-8").strip().split(' ')[1].split('=')[1].split('/')[0]
            wifi_signal = round((int(wifi_signal) / 70)* 100)

    except Exception:
        wifi_signal = None if config.use_availability else 0

    return wifi_signal


def _slugify(text):
    """Lowercase, keep [a-z0-9_], collapse the rest to single underscores. Used to
    turn a user-supplied disk name into a topic-safe sensor key."""
    s = re.sub(r'[^a-z0-9]+', '_', str(text).strip().lower()).strip('_')
    return s or 'disk'


def check_used_space(path):
    try:
        st = os.statvfs(path)
        total = st.f_blocks * st.f_frsize          # total size
        free = st.f_bfree * st.f_frsize            # truly free blocks
        avail = st.f_bavail * st.f_frsize          # available to unprivileged users
        used = total - free
        denominator = used + avail
        if denominator == 0:
            return None if config.use_availability else 0
        # Match df's Use%: used / (used + avail), excluding root-reserved blocks, rounded up
        return math.ceil(used / denominator * 100)
    except Exception:
        return None if config.use_availability else 0


def check_cpu_load():
    return psutil.cpu_percent(interval=1)


def check_voltage():
    try:
        full_cmd = "vcgencmd measure_volts | cut -f2 -d= | sed 's/000//'"
        voltage = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0]
        return voltage.strip()[:-1].decode('utf8')
    except Exception:
        return None if config.use_availability else 0


def check_swap():
    try:
        full_cmd = "free | grep -i swap | awk 'NR == 1 {if($2 > 0) {print $3/$2*100} else {print 0}}'"
        swap = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]
        return round(float(swap.decode("utf-8").replace(",", ".")), 1)
    except Exception:
        return None if config.use_availability else 0


def check_memory():
    full_cmd = 'free -b | awk \'NR==2 {printf "%.2f\\n", $3/$2 * 100}\''
    memory = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]

    if memory:
        memory = round(float(memory.decode("utf-8").replace(",", ".")))
    else:
        memory = 0

    return memory


def check_rpi_power_status():
    try:
        full_cmd = "vcgencmd get_throttled | cut -d= -f2"
        throttled = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]
        throttled = throttled.decode('utf-8').strip()
        throttled_val = int(throttled, 16)

        if throttled_val & 1<<0:
            return "Under-voltage"
        if throttled_val & 1<<3:
            return "Soft temperature limit"
        if throttled_val & 1<<1:
            return "ARM frequency capped"
        if throttled_val & 1<<2:
            return "Throttled"

        # These are "previous" statuses here for completeness
        # Home Assistant has the history so do not report them
        #
        #if throttled_val & 1<<16:
        #    return "Previous under-voltage"
        #if throttled_val & 1<<17:
        #    return "Previous ARM frequency cap"
        #if throttled_val & 1<<18:
        #    return "Previous throttling"
        #if throttled_val & 1<<19:
        #    return "Previous soft temperature limit"

        return "OK"

    except Exception as e:
        return "Error: " + str(e)


def check_service_file_exists():
    service_file_path = "/etc/systemd/system/rpi-mqtt-monitor.service"
    return os.path.exists(service_file_path)


def check_crontab_entry(script_name="rpi-cpu2mqtt.py"):
    try:
        # Get the current user's crontab
        result = subprocess.run(['crontab', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # If the crontab command fails, it means there is no crontab for the user
        if result.returncode != 0:
            return False
        
        # Check if the script name is in the crontab output
        return script_name in result.stdout
    except Exception as e:
        print(f"Error checking crontab: {e}")
        return False
    

def read_ext_sensors():
    """
    here we read the external sensors
    we create a list with the external sensors where we append the values

    """
    # we copy the variable from the config file and replace the values by the real sensor values
    ext_sensors = config.ext_sensors
    # item[0] = name
    # item[1] = sensor_type
    # item[2] = ID
    # item[3] = value
    # now we iterate over the external sensors
    for item in config.ext_sensors:
        # if it is a DS18B20 sensor 
        if item[1] == "ds18b20":
            # if sensor ID in unknown, then we try to get it
            # this only works for a single DS18B20 sensor
            if item[2]==0:
                available = ds18b20.get_available_sensors()
                if not available:
                    print("Error: no DS18B20 sensors found on 1-wire bus")
                    if config.use_availability:
                        item[3] = None
                    continue
                item[2] = available[0]
            temp = ds18b20.sensor_DS18B20(sensor_id=item[2])
            item[3] = temp
            # in case that some error occurs during reading, we get -300
            if temp==-300:
                print ("Error while reading sensor %s, %s" % (item[1], item[2]))
                if config.use_availability:
                    item[3] = None
        if item[1] == "sht21":
            try:
                with SHT21(1) as sht21:
                    temp = sht21.read_temperature()
                    temp = '%2.1f' % temp
                    hum = sht21.read_humidity()
                    hum = '%2.1f' % hum
                    item[3] = [temp, hum]
            # in case we have any problems to read the sensor, we continue and keep default values
            except Exception:
                print ("Error while reading sensor %s" % item[1])
                if config.use_availability:
                    item[3] = [None, None]
    #print (ext_sensors)
    return ext_sensors


def check_cpu_temp():
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            raise ValueError("No temperature sensors found.")

        if config.cpu_thermal_zone in temps:
            cpu_temp = temps[config.cpu_thermal_zone][0].current
        elif "cpu_thermal" in temps:
            cpu_temp = temps["cpu_thermal"][0].current
        elif "coretemp" in temps:
            cpu_temp = temps["coretemp"][0].current
        else:
            raise ValueError("CPU temperature sensor not found.")

        return round(cpu_temp, 2) 
    except Exception as e:
        print(f"Error reading CPU temperature: {e}")
        return None if config.use_availability else 0


def check_sys_clock_speed():
    try:
        full_cmd = "awk '{printf (\"%0.0f\",$1/1000); }' </sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
        byte_data = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]
        return int(byte_data.decode("utf-8").strip())
    except Exception:
        return None if config.use_availability else 0


def check_uptime(format):
    try:
        if format == 'timestamp':
            full_cmd = "uptime -s"
            tz_cmd = "date +%z"
            tz_str = subprocess.Popen(tz_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0].decode('utf-8').strip()
            timestamp_str = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0].decode('utf-8').strip()
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            iso_timestamp = timestamp.isoformat() + tz_str  # Append correct offset to indicate `local` time
            return iso_timestamp
        else:
            full_cmd = "awk '{print int($1"+format+")}' /proc/uptime"
        return int(subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0])
    except Exception:
        return None if config.use_availability else 0


def check_model_name():
   full_cmd = "cat /sys/firmware/devicetree/base/model"
   model_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
   if model_name == '':
        full_cmd = "cat /proc/cpuinfo  | grep 'name'| uniq"
        model_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
        try:
            model_name = model_name.split(':')[1].replace('\n', '')
        except Exception:
            model_name = None if config.use_availability else 'Unknown'

   return model_name


def check_rpi5_fan_speed():
    try:
        full_cmd = "cat /sys/devices/platform/cooling_fan/hwmon/*/fan1_input"
        rpi5_fan_speed = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8").strip()
        if not rpi5_fan_speed:
            return None if config.use_availability else 0
        return rpi5_fan_speed
    except Exception:
        return None if config.use_availability else 0


def get_os():
    full_cmd = 'cat /etc/os-release | grep -i pretty_name'
    pretty_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
    try:
        pretty_name = pretty_name.split('=')[1].replace('"', '').replace('\n', '')
    except Exception:
        pretty_name = None if config.use_availability else 'Unknown'
        
    return(pretty_name)


def get_manufacturer():
    try:
        model = check_model_name()
        if model and 'Raspberry' not in model:
            full_cmd = "cat /proc/cpuinfo  | grep 'vendor'| uniq"
            pretty_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
            pretty_name = pretty_name.split(':')[1].replace('\n', '')
        else:
            pretty_name = 'Raspberry Pi'
    except Exception:
        pretty_name = None if config.use_availability else 'Unknown'

    return(pretty_name)


def check_git_update(script_dir):
    remote_version = update.check_git_version_remote(script_dir)
    if config.version == remote_version:
        git_update = {
                    "installed_ver": config.version,
                    "new_ver": config.version,
                    }
    else:
        git_update = {
                    "installed_ver": config.version,
                    "new_ver": remote_version,
                    }

    return(json.dumps(git_update))


def check_git_version(script_dir):
    full_cmd = "/usr/bin/git -C {} describe --tags `/usr/bin/git -C {} rev-list --tags --max-count=1`".format(script_dir, script_dir)
    git_version = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8").replace('\n', '')

    return(git_version)


def get_network_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = None if config.use_availability else '127.0.0.1'
    finally:
        s.close()
    return IP


def get_mac_address():
    mac_num = uuid.getnode()
    mac = '-'.join((('%012X' % mac_num)[i:i+2] for i in range(0, 12, 2)))
    return mac


def get_apt_updates():
    try:
        subprocess.run(['sudo', 'apt', 'update'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        full_cmd = "apt-get -q -y --ignore-hold --allow-change-held-packages --allow-unauthenticated -s dist-upgrade | /bin/grep ^Inst | wc -l"
        result = subprocess.run(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        updates_count = int(result.stdout.strip())
    except Exception as e:
        print(f"Error checking for updates: {e}")
        updates_count = None if config.use_availability else 0

    return updates_count


def get_hwmon_device_name(hwmon_path):
    try:
        with open(os.path.join(hwmon_path, 'name'), 'r') as f:
            return f.read().strip()
    except Exception as e:
        print(f"Error reading name for {hwmon_path}: {e}")
        return None


def get_hwmon_temp(hwmon_path):
    try:
        temp_files = glob.glob(os.path.join(hwmon_path, 'temp*_input'))
        for temp_file in temp_files:
            with open(temp_file, 'r') as tf:
                temp = int(tf.read().strip()) / 1000.0
                return temp
    except Exception as e:
        print(f"Error reading temperature for {hwmon_path}: {e}")
        return None


def check_all_drive_temps():
    drive_temps = {}
    hwmon_devices = glob.glob('/sys/class/hwmon/hwmon*')
    for hwmon in hwmon_devices:
        device_name = get_hwmon_device_name(hwmon)
        if device_name and any(keyword in device_name.lower() for keyword in ['nvme', 'sd']):
            temp = get_hwmon_temp(hwmon)
            if temp is not None:
                drive_temps[device_name] = temp
    return drive_temps


def print_measured_values(monitored_values):
    import re as _re

    R      = '\033[0m'
    BOLD   = '\033[1m'
    DIM    = '\033[2m'
    CYAN   = '\033[0;36m'
    BCYAN  = '\033[1;36m'
    WHITE  = '\033[1;37m'
    BGREEN = '\033[1;32m'
    YELLOW = '\033[0;33m'
    RED    = '\033[0;31m'
    GRAY   = '\033[0;37m'

    W  = 60
    LD = '═' * W
    LS = '─' * W

    def _vlen(s):
        return len(_re.sub(r'\033\[[0-9;]*m', '', s))

    def _rpad(s):
        return s + ' ' * max(0, W - _vlen(s))

    def _center(colored_s, visible_s):
        l = (W - len(visible_s)) // 2
        r = W - len(visible_s) - l
        return ' ' * l + colored_s + ' ' * r

    def _row(label, value):
        inner = f"  {GRAY}{label:<16}{R}{value}"
        return f"{BCYAN}║{R}{_rpad(inner)}{BCYAN}║{R}"

    def _section(title):
        inner = f"  {BOLD}{CYAN}{title}{R}"
        return (f"{BCYAN}╠{LD}╣{R}\n"
                f"{BCYAN}║{R}{_rpad(inner)}{BCYAN}║{R}\n"
                f"{BCYAN}╠{LS}╣{R}")

    def _bar(value, width=12, warn=70, crit=90):
        try:
            pct = min(float(value) / 100.0, 1.0)
        except (TypeError, ValueError):
            return ''
        filled = round(pct * width)
        c = BGREEN if pct * 100 < warn else (YELLOW if pct * 100 < crit else RED)
        return f"{c}{'█' * filled}{DIM}{'░' * (width - filled)}{R}"

    def _cpct(value, unit='%', warn=70, crit=90):
        try:
            v = float(value)
            c = RED if v >= crit else (YELLOW if v >= warn else BGREEN)
            return f"{BOLD}{c}{value}{unit}{R}"
        except (TypeError, ValueError):
            return f"{value}{unit}"

    def _ctemp(value, warn=65, crit=80):
        try:
            v = float(value)
            c = RED if v >= crit else (YELLOW if v >= warn else BGREEN)
            return f"{BOLD}{c}{value}°C{R}"
        except (TypeError, ValueError):
            return f"{value}°C"

    remote_version = update.check_git_version_remote(script_dir)
    lines = [f"\n{BCYAN}╔{LD}╗{R}"]

    title_v = f"rpi-mqtt-monitor  v{config.version}"
    title_c = f"{BOLD}{WHITE}rpi-mqtt-monitor{R}  {CYAN}v{config.version}{R}"
    lines.append(f"{BCYAN}║{R}{_center(title_c, title_v)}{BCYAN}║{R}")

    # Device section
    lines.append(_section("DEVICE"))
    lines.append(_row("Model",       f"{WHITE}{check_model_name()}{R}"))
    lines.append(_row("Manufacturer",f"{WHITE}{get_manufacturer()}{R}"))
    lines.append(_row("OS",          f"{WHITE}{get_os()}{R}"))
    lines.append(_row("Hostname",    f"{CYAN}{hostname}{R}"))
    lines.append(_row("IP Address",  f"{CYAN}{get_network_ip()}{R}"))
    lines.append(_row("MAC Address", f"{GRAY}{get_mac_address()}{R}"))
    lines.append(_row("Sleep",       f"{WHITE}{config.service_sleep_time}s{R}"))
    if config.update:
        lines.append(_row("Update Check", f"{WHITE}{config.update_check_interval}s{R}"))

    # Measurements section
    lines.append(_section("MEASUREMENTS"))

    bar_metrics = [
        ("cpu_load",    "CPU Load",    "%",   70, 90),
        ("memory",      "Memory",      "%",   70, 90),
        ("used_space",  "Disk",        "%",   70, 90),
        ("swap",        "Swap",        "%",   50, 80),
        ("wifi_signal", "WiFi Signal", "%",   None, None),
    ]
    for key, label, unit, warn, crit in bar_metrics:
        if key in monitored_values:
            v = monitored_values[key]
            w, c = (warn or 70), (crit or 90)
            lines.append(_row(label, f"{_bar(v, warn=w, crit=c)}  {_cpct(v, unit, w, c)}"))

    if "cpu_temp" in monitored_values:
        lines.append(_row("CPU Temp", _ctemp(monitored_values["cpu_temp"])))

    plain_metrics = [
        ("sys_clock_speed", "Clock Speed", "MHz"),
        ("voltage",         "Voltage",     "V"),
        ("wifi_signal_dbm", "WiFi",        "dBm"),
        ("rpi5_fan_speed",  "Fan Speed",   "RPM"),
        ("data_sent",       "Data Sent",   "MB"),
        ("data_received",   "Data Recv",   "MB"),
        ("intel_gpu_render", "GPU Render", "%"),
        ("intel_gpu_video",  "GPU Video",  "%"),
        ("intel_gpu_freq",   "GPU Freq",   "MHz"),
        ("intel_gpu_power",  "GPU Power",  "W"),
    ]
    for key, label, unit in plain_metrics:
        if key in monitored_values:
            lines.append(_row(label, f"{WHITE}{monitored_values[key]} {unit}{R}"))

    if "uptime" in monitored_values:
        lines.append(_row("Uptime", f"{WHITE}{monitored_values['uptime']}{R}"))

    if "rpi_power_status" in monitored_values:
        lines.append(_row("Power Status", f"{WHITE}{monitored_values['rpi_power_status']}{R}"))

    if "update" in monitored_values:
        v = monitored_values["update"]
        c, label = (YELLOW, f"available  {GRAY}({v}){R}") if v else (BGREEN, "up to date")
        lines.append(_row("Update", f"{BOLD}{c}{label}{R}"))

    if "used_space_paths" in monitored_values:
        for name, used in (monitored_values["used_space_paths"] or {}).items():
            lines.append(_row(f"{name.replace('_',' ').title()} Disk",
                              f"{_bar(used, warn=70, crit=90)}  {_cpct(used, '%', 70, 90)}"))

    if "drive_temps" in monitored_values:
        for device, temp in (monitored_values["drive_temps"] or {}).items():
            lines.append(_row(f"{device.capitalize()} Temp", _ctemp(f"{temp:.1f}")))

    if "ext_sensors" in monitored_values:
        for item in (monitored_values["ext_sensors"] or []):
            if item[3] is not None:
                lines.append(_row(item[0], f"{WHITE}{item[3]}°C{R}"))

    # Scheduling section
    lines.append(_section("SCHEDULING"))
    scheduled = False
    if check_service_file_exists():
        lines.append(f"{BCYAN}║{R}{_rpad(f'  {BGREEN}●{R}  systemd service')}{BCYAN}║{R}")
        scheduled = True
    if check_crontab_entry():
        lines.append(f"{BCYAN}║{R}{_rpad(f'  {BGREEN}●{R}  cron job')}{BCYAN}║{R}")
        scheduled = True
    if not scheduled:
        lines.append(f"{BCYAN}║{R}{_rpad(f'  {YELLOW}○{R}  not scheduled')}{BCYAN}║{R}")

    # Release notes
    import textwrap as _tw
    rn = get_release_notes(remote_version).strip()
    if rn:
        lines.append(_section(f"RELEASE NOTES  {GRAY}v{remote_version}{R}"))
        for rline in rn.splitlines():
            for wline in (_tw.wrap(rline, W - 2) or ['']):
                lines.append(f"{BCYAN}║{R}{_rpad('  ' + wline)}{BCYAN}║{R}")

    lines.append(f"{BCYAN}╚{LD}╝{R}\n")
    print('\n'.join(lines))
    

def extract_text(html_string):
    html_string = html.unescape(html_string)
    text = re.sub('<[^<]+?>', '', html_string)

    return text


def get_release_notes(version):
    url = "https://github.com/hjelev/rpi-mqtt-monitor/releases/tag/" + version

    try:
        response = subprocess.run(['curl', '-s', url], capture_output=True)
        release_notes = response.stdout.decode('utf-8').split("What's Changed")[1].split("</div>")[0].replace("</h2>","").split("<p>")[0]
    except Exception:
        release_notes = "No release notes available"

    lines = extract_text(release_notes).split('\n')
    lines = ["   * "+ line for line in lines if line.strip() != ""]

    release_notes = '\n'.join(lines)

    if len(release_notes) > 255:
        release_notes = release_notes[:250] + " ..."

    return release_notes


def build_device_info():
    return {
        "identifiers": [hostname],
        "manufacturer": 'github.com/hjelev',
        "model": f'RPi MQTT Monitor {config.version}',
        "name": hostname,
        "sw_version": get_os(),
        "hw_version": f"{check_model_name()} by {get_manufacturer()} IP:{get_network_ip()}",
        "configuration_url": "https://github.com/hjelev/rpi-mqtt-monitor",
        "connections": [["mac", get_mac_address()]]
    }

def build_data_template(what_config):
    return {
        "state_topic": f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/{what_config}",
        "unique_id": f"{hostname}_{what_config}",
        "device": build_device_info()
    }

def add_common_attributes(data, icon, name, unit=None, device_class=None, state_class=None):
    data.update({
        "icon": icon,
        "name": name,
    })
    if unit:
        data["unit_of_measurement"] = unit
    if device_class:
        data["device_class"] = device_class
    if state_class:
        data["state_class"] = state_class

def handle_specific_configurations(data, what_config, device):
    if what_config == "cpu_load":
        add_common_attributes(data, "mdi:speedometer", get_translation("cpu_load"), "%", None, "measurement")
    elif what_config == "cpu_temp":
        add_common_attributes(data, "hass:thermometer", get_translation("cpu_temperature"), "°C", "temperature", "measurement")
    elif what_config == "used_space":
        add_common_attributes(data, "mdi:harddisk", get_translation("disk_usage"), "%", None, "measurement")
    elif what_config.startswith("used_space_"):
        add_common_attributes(data, "mdi:harddisk",
                              device.replace('_', ' ').title() + " " + get_translation("disk_usage"),
                              "%", None, "measurement")
    elif what_config == "voltage":
        add_common_attributes(data, "mdi:flash", get_translation("cpu_voltage"), "V", "voltage", "measurement")
    elif what_config == "swap":
        add_common_attributes(data, "mdi:harddisk", get_translation("disk_swap"), "%", None, "measurement")
    elif what_config == "memory":
        add_common_attributes(data, "mdi:memory", get_translation("memory_usage"), "%", None, "measurement")
    elif what_config == "sys_clock_speed":
        add_common_attributes(data, "mdi:speedometer", get_translation("cpu_clock_speed"), "MHz", "frequency", "measurement")
    elif what_config == "uptime":
        add_common_attributes(data, "mdi:calendar", get_translation("uptime"))
        data["value_template"] = "{{ as_datetime(value) }}"
        data["device_class"] = "timestamp"
    elif what_config == "uptime_seconds":
        add_common_attributes(data, "mdi:timer-outline", get_translation("uptime"), "s", "duration", "total_increasing")
    elif what_config == "wifi_signal":
        add_common_attributes(data, "mdi:wifi", get_translation("wifi_signal"), "%", None, "measurement")
    elif what_config == "wifi_signal_dbm":
        add_common_attributes(data, "mdi:wifi", get_translation("wifi_signal_strength"), "dBm", "signal_strength", "measurement")
    elif what_config == "rpi5_fan_speed":
        add_common_attributes(data, "mdi:fan", get_translation("fan_speed"), "RPM", None, "measurement")
    elif what_config == "status":
        add_common_attributes(data, "mdi:lan-connect", get_translation("status"))
        data["value_template"] = "{{ 'online' if value == '1' else 'offline' }}"
    elif what_config == "git_update":
        add_common_attributes(data, "mdi:git", get_translation("rpi_mqtt_monitor"), None, "update", "measurement")
        data["title"] = "Device Update"
        data["value_template"] = "{{ 'ON' if value_json.installed_ver != value_json.new_ver else 'OFF' }}"
    elif what_config == "update":
        version = update.check_git_version_remote(script_dir)
        add_common_attributes(data, "mdi:update", get_translation("rpi_mqtt_monitor"), None, "firmware")
        data["title"] = "New Version"
        data["state_topic"] = config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + "git_update"
        data["value_template"] = (
            "{{ {'installed_version': value_json.installed_ver, "
            "'latest_version': value_json.new_ver, "
            "'in_progress': value_json.in_progress | default(false), "
            "'update_percentage': value_json.update_percentage | default(none)} | to_json }}"
        )
        data["command_topic"] = config.mqtt_discovery_prefix + "/update/" + hostname + "/command"
        data["payload_install"] = "install"
        data['release_url'] = "https://github.com/hjelev/rpi-mqtt-monitor/releases/tag/" + version
        data['entity_picture'] = "https://raw.githubusercontent.com/hjelev/rpi-mqtt-monitor/refs/heads/master/images/update_icon.png"
        data['release_summary'] = get_release_notes(version)
    elif what_config == "restart_button":
        add_common_attributes(data, "mdi:restart", get_translation("system_restart"))
        data["command_topic"] = config.mqtt_discovery_prefix + "/update/" + hostname + "/command"
        data["payload_press"] = "restart"
        data["device_class"] = "restart"
    elif what_config == "shutdown_button":
        add_common_attributes(data, "mdi:power", get_translation("system_shutdown"))
        data["command_topic"] = config.mqtt_discovery_prefix + "/update/" + hostname + "/command"
        data["payload_press"] = "shutdown"
    elif what_config == "display_on":
        add_common_attributes(data, "mdi:monitor", get_translation("monitor_on"))
        data["command_topic"] = config.mqtt_discovery_prefix + "/update/" + hostname + "/command"
        data["payload_press"] = "display_on"
    elif what_config == "display_off":
        add_common_attributes(data, "mdi:monitor", get_translation("monitor_off"))
        data["command_topic"] = config.mqtt_discovery_prefix + "/update/" + hostname + "/command"
        data["payload_press"] = "display_off"
    elif what_config == device + "_temp":
        add_common_attributes(data, "hass:thermometer", device + " " + get_translation("temperature"), "°C", "temperature", "measurement")
    elif what_config == "rpi_power_status":
        add_common_attributes(data, "mdi:flash", get_translation("rpi_power_status"))
    elif what_config == "apt_updates":
        add_common_attributes(data, "mdi:update", get_translation("apt_updates"))
    elif what_config == "ds18b20_status":
        add_common_attributes(data, "hass:thermometer", device + " " + get_translation("temperature"), "°C", "temperature", "measurement")
        data["state_topic"] = config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + what_config + "_" + device
        data["unique_id"] = hostname + "_" + what_config + "_" + device
    elif what_config == "sht21_temp_status":
        add_common_attributes(data, "hass:thermometer", device + " " + get_translation("temperature"), "°C", "temperature", "measurement")
        data["state_topic"] = config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + what_config + "_" + device
        data["unique_id"] = hostname + "_" + what_config + "_" + device
    elif what_config == "sht21_hum_status":
        add_common_attributes(data, "mdi:water-percent", device + " " + get_translation("humidity"), "%", "humidity", "measurement")
        data["state_topic"] = config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + what_config + "_" + device
        data["unique_id"] = hostname + "_" + what_config + "_" + device
    elif what_config == "data_sent":
        add_common_attributes(data, "mdi:upload", get_translation("data_sent"), "MB", None, "measurement")
    elif what_config == "data_received":
        add_common_attributes(data, "mdi:download", get_translation("data_received"), "MB", None, "measurement")
    elif what_config == "intel_gpu_render":
        add_common_attributes(data, "mdi:expansion-card", "Intel GPU Render", "%", None, "measurement")
    elif what_config == "intel_gpu_video":
        add_common_attributes(data, "mdi:video", "Intel GPU Video", "%", None, "measurement")
    elif what_config == "intel_gpu_freq":
        add_common_attributes(data, "mdi:speedometer", "Intel GPU Frequency", "MHz", "frequency", "measurement")
    elif what_config == "intel_gpu_power":
        add_common_attributes(data, "mdi:flash", "Intel GPU Power", "W", "power", "measurement")

def config_json(what_config, device="0", hass_api=False):
    data = build_data_template(what_config)
    handle_specific_configurations(data, what_config, device)

    if "state_class" in data and data["state_class"] == "measurement" and what_config != "git_update":
        if config.expire_after_time:
            data["expire_after"] = config.expire_after_time
        if config.use_availability:
            data["availability_topic"] = f"{data['state_topic']}_availability"

    if hass_api:
        result = {key: data[key] for key in ["name", "icon", "state_class", "unit_of_measurement", "device_class", "unique_id", "value_template"] if key in data}
        return result

    return json.dumps(data)


def mqtt_transport():
    """Return the paho transport for the configured connection: "websockets" when
    mqtt_websockets is set, otherwise "tcp". Must be passed to the Client() constructor."""
    return "websockets" if getattr(config, "mqtt_websockets", False) else "tcp"


def configure_mqtt_connection(client):
    """Apply post-construction connection options to the MQTT client. Sets the WebSocket
    path when mqtt_websockets is enabled, and TLS when mqtt_tls is set (e.g. port 8883):
    system CA certs by default, honouring an optional CA file and insecure mode.
    (The transport itself is set in the Client() constructor via mqtt_transport().)"""
    if getattr(config, "mqtt_websockets", False):
        path = getattr(config, "mqtt_websocket_path", "") or "/mqtt"
        client.ws_set_options(path=path)
    if getattr(config, "mqtt_tls", False):
        ca_certs = getattr(config, "mqtt_tls_ca_certs", "") or None
        client.tls_set(ca_certs=ca_certs)
        if getattr(config, "mqtt_tls_insecure", False):
            client.tls_insecure_set(True)


def create_mqtt_client():

    def on_log(client, userdata, level, buf):
        if level == paho.MQTT_LOG_ERR:
            print("MQTT error: ", buf)


    def on_connect(client, userdata, flags, rc):
        if rc != 0:
            print("Error: Unable to connect to MQTT broker, return code:", rc)


    client = paho.Client(client_id="rpi-mqtt-monitor-" + hostname + str(int(time.time())), transport=mqtt_transport())
    client.username_pw_set(config.mqtt_user, config.mqtt_password)
    configure_mqtt_connection(client)
    client.on_log = on_log
    client.on_connect = on_connect
    # Set a short socket timeout to avoid hanging if MQTT server is unreachable
    client.socket_timeout = 5  # seconds
    try:
        # Use connect_async and loop_start to avoid blocking
        client.connect_async(config.mqtt_host, int(config.mqtt_port))
        client.loop_start()
        # Wait for connection or timeout
        max_wait = 10  # seconds
        waited = 0
        while not client.is_connected() and waited < max_wait:
            time.sleep(0.2)
            waited += 0.2
        if not client.is_connected():
            print("Error: MQTT connection timed out.")
            client.loop_stop()
            return None
    except Exception as e:
        print("Error connecting to MQTT broker:", e)
        try:
            client.loop_stop()
        except Exception:
            pass
        return None
    return client


def publish_update_status_to_mqtt(git_update, apt_updates):
    client = create_mqtt_client()
    if client is None:
        print("Error: Unable to connect to MQTT broker")
        return

    if config.git_update:
        if config.discovery_messages:
            client.publish(config.mqtt_discovery_prefix + "/binary_sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_git_update/config",
                           config_json('git_update'), qos=config.qos)
        client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/git_update", git_update, qos=1, retain=config.retain)

    if config.update:
        if config.discovery_messages:
            client.publish(config.mqtt_discovery_prefix + "/update/" + hostname + "/config",
                           config_json('update'), qos=1)

    if config.apt_updates:
        if config.discovery_messages:
            client.publish(config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_apt_updates/config",
                           config_json('apt_updates'), qos=config.qos)
        client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/apt_updates", apt_updates, qos=config.qos, retain=config.retain)


    # Wait for all messages to be delivered
    while len(client._out_messages) > 0:
        time.sleep(0.1)
        client.loop()

    client.loop_stop()
    client.disconnect()


def publish_update_progress(client, in_progress, new_ver, percentage=None):
    """Publish update progress to the update entity's state topic so Home Assistant
    shows an 'installing' state and progress bar while the update runs.

    HA's MQTT update integration reads in_progress/update_percentage from the state
    payload (via value_template), not from the discovery config, so progress must be
    sent here. The version fields are kept so the git_update binary_sensor and the
    version display keep working."""
    if not config.update:
        return
    try:
        payload = {
            "installed_ver": config.version,
            "new_ver": new_ver,
            "in_progress": bool(in_progress),
            "update_percentage": percentage,
        }
        client.publish(
            config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/git_update",
            json.dumps(payload), qos=1, retain=config.retain)
    except Exception as e:
        print("Could not publish update progress state:", e)


def publish_to_hass_api(monitored_values):
    for param, value in monitored_values.items():
        if value:
            if param == 'drive_temps' and isinstance(value, dict):
                for device, temp in value.items():
                    entity_id = f"sensor.{hostname.replace('-','_')}_{device}_temp"
                    state = temp
                    attributes = config_json(device + "_temp", device, True)
                    send_sensor_data_to_home_assistant(entity_id, state, attributes)
            elif param == 'used_space_paths' and isinstance(value, dict):
                for name, used in value.items():
                    entity_id = f"sensor.{hostname.replace('-','_')}_used_space_{name}"
                    attributes = config_json("used_space_" + name, name, True)
                    send_sensor_data_to_home_assistant(entity_id, used, attributes)
            else:
                entity_id = f"sensor.{hostname.replace('-','_')}_{param}"
                state = value
                attributes = config_json(param, "0", True)
                send_sensor_data_to_home_assistant(entity_id, state, attributes)


def send_sensor_data_to_home_assistant(entity_id, state, attributes):
    home_assistant_url = config.hass_host
    api_token = config.hass_token
    url = f"{home_assistant_url}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    data = {
        "state": state,
        "attributes": attributes
    }
    response = requests.post(url, headers=headers, json=data)
    if response.status_code in [200, 201]:
        pass
    else:
        print(f"Failed to update {entity_id}: {response.status_code} - {response.text}")


def publish_to_mqtt(monitored_values):
    client = create_mqtt_client()
    if client is None:
        return

    non_standard_values = ['restart_button', 'shutdown_button', 'display_control', 'drive_temps', 'ext_sensors', 'used_space_paths']
  # Publish standard monitored values
    for key, value in monitored_values.items():
        if key not in non_standard_values and key in config.__dict__ and config.__dict__[key]:
            if config.discovery_messages:
                client.publish(f"{config.mqtt_discovery_prefix}/sensor/{config.mqtt_topic_prefix}/{hostname}_{key}/config",
                            config_json(key), qos=config.qos)
            if config.use_availability:
                client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/{key}_availability", 'offline' if value is None else 'online', qos=config.qos)
            client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/{key}", value, qos=config.qos, retain=config.retain)

  # Publish non standard values    
    if config.restart_button:
        if config.discovery_messages:
            client.publish(config.mqtt_discovery_prefix + "/button/" + config.mqtt_topic_prefix + "/" + hostname + "_restart/config",
                           config_json('restart_button'), qos=config.qos)
    if config.shutdown_button:
        if config.discovery_messages:
            client.publish(config.mqtt_discovery_prefix + "/button/" + config.mqtt_topic_prefix + "/" + hostname + "_shutdown/config",
                           config_json('shutdown_button'), qos=config.qos)
    if config.display_control:
        if config.discovery_messages:
            client.publish(config.mqtt_discovery_prefix + "/button/" + config.mqtt_topic_prefix + "/" + hostname + "_display_on/config",
                           config_json('display_on'), qos=config.qos)
            client.publish(config.mqtt_discovery_prefix + "/button/" + config.mqtt_topic_prefix + "/" + hostname + "_display_off/config",
                           config_json('display_off'), qos=config.qos)
    if "used_space_paths" in monitored_values:
        for name, value in monitored_values["used_space_paths"].items():
            key = "used_space_" + name
            if config.discovery_messages:
                client.publish(f"{config.mqtt_discovery_prefix}/sensor/{config.mqtt_topic_prefix}/{hostname}_{key}/config",
                               config_json(key, name), qos=config.qos)
            if config.use_availability:
                client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/{key}_availability",
                               'offline' if value is None else 'online', qos=config.qos)
            client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/{key}",
                           value, qos=config.qos, retain=config.retain)

    if config.drive_temps:
        for device, temp in monitored_values['drive_temps'].items():
            if config.discovery_messages:
                client.publish(config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_" + device + "_temp/config",
                           config_json(device + "_temp", device), qos=config.qos)
            if config.use_availability:
                client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/{device}_temp_availability", 'offline' if temp is None else 'online', qos=config.qos)
            client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + device + "_temp", temp, qos=config.qos, retain=config.retain)

    if config.ext_sensors:
        # we loop through all sensors
        for item in monitored_values['ext_sensors']:
            # item[0] = name
            # item[1] = sensor_type
            # item[2] = ID
            # item[3] = value, like temperature or humidity
            if item[1] == "ds18b20":
                if config.discovery_messages:
                    client.publish(
                        config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_" + item[0] + "_status/config",
                        config_json('ds18b20_status', device=item[0]), qos=config.qos)
                if config.use_availability:
                    client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/ds18b20_status_{item[0]}_availability", 'offline' if item[3] is None else 'online', qos=config.qos)
                client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + "ds18b20_status_" + item[0], item[3], qos=config.qos, retain=config.retain)
            if item[1] == "sht21":
                if config.discovery_messages:
                    # temperature
                    client.publish(
                        config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_" + item[0] + "_temp_status/config",
                        config_json('sht21_temp_status', device=item[0]), qos=config.qos)
                    # humidity
                    client.publish(
                        config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_" + item[0] + "_hum_status/config",
                        config_json('sht21_hum_status', device=item[0]), qos=config.qos)
                if config.use_availability:
                    client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/sht21_temp_status_{item[0]}_availability", 'offline' if item[3][0] is None else 'online', qos=config.qos)
                    client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/sht21_hum_status_{item[0]}_availability", 'offline' if item[3][1] is None else 'online', qos=config.qos)
                # temperature
                client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + "sht21_temp_status_" + item[0], item[3][0], qos=config.qos, retain=config.retain)
                # humidity
                client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + "sht21_hum_status_" + item[0], item[3][1], qos=config.qos, retain=config.retain)
                
    status_sensor_topic = config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_status/config"
    client.publish(status_sensor_topic, config_json('status'), qos=config.qos)
    client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/status", "1", qos=config.qos, retain=config.retain)

    if "data_sent" in monitored_values:
        if config.discovery_messages:
            client.publish(f"{config.mqtt_discovery_prefix}/sensor/{config.mqtt_topic_prefix}/{hostname}_data_sent/config",
                           config_json("data_sent"), qos=config.qos)
        if config.use_availability:
            client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/data_sent_availability", 'offline' if monitored_values["data_sent"] is None else 'online', qos=config.qos)
        client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/data_sent",
                       monitored_values["data_sent"], qos=config.qos, retain=config.retain)

    if "data_received" in monitored_values:
        if config.discovery_messages:
            client.publish(f"{config.mqtt_discovery_prefix}/sensor/{config.mqtt_topic_prefix}/{hostname}_data_received/config",
                           config_json("data_received"), qos=config.qos)
        if config.use_availability:
            client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/data_received_availability", 'offline' if monitored_values["data_received"] is None else 'online', qos=config.qos)
        client.publish(f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/data_received",
                       monitored_values["data_received"], qos=config.qos, retain=config.retain)
    
    while len(client._out_messages) > 0:
        time.sleep(0.1)
        client.loop()

    client.loop_stop()
    client.disconnect()


def bulk_publish_to_mqtt(monitored_values):
    values = [monitored_values.get(key, 0) for key in [
        'cpu_load', 'cpu_temp', 'used_space', 'voltage', 'sys_clock_speed', 'swap', 'memory', 'uptime', 'uptime_seconds',
        'wifi_signal', 'wifi_signal_dbm', 'rpi5_fan_speed', 'git_update', 'rpi_power_status', 'data_sent', 'data_received',
        'intel_gpu_render', 'intel_gpu_video', 'intel_gpu_freq', 'intel_gpu_power'
    ]]

    values.extend(monitored_values.get('used_space_paths', {}).values())

    ext_sensors = monitored_values.get('ext_sensors', [])
    values.extend(sensor[3] for sensor in ext_sensors)
    values_str = ', '.join(map(str, values))

    client = create_mqtt_client()
    if client is None:
        return

    client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname, values_str, qos=config.qos, retain=config.retain)

    while len(client._out_messages) > 0:
        time.sleep(0.1)
        client.loop()

    client.loop_stop()
    client.disconnect()


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog='rpi-mqtt-monitor',
        description='Monitor CPU load, temperature, frequency, free space, etc., and publish the data to an MQTT server or Home Assistant API.'
    )
    parser.add_argument('-H', '--hass_api', action='store_true',  help='send readings via Home Assistant API (not via MQTT)', default=False)
    parser.add_argument('-d', '--display',  action='store_true',  help='display values on screen', default=False)
    parser.add_argument('-s', '--service',  action='store_true',  help='run script as a service, sleep interval is configurable in config.py', default=False)
    parser.add_argument('-v', '--version',  action='store_true',  help='display installed version and exit', default=False)
    parser.add_argument('-u', '--update',   action='store_true',  help='update script and config then exit', default=False)
    parser.add_argument('-w', '--hass_wake', action='store_true', help='display Home assistant wake on lan configuration', default=False)
    parser.add_argument('--uninstall', action='store_true', help='uninstall rpi-mqtt-monitor and remove all related files')
    args = parser.parse_args()

    if args.update:
        version = update.check_git_version_remote(script_dir).strip()
        update.do_update(script_dir, version, True)

        exit()

    if args.version:
        installed_version = config.version
        latest_versino = update.check_git_version_remote(script_dir).strip()
        print("Installed version: " + installed_version)
        print("Latest version: " + latest_versino)
        if installed_version != latest_versino:
            print("Update available")
        else:
            print("No update available")
        exit()

    if args.hass_wake:
        hass_config = """Add this to your Home Assistant switches.yaml file: 

  - platform: wake_on_lan
    mac: "{}"
    host: "{}"
    name: "{}-switch"
    turn_off:
      service: mqtt.publish
      data:
        topic: "{}/update/{}/command"
        payload: "shutdown"
    """.format(get_mac_address(), get_network_ip(), hostname, config.mqtt_discovery_prefix, hostname )
        print(hass_config)
        exit()

    return args


def _parse_intel_gpu_json(out):
    """Parse intel_gpu_top -J output into the most recent sample dict, or None."""
    out = (out or "").strip()
    if not out:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        # -J streams concatenated objects / an unterminated array when interrupted.
        # Extract the LAST complete top-level {...} object (most recent sample).
        last, depth, start = None, 0, None
        for i, ch in enumerate(out):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    last = out[start:i + 1]
        if last is None:
            return None
        try:
            data = json.loads(last)
        except json.JSONDecodeError:
            return None
    if isinstance(data, list):
        data = data[-1] if data else {}
    return data if isinstance(data, dict) else None


def get_intel_gpu_stats():
    """Return intel_gpu_top's latest JSON sample, or None on failure.
    Needs root: works under the systemd service; under cron `sudo -n` fails fast
    (non-interactive) so the cycle is not blocked waiting for a password.

    Fast path uses `-n 1` (print one sample and exit). Older intel-gpu-tools lack
    `-n`; for those, fall back to running without it, bounding the run with the
    `timeout` command (SIGINT, like Ctrl-C) and parsing the streamed sample."""
    # Fast path: modern intel_gpu_top prints one sample and exits immediately.
    try:
        out = subprocess.run(
            ["sudo", "-n", "intel_gpu_top", "-s", "0", "-n", "1", "-J"],
            capture_output=True, text=True, timeout=10).stdout
        data = _parse_intel_gpu_json(out)
        if data:
            return data
    except Exception:
        pass
    # Fallback for older versions without `-n`: run its loop and stop via `timeout`.
    try:
        out = subprocess.run(
            ["sudo", "-n", "timeout", "--signal=INT", "2",
             "intel_gpu_top", "-s", "500", "-J"],
            capture_output=True, text=True, timeout=10).stdout
        return _parse_intel_gpu_json(out)
    except Exception:
        return None


def _intel_gpu_engine_busy(gpu, prefix):
    """Max busy% across intel_gpu_top engines whose name starts with prefix
    ("Render" -> Render/3D, "Video" -> Video + VideoEnhance)."""
    engines = gpu.get("engines", {}) if isinstance(gpu, dict) else {}
    vals = [e.get("busy", 0) for name, e in engines.items()
            if name.startswith(prefix) and isinstance(e, dict)]
    if not vals:
        return None if config.use_availability else 0
    return round(max(vals), 1)


def _intel_gpu_value(gpu, path, ndigits, fallback_path=None):
    """Pull a nested numeric from the intel_gpu_top JSON (e.g. ["frequency","actual"]),
    optionally falling back to another path."""
    for p in (path, fallback_path):
        if not p:
            continue
        node = gpu
        ok = True
        for key in p:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                ok = False
                break
        if ok and isinstance(node, (int, float)):
            return round(node, ndigits)
    return None if config.use_availability else 0


def collect_monitored_values():
    monitored_values = {}

    if config.cpu_load:
        monitored_values["cpu_load"] = check_cpu_load()
    if config.cpu_temp:
        monitored_values["cpu_temp"] = check_cpu_temp()
    if config.used_space:
        monitored_values["used_space"] = check_used_space(config.used_space_path)
    extra_space = {}
    for entry in getattr(config, "used_space_paths", []) or []:
        slug = _slugify(entry.get("name") or entry.get("path"))
        extra_space[slug] = check_used_space(entry["path"])
    if extra_space:
        monitored_values["used_space_paths"] = extra_space
    if config.voltage:
        monitored_values["voltage"] = check_voltage()
    if config.sys_clock_speed:
        monitored_values["sys_clock_speed"] = check_sys_clock_speed()
    if config.swap:
        monitored_values["swap"] = check_swap()
    if config.memory:
        monitored_values["memory"] = check_memory()
    if config.uptime:
        monitored_values["uptime"] = check_uptime('timestamp')
    if config.uptime_seconds:
        monitored_values["uptime_seconds"] = check_uptime('')
    if config.wifi_signal:
        monitored_values["wifi_signal"] = check_wifi_signal('')
    if config.wifi_signal_dbm:
        monitored_values["wifi_signal_dbm"] = check_wifi_signal('dbm')
    if config.rpi5_fan_speed:
        monitored_values["rpi5_fan_speed"] = check_rpi5_fan_speed()
    if config.drive_temps:
        monitored_values["drive_temps"] = check_all_drive_temps()
    if config.rpi_power_status:
        monitored_values["rpi_power_status"] = check_rpi_power_status()
    if config.ext_sensors:
        monitored_values["ext_sensors"] = read_ext_sensors()
    if config.net_io:
        data_sent, data_received = get_network_data()
        monitored_values["data_sent"] = data_sent
        monitored_values["data_received"] = data_received
    if (getattr(config, "intel_gpu_render", False) or getattr(config, "intel_gpu_video", False)
            or getattr(config, "intel_gpu_freq", False) or getattr(config, "intel_gpu_power", False)):
        gpu = get_intel_gpu_stats() or {}
        if getattr(config, "intel_gpu_render", False):
            monitored_values["intel_gpu_render"] = _intel_gpu_engine_busy(gpu, "Render")
        if getattr(config, "intel_gpu_video", False):
            monitored_values["intel_gpu_video"] = _intel_gpu_engine_busy(gpu, "Video")
        if getattr(config, "intel_gpu_freq", False):
            monitored_values["intel_gpu_freq"] = _intel_gpu_value(gpu, ["frequency", "actual"], 0)
        if getattr(config, "intel_gpu_power", False):
            monitored_values["intel_gpu_power"] = _intel_gpu_value(gpu, ["power", "GPU"], 2, ["power", "Package"])

    return monitored_values


def get_network_data():
    net_io = psutil.net_io_counters()
    data_sent = net_io.bytes_sent / (1024 * 1024)  # Convert bytes to megabytes
    data_received = net_io.bytes_recv / (1024 * 1024)  # Convert bytes to megabytes
    return round(data_sent, 2), round(data_received, 2)


def gather_and_send_info():
    while not stop_event.is_set():       
        monitored_values = collect_monitored_values()

        if hasattr(config, 'random_delay'):
            time.sleep(config.random_delay)

        if args.display:
            print_measured_values(monitored_values)

        # write some output to a file
        if config.output_filename:
            # the only options are "a" for append or "w" for (over)write
            # check if one of this options is defined
            if config.output_mode not in ["a", "w"]:
                print("Error, output_type not known. Default w is set.")
                config.output_type = "w"
            try:
                # open the text file
                output_file = open(config.output_filename, config.output_mode)
                # read what should be written into the textfile
                # we need to define this is a function, otherwise the values are not updated and default values are taken
                output_content = config.get_content_outputfile()
                output_file.write(output_content)
                output_file.close()
            except Exception as e:
                print("Error writing to output file:", e)

        if args.hass_api:
            if config.hass_host != "your_hass_host" and config.hass_token != "your_hass_token":
                publish_to_hass_api(monitored_values)
            else:
                print("Error: Home Assistant API host or token not configured.")
                sys.exit(1) 
        else:
            if config.mqtt_host != "ip address or host":
                if hasattr(config, 'group_messages') and config.group_messages:
                    bulk_publish_to_mqtt(monitored_values)
                else:
                    publish_to_mqtt(monitored_values)
            else:
                pass
        if not args.service:
            break
        # Break the sleep into 1-second intervals and check stop_event after each interval
        for _ in range(config.service_sleep_time):
            if stop_event.is_set():
                break
            time.sleep(1)


def update_status():
    while not stop_event.is_set():
        git_update = check_git_update(script_dir)
        apt_updates = get_apt_updates()
        publish_update_status_to_mqtt(git_update, apt_updates)
        stop_event.wait(config.update_check_interval)
        if stop_event.is_set():
            break


def uninstall_script():
    """Call the remote_install.sh script to uninstall the application."""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../remote_install.sh")
    
    if not os.path.exists(script_path):
        print("Error: remote_install.sh script not found.")
        return

    try:
        # Run the uninstall command
        subprocess.run(["bash", script_path, "uninstall"], check=True)
        print("Uninstallation process completed.")
    except subprocess.CalledProcessError as e:
        print(f"Error during uninstallation: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


_ddcutil_display_cache = None


def _ddcutil_displays():
    """Return the DDC display indexes reported by `ddcutil detect`, cached after
    the first call because detection is slow (~1-2s). Falls back to [1]."""
    global _ddcutil_display_cache
    if _ddcutil_display_cache is not None:
        return _ddcutil_display_cache
    displays = []
    try:
        out = subprocess.run(["ddcutil", "detect", "--brief"],
                             capture_output=True, text=True, timeout=30).stdout
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Display "):
                try:
                    displays.append(int(line.split()[1]))
                except (IndexError, ValueError):
                    pass
    except Exception as e:
        print("ddcutil detect failed:", e)
    _ddcutil_display_cache = displays or [1]
    return _ddcutil_display_cache


def set_display_power(turn_on):
    """Turn attached display(s) on/off across X11, wlroots-Wayland, Raspberry Pi
    and GNOME/generic Wayland (DDC/CI). Logs which backend ran."""
    state = "on" if turn_on else "off"

    # 1. Explicit user override always wins (empty string = auto-detect)
    override = getattr(config, "display_{}_command".format(state), "")
    if override:
        rc = os.system(override)
        print("display {}: custom command rc={}".format(state, rc))
        return

    session = os.environ.get("XDG_SESSION_TYPE", "")

    # 2a. X11 -> legacy xset DPMS (keep su -l for service-as-root setups)
    if session == "x11" or (session != "wayland" and os.environ.get("DISPLAY") and shutil.which("xset")):
        os.system('su -l {} -c "xset -display :0 dpms force {}"'.format(config.os_user, state))
        print("display {}: xset/DPMS (X11)".format(state))
        return

    # 2b. wlroots Wayland (Pi labwc/wayfire, sway) -> wlr-randr per connected output
    if shutil.which("wlr-randr"):
        env = os.environ.copy()
        env.setdefault("WAYLAND_DISPLAY", "wayland-0")
        if "XDG_RUNTIME_DIR" not in env:
            # When the service runs as root, getuid() is 0 -> /run/user/0, which is not
            # the graphical session. Resolve os_user's uid so we point at /run/user/<uid>.
            uid = os.getuid()
            if uid == 0 and getattr(config, "os_user", ""):
                try:
                    import pwd
                    uid = pwd.getpwnam(config.os_user).pw_uid
                except Exception:
                    pass
            env["XDG_RUNTIME_DIR"] = "/run/user/{}".format(uid)
        try:
            listing = subprocess.run(["wlr-randr"], capture_output=True, text=True,
                                     env=env, timeout=15).stdout
            outputs = [ln.split()[0] for ln in listing.splitlines()
                       if ln and not ln[0].isspace()]
            for out in outputs:
                subprocess.run(["wlr-randr", "--output", out,
                                "--on" if turn_on else "--off"], env=env, timeout=15)
            print("display {}: wlr-randr ({} output(s))".format(state, len(outputs)))
        except Exception as e:
            print("display {}: wlr-randr failed: {}".format(state, e))
        return

    # 2c. Raspberry Pi -> vcgencmd
    if shutil.which("vcgencmd"):
        os.system("vcgencmd display_power {}".format(1 if turn_on else 0))
        print("display {}: vcgencmd".format(state))
        return

    # 2d. GNOME / generic Wayland -> ddcutil DDC/CI (d6 = power mode: 01 on,
    #     04 off -- DPM Off keeps the DDC bus alive so we can power back on;
    #     05/hard-off can leave the monitor unreachable until a physical button press)
    if shutil.which("ddcutil"):
        val = "01" if turn_on else "04"
        for disp in _ddcutil_displays():
            os.system("ddcutil --display {} setvcp d6 {}".format(disp, val))
        print("display {}: ddcutil DDC/CI".format(state))
        return

    print("display {}: no supported backend (install ddcutil or set "
          "display_{}_command in config.py)".format(state, state))


def on_message(client, userdata, msg):
    global exit_flag, thread1, thread2
    command = msg.payload.decode()
    print("Received message: ", command)

    # Map each command to the config flag that must be enabled for it to run,
    # so a stray or retained payload can't trigger a control the user disabled.
    command_gates = {
        "install": "update",
        "restart": "restart_button",
        "shutdown": "shutdown_button",
        "display_on": "display_control",
        "display_off": "display_control",
    }
    if command in command_gates and not getattr(config, command_gates[command], False):
        print("Ignored '{}': {} is disabled in config.".format(command, command_gates[command]))
        return

    if command == "install":
        def update_and_exit():
            version = update.check_git_version_remote(script_dir).strip()
            publish_update_progress(client, True, version, 0)

            def report(pct):
                publish_update_progress(client, True, version, pct)

            success = update.do_update(script_dir, version, git_update=True,
                                       config_update=True, progress_cb=report)
            if not success:
                print("Update failed; keeping service running on current version.")
                publish_update_progress(client, False, version, None)
                return
            publish_update_progress(client, True, version, 100)
            print("Update completed. Stopping MQTT client loop...")
            client.loop_stop()  # Stop the MQTT client loop
            print("Setting exit flag...")
            exit_flag = True
            stop_event.set()  # Signal the threads to stop
            if thread1 is not None:
                thread1.join()  # Wait for thread1 to finish
            if thread2 is not None:
                thread2.join()  # Wait for thread2 to finish
            os._exit(0)  # Exit the script immediately

        update_thread = threading.Thread(target=update_and_exit)
        update_thread.start()
    elif command in ("restart", "shutdown"):
        # systemctl reboot/poweroff honor logind "block" inhibitors (GNOME always holds
        # a session shutdown lock on Ubuntu Desktop), so plain `reboot`/`shutdown` are
        # silently refused with "Operation denied due to active block inhibitor".
        # -i / --ignore-inhibitors bypasses them; root is allowed to do this.
        action = "reboot" if command == "restart" else "poweroff"
        print("Restarting the system..." if command == "restart" else "Shutting down the system...")
        result = subprocess.run(["sudo", "systemctl", action, "-i"],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print("System {} failed (rc={}): {}".format(
                action, result.returncode, result.stderr.strip()))
    elif command == "display_off":
        print("Turn off display")
        set_display_power(False)
    elif command == "display_on":
        print("Turn on display")
        set_display_power(True)

exit_flag = False
thread1 = None
thread2 = None
stop_event = threading.Event()
script_dir = os.path.dirname(os.path.realpath(__file__))
# get device host name - used in mqtt topic
# and adhere to the allowed character set
if hasattr(config, 'ha_device_name') and config.ha_device_name:
    hostname = re.sub(r'[^a-zA-Z0-9_-]', '_', config.ha_device_name)
else:
    hostname = re.sub(r'[^a-zA-Z0-9_-]', '_', socket.gethostname())

if __name__ == '__main__':
    args = parse_arguments();

    if args.uninstall:
        uninstall_script()
        sys.exit(0)

    if args.service:
        if not args.hass_api:
            command_topic = config.mqtt_discovery_prefix + "/update/" + hostname + "/command"
            status_topic = config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/status"

            def on_service_connect(client, userdata, flags, rc):
                # Re-subscribe on every (re)connect: paho does not restore
                # subscriptions automatically after an auto-reconnect, so without
                # this the command buttons silently stop working after a broker
                # restart or network blip.
                if rc != 0:
                    print("Error: Unable to connect to MQTT broker, return code:", rc)
                    return
                client.subscribe(command_topic)
                client.publish(status_topic, "1", qos=config.qos, retain=config.retain)
                print("Listening to topic : " + command_topic)

            client = paho.Client(transport=mqtt_transport())
            client.username_pw_set(config.mqtt_user, config.mqtt_password)
            configure_mqtt_connection(client)
            client.on_message = on_message
            client.on_connect = on_service_connect
            # set will_set to send a message when the client disconnects
            client.will_set(status_topic, "0", qos=config.qos, retain=config.retain)
            # connect_async + loop_start so the service keeps retrying if the
            # broker is not yet reachable at boot (covered by systemd Restart too).
            client.connect_async(config.mqtt_host, int(config.mqtt_port))
            client.loop_start()


        thread1 = threading.Thread(target=gather_and_send_info)
        thread1.daemon = True  # Set thread1 as a daemon thread
        thread1.start()

        if not args.hass_api:
            if config.update:
                thread2 = threading.Thread(target=update_status)
                thread2.daemon = True  # Set thread2 as a daemon thread
                thread2.start()

        try:
            while True:
                time.sleep(1)  # Check the exit flag every second
        except KeyboardInterrupt:
            print(" Ctrl+C pressed. Setting exit flag...")
            if not args.hass_api:
                client.loop_stop()
            exit_flag = True
            stop_event.set()  # Signal the threads to stop
            sys.exit(0)  # Exit the script
    else:
        gather_and_send_info()
