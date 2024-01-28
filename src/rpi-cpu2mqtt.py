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
import config
import os
import argparse

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


def check_uptime():
    full_cmd = "awk '{print int($1/3600/24)}' /proc/uptime"
    
    return int(subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0])


def check_model_name():
   full_cmd = "cat /sys/firmware/devicetree/base/model"
   model_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
   if model_name == '':
        full_cmd = "cat /proc/cpuinfo  | grep 'name'| uniq"
        model_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
        model_name = model_name.split(':')[1]
        
   return model_name


def check_rpi5_fan_speed():
   full_cmd = "cat /sys/devices/platform/cooling_fan/hwmon/*/fan1_input"
   rpi5_fan_speed = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
        
   return rpi5_fan_speed


def get_os():
    full_cmd = 'cat /etc/os-release | grep -i pretty_name'
    pretty_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
    pretty_name = pretty_name.split('=')[1].replace('"', '')
    
    return(pretty_name)


def get_manufacturer():
    if 'Raspberry' not in check_model_name():
        full_cmd = "cat /proc/cpuinfo  | grep 'vendor'| uniq"
        pretty_name = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
        pretty_name = pretty_name.split(':')[1]
    else:
        pretty_name = 'Raspberry Pi'
        
    return(pretty_name)


def check_git_update():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    full_cmd = "git -C {} remote update && git -C {} status -uno".format(script_dir, script_dir)
    try:
        git_update = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
    except subprocess.CalledProcessError as e:
        print("Error updating git repository:", e.output)

    if any(s in git_update for s in ('Your branch is up to date', 'Your branch is up-to-date')):
        git_update = 'off'
    else:
        git_update = 'on'
        
    return(git_update)

def check_git_version():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    full_cmd = "git -C {} describe --tags `git -C {} rev-list --tags --max-count=1`".format(script_dir, script_dir)
    git_version = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
    
    return(git_version)


def check_git_version_remote():
    script_dir = os.path.dirname(os.path.realpath(__file__))
    full_cmd = "git -C {} ls-remote --tags origin | awk -F'/' '{{print $3}}' | sort -V | tail -n 1".format(script_dir)
    result = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()[0].decode("utf-8")
    latest_tag = result.strip()
    return latest_tag if latest_tag else None

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

def print_values():
    print(":: Device Information")
    print("   Model Name: " + check_model_name().strip())
    print("   Manufacturer: " + get_manufacturer().strip())
    print("   OS: " + get_os().strip())
    print("   Hostname: " + hostname)
    print("   IP Address: " + get_network_ip())
    if args.service:
        print("   Service Sleep Time: " + str(config.service_sleep_time))
    print("")
    print(":: Measured values")
    print("   CPU Load: " + str(cpu_load))
    print("   CPU Temp: " + str(cpu_temp))
    print("   Used Space: " + str(used_space))
    print("   Voltage: " + str(voltage))
    print("   CPU Clock Speed: " + str(sys_clock_speed))
    print("   Swap: " + str(swap))
    print("   Memory: " + str(memory))
    print("   Uptime: " + str(uptime_days))
    print("   Wifi Signal: " + str(wifi_signal))
    print("   Wifi Signal dBm: " + str(wifi_signal_dbm))
    print("   RPI5 Fan Speed: " + str(rpi5_fan_speed))
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
            "manufacturer": manufacturer,
            "model": model_name,
            "name": hostname,
            "sw_version": os
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
        data["state_class"] = "measurement"
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
        data["name"] = "Update Available"
        data["state_class"] = "measurement"
        data["payload_on"] = "on"
        data["payload_off"] = "off"
    else:
        return ""
    # Return our built discovery config
    return json.dumps(data)


def publish_to_mqtt(cpu_load=0, cpu_temp=0, used_space=0, voltage=0, sys_clock_speed=0, swap=0, memory=0,
                    uptime_days=0, wifi_signal=0, wifi_signal_dbm=0, rpi5_fan_speed=0, git_update=False):
    # connect to mqtt server
    client = paho.Client(client_id="rpi-mqtt-monitor-" + hostname)
    client.username_pw_set(config.mqtt_user, config.mqtt_password)
    client.connect(config.mqtt_host, int(config.mqtt_port))

    # publish monitored values to MQTT
    if config.cpu_load:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_cpuload/config",
                           config_json('cpuload'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/cpuload", cpu_load, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.cpu_temp:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_cputemp/config",
                           config_json('cputemp'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/cputemp", cpu_temp, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.used_space:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_diskusage/config",
                           config_json('diskusage'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/diskusage", used_space, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.voltage:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_voltage/config",
                           config_json('voltage'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/voltage", voltage, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.swap:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_swap/config",
                           config_json('swap'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/swap", swap, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.memory:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_memory/config",
                           config_json('memory'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/memory", memory, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.sys_clock_speed:
        if config.discovery_messages:
            client.publish(
                "homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_sys_clock_speed/config",
                config_json('sys_clock_speed'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/sys_clock_speed", sys_clock_speed, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.uptime:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_uptime_days/config",
                           config_json('uptime_days'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/uptime_days", uptime_days, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.wifi_signal:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_wifi_signal/config",
                           config_json('wifi_signal'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/wifi_signal", wifi_signal, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.wifi_signal_dbm:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_wifi_signal_dbm/config",
                           config_json('wifi_signal_dbm'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/wifi_signal_dbm", wifi_signal_dbm, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.rpi5_fan_speed:
        if config.discovery_messages:
            client.publish("homeassistant/sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_rpi5_fan_speed/config",
                           config_json('rpi5_fan_speed'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/rpi5_fan_speed", rpi5_fan_speed, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    if config.git_update:
        if config.discovery_messages:
            client.publish("homeassistant/binary_sensor/" + config.mqtt_topic_prefix + "/" + hostname + "_git_update/config",
                           config_json('git_update'), qos=config.qos)
            time.sleep(config.sleep_time)
        client.publish(config.mqtt_topic_prefix + "/" + hostname + "/git_update", git_update, qos=config.qos, retain=config.retain)
        time.sleep(config.sleep_time)
    # disconnect from mqtt server
    client.disconnect()


def bulk_publish_to_mqtt(cpu_load=0, cpu_temp=0, used_space=0, voltage=0, sys_clock_speed=0, swap=0, memory=0,
                         uptime_days=0, wifi_signal=0, wifi_signal_dbm=0, rpi5_fan_speed=0, git_update=0):
    # compose the CSV message containing the measured values

    values = cpu_load, cpu_temp, used_space, voltage, int(sys_clock_speed), swap, memory, uptime_days, wifi_signal, wifi_signal_dbm, rpi5_fan_speed, git_update
    values = str(values)[1:-1]

    # connect to mqtt server
    client = paho.Client(client_id="rpi-mqtt-monitor-" + hostname)
    client.username_pw_set(config.mqtt_user, config.mqtt_password)
    client.connect(config.mqtt_host, int(config.mqtt_port))

    # publish monitored values to MQTT
    client.publish(config.mqtt_topic_prefix + "/" + hostname, values, qos=config.qos, retain=config.retain)

    # disconnect from mqtt server
    client.disconnect()


    
if __name__ == '__main__':
    # parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--display', '-d', action='store_true', help='Display values on screen', default=False)
    parser.add_argument('--service', '-s', action='store_true', help='Run script as a service', default=False)
    parser.add_argument('--version', '-v', action='store_true', help='Display version', default=False)
    args = parser.parse_args()

    if args.version:
        print("rpi-mqtt-monitor version: " + check_git_version().strip())
        print("rpi-mqtt-monitor remote version: " + check_git_version_remote().strip())
        exit()

    while True:
        # set all monitored values to False in case they are turned off in the config
        cpu_load = cpu_temp = used_space = voltage = sys_clock_speed = swap = memory = uptime_days = wifi_signal = wifi_signal_dbm = rpi5_fan_speed = git_update = False

        # delay the execution of the script
        if hasattr(config, 'random_delay'): time.sleep(config.random_delay)
        
        if hasattr(config, 'used_space_path'): used_space_path = config.used_space_path
        else: used_space_path = '/'
        
        # collect the monitored values
        if config.cpu_load:
            cpu_load = check_cpu_load()
        if config.cpu_temp:
            cpu_temp = check_cpu_temp()
        if config.used_space:
            used_space = check_used_space(used_space_path)
        if config.voltage:
            voltage = check_voltage()
        if config.sys_clock_speed:
            sys_clock_speed = check_sys_clock_speed()
        if config.swap:
            swap = check_swap()
        if config.memory:
            memory = check_memory()
        if config.uptime:
            uptime_days = check_uptime()
        if config.wifi_signal:
            wifi_signal = check_wifi_signal('')
        if config.wifi_signal_dbm:
            wifi_signal_dbm = check_wifi_signal('dbm')
        if config.rpi5_fan_speed:
            rpi5_fan_speed = check_rpi5_fan_speed()
        if config.git_update:
            git_update = check_git_update()
            
        # Display collected values on screen if --display option is used    
        if args.display:
            print_values()
            
        # Publish messages to MQTT
        if hasattr(config, 'group_messages') and config.group_messages:
            bulk_publish_to_mqtt(cpu_load, cpu_temp, used_space, voltage, sys_clock_speed, swap, memory, uptime_days, wifi_signal, wifi_signal_dbm, rpi5_fan_speed, git_update)
        else:
            publish_to_mqtt(cpu_load, cpu_temp, used_space, voltage, sys_clock_speed, swap, memory, uptime_days, wifi_signal, wifi_signal_dbm, rpi5_fan_speed, git_update)

        # if not running as a service, break the loop after one iteration
        if not args.service:
            break
        # if running as a service, sleep before the next iteration
        time.sleep(config.service_sleep_time)