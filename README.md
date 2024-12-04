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
* Monitor: cpu load, cpu temperature, free space, used memory, swap usage, uptime, wifi signal quality, voltage, rpi power health, rpi5 fan speed, apt updates available on host, external sensors, hdd/ssd temperature and system clock speed.
* Remotely restart / shutdown your system and control your monitors.
* Automatic HASS configuration: Supports discovery messages, so no manual configuration in [Home Assistant](https://www.home-assistant.io/) configuration.yaml is needed.
* Automated installation and configuration: you can install it and schedule it with a service or cron with just one command from shell.
* Configurable: You can select what is monitored and how the message(s) is send (separately or as one csv message).
* Easy update: You can update the script by calling it with command line "rpi-mqtt-monitor --update" or via Home Assistant UI.


## Table of Contents

- [What is new](#what-is-new)
- [CLI arguments](#cli-arguments)
- [Installation](#installation)
  - [Automated](#automated)
  - [Manual](#manual)
- [Configuration](#configuration)
  - [External Sensors](#external-sensors)
- [Test Raspberry Pi MQTT Monitor](#test-raspberry-pi-mqtt-monitor)
- [Schedule Raspberry Pi MQTT Monitor execution as a service](#schedule-raspberry-pi-mqtt-monitor-execution-as-a-service)
- [Schedule Raspberry Pi MQTT Monitor execution](#schedule-raspberry-pi-mqtt-monitor-execution)
- [How to update](#how-to-update)
- [Home Assistant Integration](#home-assistant-integration)
- [To Do](#to-do)
- [Feature request](#feature-request)

## What is new

* 2024-12-01: Support for Home Assistant API (no MQTT needed)
* 2024-11-06: External sensors by @pallago
* 2024-10-25: Apt updates sensor
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
usage: rpi-mqtt-monitor [-h] [-H] [-d] [-s] [-v] [-u] [-w]

Monitor CPU load, temperature, frequency, free space, etc., and publish the data to an MQTT server or Home Assistant API.

options:
  -h, --help       show this help message and exit
  -H, --hass_api   send readings via Home Assistant API (not via MQTT)
  -d, --display    display values on screen
  -s, --service    run script as a service, sleep interval is configurable in config.py
  -v, --version    display installed version and exit
  -u, --update     update script and config then exit
  -w, --hass_wake  display Home assistant wake on lan configuration

```


## Installation

### Automated

Run this command to use the automated installation:

```bash
bash <(curl -s https://raw.githubusercontent.com/hjelev/rpi-mqtt-monitor/master/remote_install.sh)
```

Raspberry Pi MQTT monitor will be installed in the location where the installer is called, inside a folder named rpi-mqtt-monitor.

The auto-installer needs the software below and will install it if its not found:

* git
* python (2 or 3)
* python-pip
* paho-mqtt (python module)
* requests (python module)

Only python is not automatically installed, the rest of the dependencies should be handled by the auto installation.
It will also help you configure the host and credentials for the mqtt server in config.py and create the service or cronjob configuration for you.
It is recommended to run the script as a service, this way you can use the restart, shutdown and display control buttons in Home Assistant.

### Manual
[moved to wiki](../../wiki/Manual-Installation)

## Home Assistant Integration

If you are using discovery_messages, then this step is not required as a new MQTT device will be automatically created in Home Assistant and all you need to do is add it to a dashboard.

Use '''rpi-mqtt-monitor --hass_wake''' to display the configuration for Home Assistant wake on lan switch.

[moved to wiki](../../wiki/Home-Assistant-Integration-(outdated))

## To Do

- fix uptime sensor to use timestamp
- improve hass api integration

## Feature request

If you want to suggest a new feature or improvement don't hesitate to open an issue or pull request.
