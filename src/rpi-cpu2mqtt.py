# -*- coding: utf-8 -*-
# Python script (runs on 2 and 3) to monitor cpu load, temperature, frequency, free space etc.
# on a Raspberry Pi or Ubuntu computer and publish the data to a MQTT server.
# RUN sudo apt-get install python-pip
# RUN pip install paho-mqtt

from __future__ import division
import subprocess
import time
import socket
import paho.mqtt.client as paho
import json
import os
import sys
import argparse
import threading
import update
import config


# get device host name - used in mqtt topic
hostname = socket.gethostname()

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
        wifi_signal = 0

    return wifi_signal


def check_used_space(path):
    st = os.statvfs(path)
    free_space = st.f_bavail * st.f_frsize
    total_space = st.f_blocks * st.f_frsize
    used_space = int(100 - ((free_space / total_space) * 100))

    return used_space


def check_cpu_load():
    p = subprocess.Popen("uptime", shell=True, stdout=subprocess.PIPE).communicate()[0]
    cores = subprocess.Popen("nproc", shell=True, stdout=subprocess.PIPE).communicate()[0]
    cpu_load = str(p).split("average:")[1].split(", ")[0].replace(' ', '').replace(',', '.')
    cpu_load = float(cpu_load) / int(cores) * 100
    cpu_load = round(float(cpu_load), 1)

    return cpu_load


def check_voltage():
    try:
        full_cmd = "vcgencmd measure_volts | cut -f2 -d= | sed 's/000//'"
        voltage = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0]
        voltage = voltage.strip()[:-1]
    except Exception:
        voltage = 0

    return voltage.decode('utf8')


def check_swap():
    full_cmd = "free -t |grep -i swap | awk 'NR == 1 {print $3/$2*100}'"
    swap = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]
    swap = round(float(swap.decode("utf-8").replace(",", ".")), 1)

    return swap


def check_memory():
    full_cmd = "free -t | awk 'NR == 2 {print $3/$2*100}'"
    memory = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]
    memory = round(float(memory.decode("utf-8").replace(",", ".")))

    return memory


def check_cpu_temp():
    full_cmd = "cat /sys/class/thermal/thermal_zone*/temp 2> /dev/null | sed 's/\(.\)..$//' | tail -n 1"
    try:
        p = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]
        cpu_temp = p.decode("utf-8").strip()
    except Exception:
        cpu_temp = 0

    return cpu_temp


def check_sys_clock_speed():
    full_cmd = "awk '{printf (\"%0.0f\",$1/1000); }' </sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"

    return subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]


def check_uptime(format):
    full_cmd = "awk '{print int($1"+format+")}' /proc/uptime"

    return int(subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0])


def check_model_name():
   full_cmd = "cat /sys/firmware/devicetree/base/model"
   model_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
   if model_name == '':
        full_cmd = "cat /proc/cpuinfo  | grep 'name'| uniq"
        model_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
        model_name = model_name.split(':')[1].replace('\n', '')

   return model_name


def check_rpi5_fan_speed():
   full_cmd = "cat /sys/devices/platform/cooling_fan/hwmon/*/fan1_input"
   rpi5_fan_speed = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8").strip()

   return rpi5_fan_speed


def get_os():
    full_cmd = 'cat /etc/os-release | grep -i pretty_name'
    pretty_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
    pretty_name = pretty_name.split('=')[1].replace('"', '').replace('\n', '')

    return(pretty_name)


def get_manufacturer():
    if 'Raspberry' not in check_model_name():
        full_cmd = "cat /proc/cpuinfo  | grep 'vendor'| uniq"
        pretty_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
        pretty_name = pretty_name.split(':')[1].replace('\n', '')
    else:
        pretty_name = 'Raspberry Pi'

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
    full_cmd = "git -C {} describe --tags `git -C {} rev-list --tags --max-count=1`".format(script_dir, script_dir)
    git_version = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8").replace('\n', '')

    return(git_version)


def get_network_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def print_measured_values( cpu_load=0, cpu_temp=0, used_space=0, voltage=0, sys_clock_speed=0, swap=0, memory=0,
                    uptime_days=0, uptime_seconds = 0, wifi_signal=0, wifi_signal_dbm=0, rpi5_fan_speed=0, git_update=False):
    print(":: rpi-mqtt-monitor")
    print("   Version: " + config.version)
    print("")
    print(":: Device Information")
    print("   Model Name: " + check_model_name())
    print("   Manufacturer: " + get_manufacturer())
    print("   OS: " + get_os())
    print("   Hostname: " + hostname)
    print("   IP Address: " + get_network_ip())
    if args.service:
        print("   Service Sleep Time: " + str(config.service_sleep_time))
    print("")
    print(":: Measured values")
    print("   CPU Load: " + str(cpu_load) + " %")
    print("   CPU Temp: " + str(cpu_temp) + " °C")
    print("   Used Space: " + str(used_space) + " %")
    print("   Voltage: " + str(voltage) + " V")
    print("   CPU Clock Speed: " + str(sys_clock_speed) + " MHz")
    print("   Swap: " + str(swap) + " %")
    print("   Memory: " + str(memory) + " %")
    print("   Uptime: " + str(uptime_days) + " days")
    print("   Uptime: " + str(uptime_seconds) + " seconds")
    print("   Wifi Signal: " + str(wifi_signal) + " %")
    print("   Wifi Signal dBm: " + str(wifi_signal_dbm) +  " dBm")
    print("   RPI5 Fan Speed: " + str(rpi5_fan_speed) + " RPM")
    print("   Update Available: " + str(git_update))
    print("")


def config_json(what_config):
    model_name = check_model_name()
    manufacturer = get_manufacturer()
    os = get_os()
    data = {
        "state_topic": "",
        "icon": "",
        "name": "",
        "unique_id": "",
        "unit_of_measurement": "",
        "device": {
            "identifiers": [hostname],
            "manufacturer": 'github.com/hjelev',
            "model": 'RPi MQTT Monitor ' + config.version,
            "name": hostname,
            "sw_version": os,
            "hw_version": model_name + " by " + manufacturer,
            "configuration_url": "https://github.com/hjelev/rpi-mqtt-monitor"
        }
    }

    data["state_topic"] = config.mqtt_topic_prefix + "/" + hostname + "/" + what_config
    data["unique_id"] = hostname + "_" + what_config
    if what_config == "cpuload":
        data["icon"] = "mdi:speedometer"
        data["name"] = "CPU Usage"
        data["state_class"] = "measurement"
        data["unit_of_measurement"] = "%"
    elif what_config == "cputemp":
        data["icon"] = "hass:thermometer"
        data["name"] = "CPU Temperature"
        data["unit_of_measurement"] = "°C"
        data["state_class"] = "measurement"
    elif what_config == "diskusage":
        data["icon"] = "mdi:harddisk"
        data["name"] = "Disk Usage"
        data["unit_of_measurement"] = "%"
        data["state_class"] = "measurement"
    elif what_config == "voltage":
        data["icon"] = "mdi:flash"
        data["name"] = "CPU Voltage"
        data["unit_of_measurement"] = "V"
        data["state_class"] = "measurement"
    elif what_config == "swap":
        data["icon"] = "mdi:harddisk"
        data["name"] = "Disk Swap"
        data["unit_of_measurement"] = "%"
        data["state_class"] = "measurement"
    elif what_config == "memory":
        data["icon"] = "mdi:memory"
        data["name"] = "Memory Usage"
        data["unit_of_measurement"] = "%"
        data["state_class"] = "measurement"
    elif what_config == "sys_clock_speed":
        data["icon"] = "mdi:speedometer"
        data["name"] = "CPU Clock Speed"
        data["unit_of_measurement"] = "MHz"
        data["state_class"] = "measurement"
    elif what_config == "uptime_days":
        data["icon"] = "mdi:calendar"
        data["name"] = "Uptime"
        data["unit_of_measurement"] = "days"
        data["state_class"] = "total_increasing"
    elif what_config == "uptime_seconds":
        data["icon"] = "mdi:timer-outline"
        data["name"] = "Uptime"
        data["unit_of_measurement"] = "s"
        data["device_class"] = "duration"
        data["state_class"] = "total_increasing"
    elif what_config == "wifi_signal":
        data["icon"] = "mdi:wifi"
        data["name"] = "Wifi Signal"
        data["unit_of_measurement"] = "%"
        data["state_class"] = "measurement"
    elif what_config == "wifi_signal_dbm":
        data["icon"] = "mdi:wifi"
        data["name"] = "Wifi Signal"
        data["unit_of_measurement"] = "dBm"
        data["state_class"] = "measurement"
    elif what_config == "rpi5_fan_speed":
        data["icon"] = "mdi:fan"
        data["name"] = "Fan Speed"
        data["unit_of_measurement"] = "RPM"
        data["state_class"] = "measurement"
    elif what_config == "git_update":
        data["icon"] = "mdi:git"
        data["name"] = "RPi MQTT Monitor"
        data["title"] = "Device Update"
        data["device_class"] = "update"
        data["state_class"] = "measurement"
        data["value_template"] = "{{ 'ON' if value_json.installed_ver != value_json.new_ver else 'OFF' }}"
    elif what_config == "update":
        version = update.check_git_version_remote(script_dir).strip()
        data["icon"] = "mdi:update"
        data["name"] = "RPi MQTT Monitor"
        data["title"] = "New Version"
        data["state_topic"] = config.mqtt_topic_prefix + "/" + hostname + "/" + "git_update"
        data["value_template"] = "{{ {'installed_version': value_json.installed_ver, 'latest_version': value_json.new_ver } | to_json }}"
        data["device_class"] = "firmware"
        data["command_topic"] = "homeassistant/update/" + hostname + "/command"
        data["payload_install"] = "install"
        data['release_url'] = "https://github.com/hjelev/rpi-mqtt-monitor/releases/tag/" + version
        data['entity_picture'] = "https://masoko.net/rpi-mqtt-monitor.png"
    elif what_config == "restart_button":
        data["icon"] = "mdi:restart"
        data["name"] = "System Restart"
        data["command_topic"] = "homeassistant/update/" + hostname + "/command"
        data["payload_press"] = "restart"
    else:
        return ""
    # Return our built discovery config
    return json.dumps(data)


def on_log(client, userdata, level, buf):
    if level == paho.MQTT_LOG_ERR:
        print("MQTT error: ", buf)


def on_connect(client, userdata, flags, rc):
    if rc != 0:
        print("Error: Unable to connect to MQTT broker, return code:", rc)


def create_mqtt_client():
    client = paho.Client(client_id="rpi-mqtt-monitor-" + hostname)
    client.username_pw_set(config.mqtt_user, config.mqtt_password)
    client.on_log = on_log
    client.on_connect = on_connect
    try:
        client.connect(config.mqtt_host, int(config.mqtt_port))
    except Exception as e:
        print("Error connecting to MQTT broker:", e)
        return None
    return client


def publish_update_status_to_mqtt(git_update):

    client = create_mqtt_client()
    if client is None:
        return
      
    client.loop_start()
    if config.git_update:
        if config.discovery_messages:
            client.publish("homeassistant/binary_sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_git_update/config",
                           config_json('git_update'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/git_update", git_update, qos=config.qos, retain=config.retain)
    
    if config.update:
        if config.discovery_messages:
            client.publish("homeassistant/update/" + hostname + "/config",
                           config_json('update'), qos=config.qos)
    client.loop_stop()
    client.disconnect()        


def publish_to_mqtt(cpu_load=0, cpu_temp=0, used_space=0, voltage=0, sys_clock_speed=0, swap=0, memory=0,
                    uptime_days=0, uptime_seconds=0, wifi_signal=0, wifi_signal_dbm=0, rpi5_fan_speed=0):
    # connect to mqtt server
    client = create_mqtt_client()
    if client is None:
        return
      
    client.loop_start()
    # publish monitored values to MQTT
    if config.cpu_load:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_cpuload/config",
                           config_json('cpuload'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/cpuload", cpu_load, qos=config.qos, retain=config.retain)
    if config.cpu_temp:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_cputemp/config",
                           config_json('cputemp'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/cputemp", cpu_temp, qos=config.qos, retain=config.retain)
    if config.used_space:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_diskusage/config",
                           config_json('diskusage'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/diskusage", used_space, qos=config.qos, retain=config.retain)
    if config.voltage:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_voltage/config",
                           config_json('voltage'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/voltage", voltage, qos=config.qos, retain=config.retain)
    if config.swap:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_swap/config",
                           config_json('swap'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/swap", swap, qos=config.qos, retain=config.retain)
    if config.memory:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_memory/config",
                           config_json('memory'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/memory", memory, qos=config.qos, retain=config.retain)
    if config.sys_clock_speed:
        if config.discovery_messages:
            client.publish(
                "homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_sys_clock_speed/config",
                config_json('sys_clock_speed'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/sys_clock_speed", sys_clock_speed, qos=config.qos, retain=config.retain)
    if config.uptime:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_uptime_days/config",
                           config_json('uptime_days'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/uptime_days", uptime_days, qos=config.qos, retain=config.retain)
    if config.uptime_seconds:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_uptime_seconds/config",
                           config_json('uptime_seconds'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/uptime_seconds", uptime_seconds, qos=config.qos, retain=config.retain)
    if config.wifi_signal:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_wifi_signal/config",
                           config_json('wifi_signal'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/wifi_signal", wifi_signal, qos=config.qos, retain=config.retain)
    if config.wifi_signal_dbm:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_wifi_signal_dbm/config",
                           config_json('wifi_signal_dbm'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/wifi_signal_dbm", wifi_signal_dbm, qos=config.qos, retain=config.retain)
    if config.rpi5_fan_speed:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_rpi5_fan_speed/config",
                           config_json('rpi5_fan_speed'), qos=config.qos)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/rpi5_fan_speed", rpi5_fan_speed, qos=config.qos, retain=config.retain)
    if config.restart_button:
        if config.discovery_messages:
            client.publish("homeassistant/button/" + config.mqtt_topic_prefix + "/" + hostname + "_restart/config",
                           config_json('restart_button'), qos=config.qos)

    client.loop_stop()
    # disconnect from mqtt server
    client.disconnect()


def bulk_publish_to_mqtt(cpu_load=0, cpu_temp=0, used_space=0, voltage=0, sys_clock_speed=0, swap=0, memory=0,
                         uptime_days=0, uptime_seconds=0, wifi_signal=0, wifi_signal_dbm=0, rpi5_fan_speed=0, git_update=0):
    # compose the CSV message containing the measured values

    values = cpu_load, cpu_temp, used_space, voltage, int(sys_clock_speed), swap, memory, uptime_days, uptime_seconds, wifi_signal, wifi_signal_dbm, rpi5_fan_speed, git_update
    values = str(values)[1:-1]

    client = paho.Client(client_id="rpi-mqtt-monitor-" + hostname)
    client.username_pw_set(config.mqtt_user, config.mqtt_password)
    client.on_log = on_log
    client.on_connect = on_connect

    try:
        client.connect(config.mqtt_host, int(config.mqtt_port))
    except Exception as e:
        print("Error connecting to MQTT broker:", e)
        return

    # publish monitored values to MQTT
    client.publish(config.mqtt_topic_prefix + "/" + hostname, values, qos=config.qos, retain=config.retain)

    # disconnect from mqtt server
    client.disconnect()


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--display', '-d', action='store_true', help='display values on screen', default=False)
    parser.add_argument('--service', '-s', action='store_true', help='run script as a service, sleep interval is configurable in config.py', default=False)
    parser.add_argument('--version', '-v', action='store_true', help='display installed version and exit', default=False)
    parser.add_argument('--update', '-u', action='store_true', help='update script and config then exit', default=False)
    args = parser.parse_args()

    if args.update:
        version = update.check_git_version_remote(script_dir).strip()
        git_update = check_git_update(script_dir)

        if git_update == 'on':
            git_update = True
        else:
            git_update = False

        update.do_update(script_dir, version, git_update)

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

    return args


def collect_monitored_values():
    cpu_load = cpu_temp = used_space = voltage = sys_clock_speed = swap = memory = uptime_seconds = uptime_days = wifi_signal = wifi_signal_dbm = rpi5_fan_speed = git_update = False

    if config.cpu_load:
        cpu_load = check_cpu_load()
    if config.cpu_temp:
        cpu_temp = check_cpu_temp()
    if config.used_space:
        used_space = check_used_space(config.used_space_path)
    if config.voltage:
        voltage = check_voltage()
    if config.sys_clock_speed:
        sys_clock_speed = check_sys_clock_speed()
    if config.swap:
        swap = check_swap()
    if config.memory:
        memory = check_memory()
    if config.uptime:
        uptime_days = check_uptime('/3600/24')
    if config.uptime_seconds:
        uptime_seconds = check_uptime('')
    if config.wifi_signal:
        wifi_signal = check_wifi_signal('')
    if config.wifi_signal_dbm:
        wifi_signal_dbm = check_wifi_signal('dbm')
    if config.rpi5_fan_speed:
        rpi5_fan_speed = check_rpi5_fan_speed()

    git_update = check_git_update(script_dir)

    return cpu_load, cpu_temp, used_space, voltage, sys_clock_speed, swap, memory, uptime_days, uptime_seconds, wifi_signal, wifi_signal_dbm, rpi5_fan_speed, git_update


def gather_and_send_info():
    while not stop_event.is_set():
        cpu_load, cpu_temp, used_space, voltage, sys_clock_speed, swap, memory, uptime_days, uptime_seconds, wifi_signal, wifi_signal_dbm, rpi5_fan_speed, git_update = collect_monitored_values()

        if hasattr(config, 'random_delay'):
            time.sleep(config.random_delay)

        if args.display:
            print_measured_values(cpu_load, cpu_temp, used_space, voltage, sys_clock_speed, swap, memory, uptime_days, uptime_seconds, wifi_signal, wifi_signal_dbm, rpi5_fan_speed, git_update)

        if hasattr(config, 'group_messages') and config.group_messages:
            bulk_publish_to_mqtt(cpu_load, cpu_temp, used_space, voltage, sys_clock_speed, swap, memory, uptime_days, uptime_seconds, wifi_signal, wifi_signal_dbm, rpi5_fan_speed)
        else:
            publish_to_mqtt(cpu_load, cpu_temp, used_space, voltage, sys_clock_speed, swap, memory, uptime_days, uptime_seconds, wifi_signal, wifi_signal_dbm, rpi5_fan_speed)

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
        publish_update_status_to_mqtt(git_update)
        stop_event.wait(config.update_check_interval)
        if stop_event.is_set():
            break


def on_message(client, userdata, msg):
    global exit_flag
    print("Received message: ", msg.payload.decode())
    if msg.payload.decode() == "install":
        version = update.check_git_version_remote(script_dir).strip()
        update.do_update(script_dir, version, git_update=True, config_update=True)
        print("Update completed. Setting exit flag...")
        exit_flag = True
        stop_event.set()  # Signal the threads to stop
        thread1.join()  # Wait for thread1 to finish
        thread2.join()  # Wait for thread2 to finish
        sys.exit(0)  # Exit the script
    elif msg.payload.decode() == "restart":
        print("Restarting the application...")
        # restart the system
        print("Restarting the system...")
        os.system("sudo reboot")

exit_flag = False

# Create a stop event
stop_event = threading.Event()

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.realpath(__file__))
    args = parse_arguments();

    if args.service:
        client = paho.Client()
        client.username_pw_set(config.mqtt_user, config.mqtt_password)
        client.on_message = on_message

        try:
            client.connect(config.mqtt_host, int(config.mqtt_port))
        except Exception as e:
            print("Error connecting to MQTT broker:", e)
            sys.exit(1)  # Exit the script

        client.subscribe("homeassistant/update/" + hostname + "/command")  # Replace with your MQTT topic
        print("Listening to topic : " + "homeassistant/update/" + hostname + "/command")

        # Start the gather_and_send_info function in a new thread
        thread1 = threading.Thread(target=gather_and_send_info)
        thread1.daemon = True  # Set the daemon attribute to True
        thread1.start()

        if config.update:
            # Start the update_status function in a new thread
            thread2 = threading.Thread(target=update_status)
            thread2.daemon = True  # Set the daemon attribute to True
            thread2.start()

        client.loop_start()  # Start the MQTT client loop in a new thread

        # Check the exit flag in the main thread
        while True:
            if exit_flag:
                print("Exit flag set. Exiting the application...")
                stop_event.set()  # Signal the threads to stop
                thread1.join()  # Wait for thread1 to finish
                thread2.join()  # Wait for thread2 to finish
                sys.exit(0)
            time.sleep(1)  # Check the exit flag every second
    else:
        gather_and_send_info()
