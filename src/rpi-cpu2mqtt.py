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
import os
import sys
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
import logging
import math
#import external sensor lib only if one uses external sensors
if config.ext_sensors:
    # append folder ext_sensor_lib
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ext_sensor_lib')))
    import ds18b20
    from sht21 import SHT21

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


configlanguage = configparser.ConfigParser()
configlanguage.read(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'translations.ini'))

def get_translation(key):
    """ get the correct translation"""
    return configlanguage.get(config.language, key, fallback=key)


def sanitize_numeric(value):
    """Return a valid numeric value or a fallback when invalid."""
    try:
        if value is None:
            raise ValueError
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ValueError
        return value
    except Exception:
        return None if config.use_availability else 0


def check_wifi_signal(format):
    try:
        interfaces = glob.glob('/sys/class/ieee80211/*/device/net/*')
        interface = os.path.basename(interfaces[0]) if interfaces else None
        if not interface:
            raise RuntimeError('No Wi-Fi interface found')
        result = subprocess.run(['/sbin/iwconfig', interface], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        wifi_output = result.stdout
        if format == 'dbm':
            wifi_signal = wifi_output.strip().split(' ')[4].split('=')[1]
        else:
            quality = wifi_output.strip().split(' ')[1].split('=')[1].split('/')[0]
            wifi_signal = round((int(quality) / 70) * 100)
    except Exception:
        wifi_signal = None if config.use_availability else 0
    return wifi_signal


def check_used_space(path):
    st = os.statvfs(path)
    free_space = st.f_bavail * st.f_frsize
    total_space = st.f_blocks * st.f_frsize
    used_space = int(100 - ((free_space / total_space) * 100))

    return used_space


def check_cpu_load():
    return psutil.cpu_percent(interval=1)


def check_voltage():
    try:
        result = subprocess.run(['vcgencmd', 'measure_volts'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        voltage = result.stdout.strip().split('=')[1].rstrip('V')
    except Exception:
        voltage = None if config.use_availability else 0
    return voltage

def check_swap():
    try:
        result = subprocess.run(['free'], stdout=subprocess.PIPE, text=True, check=True)
        for line in result.stdout.splitlines():
            if line.lower().startswith('swap'):
                parts = line.split()
                if int(parts[1]) > 0:
                    swap = float(parts[2]) / float(parts[1]) * 100
                else:
                    swap = 0.0
                break
        else:
            swap = 0.0
        swap = round(swap, 1)
    except Exception:
        swap = None if config.use_availability else 0
    return swap

def check_memory():
    try:
        result = subprocess.run(['free','-b'], stdout=subprocess.PIPE, text=True, check=True)
        parts = result.stdout.splitlines()[1].split()
        memory = round(float(parts[2]) / float(parts[1]) * 100)
    except Exception:
        memory = None if config.use_availability else 0
    return memory

def check_rpi_power_status():
    try:
        result = subprocess.run(['vcgencmd', 'get_throttled'], stdout=subprocess.PIPE, text=True, check=True)
        throttled = result.stdout.split('=')[1].strip()
        throttled_val = int(throttled, 16)
        if throttled_val & 1<<0:
            return 'Under-voltage'
        if throttled_val & 1<<3:
            return 'Soft temperature limit'
        if throttled_val & 1<<1:
            return 'ARM frequency capped'
        if throttled_val & 1<<2:
            return 'Throttled'
        return 'OK'
    except Exception as e:
        return 'Error: ' + str(e)

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
        logger.error("Error checking crontab: %s", e)
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
            try:
                if item[2] == 0:
                    sensors = ds18b20.get_available_sensors()
                    if not sensors:
                        raise RuntimeError("No DS18B20 sensors found")
                    item[2] = sensors[0]
                temp = ds18b20.sensor_DS18B20(sensor_id=item[2])
                item[3] = temp
                if temp == -300:
                    raise RuntimeError("Read error")
            except Exception:
                logger.error("Error while reading sensor %s, %s", item[1], item[2])
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
                logger.error("Error while reading sensor %s", item[1])
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
        logger.error("Error reading CPU temperature: %s", e)
        return None if config.use_availability else 0


def check_sys_clock_speed():
    try:
        with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq') as f:
            freq = int(f.read().strip())
        return freq // 1000
    except Exception as e:
        logger.error("Error reading system clock speed: %s", e)
        return None if config.use_availability else 0


def check_uptime(format):
    if format == 'timestamp':
        tz_str = subprocess.run(['date','+%z'], stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
        timestamp_str = subprocess.run(['uptime','-s'], stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        return timestamp.isoformat() + tz_str
    else:
        with open('/proc/uptime') as f:
            uptime_seconds = float(f.read().split()[0])
        return int(uptime_seconds)

def check_model_name():
    try:
        with open('/sys/firmware/devicetree/base/model') as f:
            model_name = f.read().strip()
        if not model_name:
            with open('/proc/cpuinfo') as f:
                for line in f:
                    if 'name' in line.lower():
                        model_name = line.split(':')[1].strip()
                        break
    except Exception:
        model_name = None if config.use_availability else 'Unknown'
    return model_name

def check_rpi5_fan_speed():
    try:
        paths = glob.glob('/sys/devices/platform/cooling_fan/hwmon/*/fan1_input')
        if not paths:
            return None if config.use_availability else '0'
        with open(paths[0]) as f:
            return f.read().strip()
    except Exception:
        return None if config.use_availability else '0'

def get_os():
    try:
        with open('/etc/os-release') as f:
            for line in f:
                if line.startswith('PRETTY_NAME='):
                    return line.split('=',1)[1].strip().strip('"')
    except Exception:
        return None if config.use_availability else 'Unknown'

def get_manufacturer():
    try:
        if 'Raspberry' not in check_model_name():
            with open('/proc/cpuinfo') as f:
                for line in f:
                    if 'vendor' in line.lower():
                        return line.split(':')[1].strip()
        else:
            return 'Raspberry Pi'
    except Exception:
        return None if config.use_availability else 'Unknown'

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
    try:
        rev = subprocess.run(['git', '-C', script_dir, 'rev-list', '--tags', '--max-count=1'], stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
        result = subprocess.run(['git', '-C', script_dir, 'describe', '--tags', rev], stdout=subprocess.PIPE, text=True, check=True)
        git_version = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        logger.error('Error getting git version: %s', e)
        git_version = ''
    return git_version

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
        cmd = ['apt-get', '-q', '-y', '--ignore-hold', '--allow-change-held-packages', '--allow-unauthenticated', '-s', 'dist-upgrade']
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        grep = subprocess.run(['grep', '^Inst'], input=result.stdout, text=True, stdout=subprocess.PIPE)
        updates_count = len([line for line in grep.stdout.splitlines() if line])
    except Exception as e:
        logger.error("Error checking for updates: %s", e)
        updates_count = None if config.use_availability else 0

    return updates_count


def get_hwmon_device_name(hwmon_path):
    try:
        with open(os.path.join(hwmon_path, 'name'), 'r') as f:
            return f.read().strip()
    except Exception as e:
        logger.error("Error reading name for %s: %s", hwmon_path, e)
        return None


def get_hwmon_temp(hwmon_path):
    try:
        temp_files = glob.glob(os.path.join(hwmon_path, 'temp*_input'))
        for temp_file in temp_files:
            with open(temp_file, 'r') as tf:
                temp = int(tf.read().strip()) / 1000.0
                return temp
    except Exception as e:
        logger.error("Error reading temperature for %s: %s", hwmon_path, e)
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
    remote_version = update.check_git_version_remote(script_dir)
    output = """:: rpi-mqtt-monitor :: v {}

:: Device Information
   Model Name: {}
   Manufacturer: {}
   OS: {}
   Hostname: {}
   IP Address: {}
   MAC Address: {}
""".format(config.version, check_model_name(), get_manufacturer(), get_os(), hostname, get_network_ip(), get_mac_address())

    output += "   Service Sleep Time: {} seconds\n".format(config.service_sleep_time)
    if config.update:
        output += "   Update Check Interval: {} seconds\n".format(config.update_check_interval)
    # Add dynamic measured values with units
    measured_values = {
        get_translation("cpu_load"): ("cpu_load", "%"),
        get_translation("cpu_temperature"): ("cpu_temp", "°C"),
        get_translation("used_space"): ("used_space", "%"),
        get_translation("voltage"): ("voltage", "V"),
        get_translation("cpu_clock_speed"): ("sys_clock_speed", "MHz"),
        get_translation("disk_swap"): ("swap", "%"),
        get_translation("memory_usage"): ("memory", "%"),
        get_translation("uptime"): ("uptime", ""),
        get_translation("wifi_signal"): ("wifi_signal", "%"),
        get_translation("wifi_signal_strength")+" [dBm]": ("wifi_signal_dbm", "dBm"),
        get_translation("fan_speed"): ("rpi5_fan_speed", "RPM"),
        get_translation("rpi_power_status"): ("rpi_power_status", ""),
        get_translation("update"): ("update", ""),
        get_translation("external_sensors"): ("ext_sensors", ""),
        get_translation("data_sent"): ("data_sent", "MB"),
        get_translation("data_received"): ("data_received", "MB")
    }

    output += "\n:: Measured values\n"
    for label, (key, unit) in measured_values.items():
        if key in monitored_values:
            output += f"   {label}: {monitored_values[key]} {unit}\n"

    if config.drive_temps:
        drive_temps = check_all_drive_temps()
        if len(drive_temps) > 0:
            for device, temp in drive_temps.items():
                output += f"   {device.capitalize()} Temp: {temp:.2f}°C\n"
    output += "\n:: Scheduling\n "

    if check_service_file_exists():
        output += "  Running as Service\n"
    if check_crontab_entry():
        output += "  Running as Cron Job\n"
        
    output += """\n:: Installation directory :: {}

:: Release notes {}: 
{}""".format(os.path.dirname(script_dir), remote_version, get_release_notes(remote_version))
    logger.info("\n%s", output)
    

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
        release_notes = None if config.use_availability else "No release notes available"

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
        add_common_attributes(data, "mdi:wifi", get_translation("wifi_signal"), "%", "signal_strength", "measurement")
    elif what_config == "wifi_signal_dbm":
        add_common_attributes(data, "mdi:wifi", get_translation("wifi_signal_strength"), "dBm", "signal_strength", "measurement")
    elif what_config == "rpi5_fan_speed":
        add_common_attributes(data, "mdi:fan", get_translation("fan_speed"), "RPM", None, "measurement")
    elif what_config == "status":
        add_common_attributes(data, "mdi:lan-connect", get_translation("status"))
        data["value_template"] = "{{ 'Online' if value == '1' else 'Offline' }}"
    elif what_config == "git_update":
        add_common_attributes(data, "mdi:git", get_translation("rpi_mqtt_monitor"), None, "update", "measurement")
        data["title"] = "Device Update"
        data["value_template"] = "{{ 'ON' if value_json.installed_ver != value_json.new_ver else 'OFF' }}"
    elif what_config == "update":
        version = update.check_git_version_remote(script_dir)
        add_common_attributes(data, "mdi:update", get_translation("rpi_mqtt_monitor"), None, "firmware")
        data["title"] = "New Version"
        data["state_topic"] = config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + "git_update"
        data["value_template"] = "{{ {'installed_version': value_json.installed_ver, 'latest_version': value_json.new_ver } | to_json }}"
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
        data["device_class"] = "restart"
    elif what_config == "display_on":
        add_common_attributes(data, "mdi:monitor", get_translation("monitor_on"))
        data["command_topic"] = config.mqtt_discovery_prefix + "/update/" + hostname + "/command"
        data["payload_press"] = "display_on"
        data["device_class"] = "restart"
    elif what_config == "display_off":
        add_common_attributes(data, "mdi:monitor", get_translation("monitor_off"))
        data["command_topic"] = config.mqtt_discovery_prefix + "/update/" + hostname + "/command"
        data["payload_press"] = "display_off"
        data["device_class"] = "restart"
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
        add_common_attributes(data, "mdi:water-percent", device + " " + get_translation("humidity"), "%", "temperature", "measurement")
        data["state_topic"] = config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + what_config + "_" + device
        data["unique_id"] = hostname + "_" + what_config + "_" + device
    elif what_config == "data_sent":
        add_common_attributes(data, "mdi:upload", get_translation("data_sent"), "MB", None, "measurement")
    elif what_config == "data_received":
        add_common_attributes(data, "mdi:download", get_translation("data_received"), "MB", None, "measurement")

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


def create_mqtt_client():
    def on_log(client, userdata, level, buf):
        if level == paho.MQTT_LOG_ERR:
            logger.error("MQTT error: %s", buf)

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            logger.info("MQTT connected")
            # (Re-)subscribe to command topic on every connect
            cmd_topic = f"{config.mqtt_discovery_prefix}/update/{hostname}/command"
            client.subscribe(cmd_topic)
            logger.info("Subscribed to command topic: %s", cmd_topic)
        else:
            logger.error("Error: connect failed, rc=%s", rc)

    def on_disconnect(client, userdata, rc):
        if rc != 0:
            logger.warning("MQTT disconnected (rc=%s), will auto-reconnect…", rc)

        # Persistent session + auto-re-subscribe on reconnect
    client = paho.Client(
        client_id=f"rpi-mqtt-monitor-{hostname}-{int(time.time())}",
        clean_session=False
    )
    client.username_pw_set(config.mqtt_user, config.mqtt_password)
    client.on_log = on_log
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    # enable built-in backoff
    client.reconnect_delay_set(min_delay=1, max_delay=120)

    try:
        # Use async connect so the client will retry in the background
        client.connect_async(config.mqtt_host, int(config.mqtt_port), keepalive=60)
    except Exception as e:
        # Even if the initial connection fails, return the client so it can
        # keep retrying in the background when loop_start() is called.
        logger.error("Error initiating MQTT connection: %s", e)

    return client

def publish_update_status_to_mqtt(git_update, apt_updates, client=None):
    own_client = False
    if client is None:
        client = create_mqtt_client()
        client.loop_start()
        own_client = True

    if not client.is_connected():
        logger.warning("MQTT client not connected, skipping publish_update_status")
        if own_client:
            client.loop_stop()
            client.disconnect()
        return
    publish_infos = []
    if config.git_update:
        if config.discovery_messages:
            publish_infos.append(
                client.publish(
                    config.mqtt_discovery_prefix + "/binary_sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_git_update/config",
                    config_json('git_update'), qos=config.qos))
        publish_infos.append(
            client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/git_update",
                          git_update, qos=1, retain=config.retain))

    if config.update:
        if config.discovery_messages:
            publish_infos.append(
                client.publish(config.mqtt_discovery_prefix + "/update/" + hostname + "/config",
                              config_json('update'), qos=1))

    if config.apt_updates:
        if config.discovery_messages:
            publish_infos.append(
                client.publish(
                    config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_apt_updates/config",
                    config_json('apt_updates'), qos=config.qos))
        publish_infos.append(
            client.publish(
                config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/apt_updates",
                apt_updates, qos=config.qos, retain=config.retain))


    for info in publish_infos:
        try:
            info.wait_for_publish()
        except RuntimeError as e:
            logger.error("Publish failed: %s", e)
            break

    if own_client:
        client.loop_stop()
        client.disconnect()


def publish_to_hass_api(monitored_values):
    for param, value in monitored_values.items():
        if value:
            if param == 'drive_temps' and isinstance(value, dict):
                for device, temp in value.items():
                    entity_id = f"sensor.{hostname.replace('-','_')}_{device}_temp"
                    state = temp
                    attributes = config_json(device + "_temp", device, True)
                    send_sensor_data_to_home_assistant(entity_id, state, attributes)
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
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code not in [200, 201]:
            logger.error(
                "Failed to update %s: %s - %s",
                entity_id,
                response.status_code,
                response.text,
            )
    except requests.RequestException as exc:
        logger.error("Error sending %s to Home Assistant: %s", entity_id, exc)


def publish_to_mqtt(monitored_values, client=None):
    own_client = False
    if client is None:
        client = create_mqtt_client()
        client.loop_start()
        own_client = True

    if not client.is_connected():
        logger.warning("MQTT client not connected, skipping publish")
        if own_client:
            client.loop_stop()
            client.disconnect()
        return
    publish_infos = []
    non_standard_values = ['restart_button', 'shutdown_button', 'display_control', 'drive_temps', 'ext_sensors']
  # Publish standard monitored values
    for key, value in monitored_values.items():
        if key not in non_standard_values and key in config.__dict__ and config.__dict__[key]:
            if config.discovery_messages:
                publish_infos.append(
                    client.publish(
                        f"{config.mqtt_discovery_prefix}/sensor/{config.mqtt_topic_prefix}/{hostname}_{key}/config",
                        config_json(key), qos=config.qos))
            if config.use_availability:
                publish_infos.append(
                    client.publish(
                        f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/{key}_availability",
                        'Offline' if value is None else 'Online', qos=config.qos))
            publish_infos.append(
                client.publish(
                    f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/{key}",
                    value, qos=config.qos, retain=config.retain))

  # Publish non standard values    
    if config.restart_button:
        if config.discovery_messages:
            publish_infos.append(
                client.publish(
                    config.mqtt_discovery_prefix + "/button/" + config.mqtt_topic_prefix + "/" + hostname + "_restart/config",
                    config_json('restart_button'), qos=config.qos))
    if config.shutdown_button:
        if config.discovery_messages:
            publish_infos.append(
                client.publish(
                    config.mqtt_discovery_prefix + "/button/" + config.mqtt_topic_prefix + "/" + hostname + "_shutdown/config",
                    config_json('shutdown_button'), qos=config.qos))
    if config.display_control:
        if config.discovery_messages:
            publish_infos.append(
                client.publish(
                    config.mqtt_discovery_prefix + "/button/" + config.mqtt_topic_prefix + "/" + hostname + "_display_on/config",
                    config_json('display_on'), qos=config.qos))
            publish_infos.append(
                client.publish(
                    config.mqtt_discovery_prefix + "/button/" + config.mqtt_topic_prefix + "/" + hostname + "_display_off/config",
                    config_json('display_off'), qos=config.qos))
    if config.drive_temps:
        for device, temp in monitored_values['drive_temps'].items():
            if config.discovery_messages:
                publish_infos.append(
                    client.publish(
                        config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_" + device + "_temp/config",
                        config_json(device + "_temp", device), qos=config.qos))
            if config.use_availability:
                publish_infos.append(
                    client.publish(
                        f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/{device}_temp_availability",
                        'Offline' if temp is None else 'Online', qos=config.qos))
            publish_infos.append(
                client.publish(
                    config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + device + "_temp",
                    temp, qos=config.qos, retain=config.retain))

    if config.ext_sensors:
        # we loop through all sensors
        for item in monitored_values['ext_sensors']:
            # item[0] = name
            # item[1] = sensor_type
            # item[2] = ID
            # item[3] = value, like temperature or humidity
            if item[1] == "ds18b20":
                if config.discovery_messages:
                    publish_infos.append(
                        client.publish(
                            config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_" + item[0] + "_status/config",
                            config_json('ds18b20_status', device=item[0]), qos=config.qos))
                if config.use_availability:
                    publish_infos.append(
                        client.publish(
                            f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/ds18b20_status_{item[0]}_availability",
                            'Offline' if item[3] is None else 'Online', qos=config.qos))
                publish_infos.append(
                    client.publish(
                        config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + "ds18b20_status_" + item[0],
                        item[3], qos=config.qos, retain=config.retain))
            if item[1] == "sht21":
                if config.discovery_messages:
                    # temperature
                    publish_infos.append(
                        client.publish(
                            config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_" + item[0] + "_temp_status/config",
                            config_json('sht21_temp_status', device=item[0]), qos=config.qos))
                    # humidity
                    publish_infos.append(
                        client.publish(
                            config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_" + item[0] + "_hum_status/config",
                            config_json('sht21_hum_status', device=item[0]), qos=config.qos))
                if config.use_availability:
                    publish_infos.append(
                        client.publish(
                            f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/sht21_temp_status_{item[0]}_availability",
                            'Offline' if item[3][0] is None else 'Online', qos=config.qos))
                    publish_infos.append(
                        client.publish(
                            f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/sht21_hum_status_{item[0]}_availability",
                            'Offline' if item[3][1] is None else 'Online', qos=config.qos))
                # temperature
                publish_infos.append(
                    client.publish(
                        config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + "sht21_temp_status_" + item[0],
                        item[3][0], qos=config.qos, retain=config.retain))
                # humidity
                publish_infos.append(
                    client.publish(
                        config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/" + "sht21_hum_status_" + item[0],
                        item[3][1], qos=config.qos, retain=config.retain))
                
    status_sensor_topic = config.mqtt_discovery_prefix + "/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_status/config"
    publish_infos.append(
        client.publish(status_sensor_topic, config_json('status'), qos=config.qos))
    publish_infos.append(
        client.publish(config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname + "/status",
                      "1", qos=config.qos, retain=config.retain))

    if "data_sent" in monitored_values:
        if config.discovery_messages:
            publish_infos.append(
                client.publish(
                    f"{config.mqtt_discovery_prefix}/sensor/{config.mqtt_topic_prefix}/{hostname}_data_sent/config",
                    config_json("data_sent"), qos=config.qos))
        publish_infos.append(
            client.publish(
                f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/data_sent",
                monitored_values["data_sent"], qos=config.qos, retain=config.retain))

    if "data_received" in monitored_values:
        if config.discovery_messages:
            publish_infos.append(
                client.publish(
                    f"{config.mqtt_discovery_prefix}/sensor/{config.mqtt_topic_prefix}/{hostname}_data_received/config",
                    config_json("data_received"), qos=config.qos))
        publish_infos.append(
            client.publish(
                f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/data_received",
                monitored_values["data_received"], qos=config.qos, retain=config.retain))
    
    for info in publish_infos:
        try:
            info.wait_for_publish()
        except RuntimeError as e:
            logger.error("Publish failed: %s", e)
            break

    if own_client:
        client.loop_stop()
        client.disconnect()


def bulk_publish_to_mqtt(monitored_values, client=None):
    values = [monitored_values.get(key, 0) for key in [
        'cpu_load', 'cpu_temp', 'used_space', 'voltage', 'sys_clock_speed', 'swap', 'memory', 'uptime', 'uptime_seconds',
        'wifi_signal', 'wifi_signal_dbm', 'rpi5_fan_speed', 'git_update', 'rpi_power_status', 'data_sent', 'data_received'
    ]]

    ext_sensors = monitored_values.get('ext_sensors', [])
    values.extend(sensor[3] for sensor in ext_sensors)
    values_str = ', '.join(map(str, values))

    own_client = False
    if client is None:
        client = create_mqtt_client()
        client.loop_start()
        own_client = True

    if not client.is_connected():
        logger.warning("MQTT client not connected, skipping bulk_publish")
        if own_client:
            client.loop_stop()
            client.disconnect()
        return
    info = client.publish(
        config.mqtt_uns_structure + config.mqtt_topic_prefix + "/" + hostname,
        values_str, qos=config.qos, retain=config.retain)

    try:
        info.wait_for_publish()
    except RuntimeError as e:
        logger.error("Publish failed: %s", e)

    if own_client:
        client.loop_stop()
        client.disconnect()


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog='rpi-mqtt-monitor',
        description='Monitor CPU Load, temperature, frequency, free space, etc., and publish the data to an MQTT server or Home Assistant API.'
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
        latest_version = update.check_git_version_remote(script_dir).strip()
        logger.info("Installed version: %s", installed_version)
        logger.info("Latest version: %s", latest_version)
        if installed_version != latest_version:
            logger.info("Update available")
            response = input("Update to %s? [y/N]: " % latest_version)
            if response.lower() in ["y", "yes"]:
                update.do_update(script_dir, latest_version, True)
        else:
            logger.info("No update available")
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
    """.format(get_mac_address(), get_network_ip(), hostname, config.mqtt_discovery_prefix, hostname)
        logger.info("%s", hass_config)
        exit()

    return args


def collect_monitored_values():
    monitored_values = {}

    if config.cpu_load:
        monitored_values["cpu_load"] = sanitize_numeric(check_cpu_load())
    if config.cpu_temp:
        monitored_values["cpu_temp"] = sanitize_numeric(check_cpu_temp())
    if config.used_space:
        monitored_values["used_space"] = sanitize_numeric(check_used_space(config.used_space_path))
    if config.voltage:
        monitored_values["voltage"] = sanitize_numeric(check_voltage())
    if config.sys_clock_speed:
        monitored_values["sys_clock_speed"] = sanitize_numeric(check_sys_clock_speed())
    if config.swap:
        monitored_values["swap"] = sanitize_numeric(check_swap())
    if config.memory:
        monitored_values["memory"] = sanitize_numeric(check_memory())
    if config.uptime:
        monitored_values["uptime"] = check_uptime('timestamp')
    if config.uptime_seconds:
        monitored_values["uptime_seconds"] = sanitize_numeric(check_uptime(''))
    if config.wifi_signal:
        monitored_values["wifi_signal"] = sanitize_numeric(check_wifi_signal(''))
    if config.wifi_signal_dbm:
        monitored_values["wifi_signal_dbm"] = sanitize_numeric(check_wifi_signal('dbm'))
    if config.rpi5_fan_speed:
        monitored_values["rpi5_fan_speed"] = sanitize_numeric(check_rpi5_fan_speed())
    if config.drive_temps:
        temps = check_all_drive_temps()
        monitored_values["drive_temps"] = {k: sanitize_numeric(v) for k, v in temps.items()}
    if config.rpi_power_status:
        monitored_values["rpi_power_status"] = check_rpi_power_status()
    if config.ext_sensors:
        sensors = read_ext_sensors()
        for sensor in sensors:
            if isinstance(sensor[3], list):
                sensor[3] = [sanitize_numeric(v) for v in sensor[3]]
            else:
                sensor[3] = sanitize_numeric(sensor[3])
        monitored_values["ext_sensors"] = sensors
    if config.net_io:
        data_sent, data_received = get_network_data()
        monitored_values["data_sent"] = sanitize_numeric(data_sent)
        monitored_values["data_received"] = sanitize_numeric(data_received)

    return monitored_values


def get_network_data():
    net_io = psutil.net_io_counters()
    data_sent = net_io.bytes_sent / (1024 * 1024)  # Convert bytes to megabytes
    data_received = net_io.bytes_recv / (1024 * 1024)  # Convert bytes to megabytes
    return round(data_sent, 2), round(data_received, 2)


def gather_and_send_info(mqtt_client=None):
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
                logger.warning("Error, output_mode not known. Default w is set.")
                config.output_mode = "w"
            try:
                # read what should be written into the textfile
                # we need to define this is a function, otherwise the values are not updated and default values are taken
                output_content = config.get_content_outputfile()
                with open(config.output_filename, config.output_mode) as output_file:
                    output_file.write(output_content)
            except Exception as e:
                logger.error("Error writing to output file: %s", e)

        if args.hass_api:
            if config.hass_host != "your_hass_host" and config.hass_token != "your_hass_token":
                publish_to_hass_api(monitored_values)
            else:
                logger.error("Error: Home Assistant API host or token not configured.")
                sys.exit(1)
        else:
            if config.mqtt_host != "ip address or host":
                if hasattr(config, 'group_messages') and config.group_messages:
                    bulk_publish_to_mqtt(monitored_values, mqtt_client)
                else:
                    publish_to_mqtt(monitored_values, mqtt_client)
            else:
                pass
        if not args.service:
            break
        # Break the sleep into 1-second intervals and check stop_event after each interval
        for _ in range(config.service_sleep_time):
            if stop_event.is_set():
                break
            time.sleep(1)


def update_status(mqtt_client=None):
    while not stop_event.is_set():
        git_update = check_git_update(script_dir)
        apt_updates = get_apt_updates()
        publish_update_status_to_mqtt(git_update, apt_updates, mqtt_client)
        stop_event.wait(config.update_check_interval)
        if stop_event.is_set():
            break


def uninstall_script():
    """Call the remote_install.sh script to uninstall the application."""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../remote_install.sh")
    
    if not os.path.exists(script_path):
        logger.error("Error: remote_install.sh script not found.")
        return

    try:
        # Run the uninstall command
        subprocess.run(["bash", script_path, "uninstall"], check=True)
        logger.info("Uninstallation process completed.")
    except subprocess.CalledProcessError as e:
        logger.error("Error during uninstallation: %s", e)
    except Exception as e:
        logger.error("Unexpected error: %s", e)


def on_message(client, userdata, msg):
    global thread1, thread2
    logger.info("Received message: %s", msg.payload.decode())
    if msg.payload.decode() == "install":
        def update_and_exit():
            version = update.check_git_version_remote(script_dir).strip()
            update.do_update(script_dir, version, git_update=True, config_update=True)
            logger.info("Update completed. Stopping MQTT client loop...")
            client.loop_stop()  # Stop the MQTT client loop
            logger.info("Signalling threads to stop...")
            stop_event.set()  # Signal the threads to stop
            if thread1 is not None:
                thread1.join()  # Wait for thread1 to finish
            if thread2 is not None:
                thread2.join()  # Wait for thread2 to finish
            sys.exit(0)  # Exit the script gracefully

        update_thread = threading.Thread(target=update_and_exit)
        update_thread.start()
    elif msg.payload.decode() == "restart":
        logger.info("Restarting the system...")
        subprocess.run(["sudo", "reboot"], check=True)
    elif msg.payload.decode() == "shutdown":
        logger.info("Shutting down the system...")
        subprocess.run(["sudo", "shutdown", "now"], check=True)
    elif msg.payload.decode() == "display_off":
        logger.info("Turn off display")
        subprocess.run(
            ["su", "-l", config.os_user, "-c", "xset -display :0 dpms force off"],
            check=True
        )
    elif msg.payload.decode() == "display_on":
        logger.info("Turn on display")
        subprocess.run(
            ["su", "-l", config.os_user, "-c", "xset -display :0 dpms force on"],
            check=True
        )

stop_event = threading.Event()
thread1 = None
thread2 = None
script_dir = os.path.dirname(os.path.realpath(__file__))
# get device host name - used in mqtt topic
# and adhere to the allowed character set
if hasattr(config, 'ha_device_name') and config.ha_device_name:
    hostname = re.sub(r'[^a-zA-Z0-9_-]', '_', config.ha_device_name)
else:
    hostname = re.sub(r'[^a-zA-Z0-9_-]', '_', socket.gethostname())

if __name__ == '__main__':
    args = parse_arguments()

    if args.uninstall:
        uninstall_script()
        sys.exit(0)

    if args.service:
        # 1. Create a resilient MQTT client (with auto-reconnect)
        client = create_mqtt_client()
        if client is None:
            sys.exit(1)

        # 2. If using MQTT (not hass_api), hook up command handling
        if not args.hass_api:
            client.on_message = on_message
            client.will_set(
                f"{config.mqtt_uns_structure}{config.mqtt_topic_prefix}/{hostname}/status",
                "0", qos=config.qos, retain=config.retain
            )
            client.subscribe(f"{config.mqtt_discovery_prefix}/update/{hostname}/command")
            logger.info("Listening to topic: %s/update/%s/command", config.mqtt_discovery_prefix, hostname)

        # 3. Start your metric‐gathering threads
        thread1 = threading.Thread(target=gather_and_send_info, args=(client,), daemon=True)
        thread1.start()
        if not args.hass_api and config.update:
            thread2 = threading.Thread(target=update_status, args=(client,), daemon=True)
            thread2.start()

        # 4. Start the network loop in the background (handles reconnects automatically)
        client.loop_start()
        try:
            # main thread waits until stop_event is set (from on_message or KeyboardInterrupt)
            while not stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Ctrl+C pressed. Shutting down…")
            stop_event.set()
        finally:
            # cleanly stop the network loop and exit
            client.loop_stop()
            sys.exit(0)

    else:
        # One-shot (non-service) mode
        gather_and_send_info()
