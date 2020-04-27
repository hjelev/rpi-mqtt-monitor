# Rapsberry Pi MQTT monitor
Python 2 script to check cpu load, cpu temperature and free space,
on a Raspberry Pi computer and publish the data to a MQTT server.

# Installation:
Install these two modules needed for the script

RUN pip install paho-mqtt

RUN sudo apt-get install python-pip

Rename config.py.example to config.py and populate the needed variables

Test the script.

Create a cron entry like this:

*/2 * * * * /usr/bin/python /home/pi/scripts/cpu_mqtt.py
