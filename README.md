# Rapsberry Pi MQTT monitor
Python 2 script to check cpu load, cpu temperature, free space, voltage and system clock speed
on a Raspberry Pi computer and publish the data to a MQTT server.

I wrote this so I can monitor my raspberries at home with home assistant. The script is writen for python 2
as when I wrote it one of the used python modules was not available for python 3. (if the modules are available for python 3 now the script shuold have no problems running on python 3 - plan to check that in the near feature)
The script if very light, it takes 4 seconds as there are 4 one second sleeps in the code - due to mqtt have problems if I shoot the messages with no delay.

# Installation:

Install these two modules needed for the script

RUN pip install paho-mqtt

RUN sudo apt-get install python-pip

Rename config.py.example to config.py and populate the needed variables

Test the script.

Create a cron entry like this:

*/2 * * * * /usr/bin/python /home/pi/scripts/cpu_mqtt.py
