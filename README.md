# Raspberry Pi MQTT Monitor

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/hjelev/rpi-mqtt-monitor)](https://github.com/hjelev/rpi-mqtt-monitor/releases)
[![GitHub repo size](https://img.shields.io/github/repo-size/hjelev/rpi-mqtt-monitor)](https://github.com/hjelev/rpi-mqtt-monitor)
[![GitHub issues](https://img.shields.io/github/issues/hjelev/rpi-mqtt-monitor)](https://github.com/hjelev/rpi-mqtt-monitor/issues)
[![GitHub closed issues](https://img.shields.io/github/issues-closed/hjelev/rpi-mqtt-monitor)](https://github.com/hjelev/rpi-mqtt-monitor/issues?q=is%3Aissue+is%3Aclosed)
[![GitHub language count](https://img.shields.io/github/languages/count/hjelev/rpi-mqtt-monitor)](https://github.com/hjelev/rpi-mqtt-monitor)
[![GitHub top language](https://img.shields.io/github/languages/top/hjelev/rpi-mqtt-monitor)](https://github.com/hjelev/rpi-mqtt-monitor)

<p align="center">
  <img src="./images/rpi-mqtt-monitor-2-min.png" alt="Raspberry Pi MQTT Monitor" />
</p>

The easiest way to track your Raspberry Pi or Ubuntu computer system health and performance in Home Assistant.

* Start monitoring your system in just a few minutes.
* Monitor: cpu load, cpu temperature, free space, used memory, swap usage, uptime, wifi signal quality, voltage and system clock speed.
* Automatic HASS configuration: Supports discovery messages, so no manual configuration in [Home Assistant](https://www.home-assistant.io/) configuration.yaml is needed.
* Automated installation and configuration: you can install it and schedule it with a service or cron with just one command from shell.
* Configurable: You can select what is monitored and how the message(s) is send (separately or as one csv message)
* Easy update: You can update the script by calling it with command line argument --update


## Table of Contents

- [What is new](#what-is-new)
- [CLI arguments](#cli-arguments)
- [Installation](#installation)
  - [Automated](#automated)
  - [Manual](#manual)
- [Configuration](#configuration)
- [Test Raspberry Pi MQTT Monitor](#test-raspberry-pi-mqtt-monitor)
- [Schedule Raspberry Pi MQTT Monitor execution as a service](#schedule-raspberry-pi-mqtt-monitor-execution-as-a-service)
- [Schedule Raspberry Pi MQTT Monitor execution](#schedule-raspberry-pi-mqtt-monitor-execution)
- [How to update](#how-to-update)
- [Home Assistant Integration](#home-assistant-integration)
- [To Do](#to-do)
- [Feature request](#feature-request)

## What is new

* 2024-10-24: Added rpi_power_status sensor
* 2024-10-19: Added support for drive temperatures
* 2024-03-24: --hass to display configuration for Home Assistant wake on lan switch
* 2024-02-20: Shutdown button added (only works when running as service)
* 2024-02-05: System Restart button added (only works when running as service)
* 2024-01-28: Remote updates via Home Assistant are now available
* 2024-01-28: Improved error handling for the MQTT connection
* 2024-01-28: Script version is displayed in home assistant device information
* 2024-01-28: Update the script by calling it with command line argument --update
* 2024-01-27: Now you can run the script as a service (systemd) or as a cron job
* 2024-01-27: Support for command line arguments
* 2024-01-27: Added a binary sensor for github to monitor for new versions of the script
* 2024-01-27: Updated the sensors names not to include the device name as per home assistant guidelines
* 2024-01-10: Added support for Raspberry Pi 5 fan speed monitoring (only works on Raspberry Pi 5 with stock fan)

## CLI arguments

```
usage: rpi-cpu2mqtt.py [-h] [--display] [--service] [--version] [--update]

options:
  -h, --help     show this help message and exit
  --display, -d  display values on screen
  --service, -s  run script as a service
  --version, -v  display version
  --update,  -u  update script and config
  --hass, -H     display Home assistant wake on lan configuration
```



## Installation

### Automated

Run this command to use the automated installation:

```bash
bash <(curl -s https://raw.githubusercontent.com/hjelev/rpi-mqtt-monitor/master/remote_install.sh)
```

Raspberry Pi MQTT monitor will be installed in the location where the installer is called, inside a folder named rpi-mqtt-monitor.

The auto-installer needs the software below and will install it if its not found:

* python (2 or 3)
* python-pip
* git
* paho-mqtt

Only python is not automatically installed, the rest of the dependencies should be handled by the auto installation.
It will also help you configure the host and credentials for the mqtt server in config.py and create the service or cronjob configuration for you.
It is recommended to run the script as a service, this way you can use the restart, shutdown and display control buttons in Home Assistant.

### Manual

If you don't like the automated installation here are manual installation instructions (missing the creation of virtual environment).

1. Install pip if you don't have it:

```bash
sudo apt install python-pip
```

2. Then install this python module needed for the script:

```bash
pip install paho-mqtt==1.6.1
```

3. Install git if you don't have it:

```bash
apt install git
```

4. Clone the repository:

```bash
git clone https://github.com/hjelev/rpi-mqtt-monitor.git
```

5. Rename ```src/config.py.example``` to ```src/config.py```



## Configuration

(only needed for manual installation)
Populate the variables for MQTT host, user, password and main topic in ```src/config.py```.

You can also choose what messages are sent and what is the delay (sleep_time is only used for multiple messages) between them.
If you are sending a grouped message, and you want to delay the execution of the script you need to use the ```random_delay``` variable which is set to 1 by default.
This is the default configuration (check the example file for more info):

```
random_delay = randrange(1)
discovery_messages = True
group_messages = False
sleep_time = 0.5
service_sleep_time = 120
cpu_load = True
cpu_temp = True
used_space = True
voltage = True
sys_clock_speed = True
swap = True
memory = True
uptime = True
uptime_seconds = False
wifi_signal = False
wifi_signal_dbm = False
rpi5_fan_speed = False
display_control = False
shutdown_button = True
restart_button = True
```

If ```discovery_messages``` is set to true, the script will send MQTT Discovery config messages which allows Home Assistant to automatically add the sensors without having to define them in configuration.  Note, this setting is only available when ```group_messages``` is not used.

If ```group_messages``` is set to true the script will send just one message containing all values in CSV format.
The group message looks like this:

```
1.3, 47.1, 12, 1.2, 600, nan, 14.1, 12, 50, -60
```

## Test Raspberry Pi MQTT Monitor

Run Raspberry Pi MQTT Monitor (this will work only if you used the automated installer or created the shortcut manually)

```bash
rpi-mqtt-monitor -d
```

Once you run Raspberry Pi MQTT monitor you should see something like this:

```
:: rpi-mqtt-monitor
   Version: 0.9.1

:: Device Information
   Model Name:  Intel(R) Pentium(R) Silver J5040 CPU @ 2.00GHz
   Manufacturer:  GenuineIntel
   OS: Ubuntu 23.10
   Hostname: ubuntu-pc
   IP Address: 192.168.0.200
   MAC Address: A8-A1-59-82-57-E7
   Update Check Interval: 3600 seconds

:: Measured values
   CPU Load: 48.5 %
   CPU Temp: 71 °C
   Used Space: 12 %
   Voltage: False V
   CPU Clock Speed: False MHz
   Swap: False %
   Memory: 53 %
   Uptime: 0 days
   Wifi Signal: False %
   Wifi Signal dBm: False
   RPI5 Fan Speed: False RPM
   Update: {"installed_ver": "0.9.1", "new_ver": "0.9.1"}
```
## Schedule Raspberry Pi MQTT Monitor execution as a service

If you want to run Raspberry Pi MQTT Monitor as a service you can use the provided service file.
You need to edit the service file and update the path to the script and the user (if you want to use shutdown or restart buttons user needs to be root) that will run it. 
Then copy the service file to ```/etc/systemd/system/``` and enable it:

```bash
sudo cp rpi-mqtt-monitor.service /etc/systemd/system/
sudo systemctl enable rpi-mqtt-monitor.service
```

To test that the service is working you can run:

```bash
sudo service rpi-mqtt-monitor start
sudo service rpi-mqtt-monitor status
```

## Schedule Raspberry Pi MQTT Monitor execution with a cron

Create a cron entry like this (you might need to update the path in the cron entry below, depending on where you installed it):

```
*/2 * * * * cd /home/pi/rpi-mqtt-monitor; /usr/bin/python /home/pi/rpi-mqtt-monitor/rpi-cpu2mqtt.py
```
## How to update

Remote updates via Home Assistant are now available. 

To use these you need to have the script running as a service. (the installer now supports this)

Manual update:

```bash
cd rpi-mqtt-monitor
python3 src/update.py
```

## Home Assistant Integration

If you are using discovery_messages, then this step is not required as a new MQTT device will be automatically created in Home Assistant and all you need to do is add it to a dashboard.

Use '''python3 src/rpi-cpu2mqtt.py --hass''' to display the configuration for Home Assistant wake on lan switch.

[moved to wiki](../../wiki/Home-Assistant-Integration-(outdated))

## To Do

- maybe add network traffic monitoring via some third party software (for now I can't find a way to do it without additional software)

## Feature request

If you want to suggest a new feature or improvement don't hesitate to open an issue or pull request.
