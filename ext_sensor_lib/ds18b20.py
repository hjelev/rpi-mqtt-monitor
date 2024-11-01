#!/usr/bin/python3
import time
import os
"""
This reads the temp value of a DS18B20 sensor
"""


def sensor_DS18B20(sensor_id, verbose=False):
    """
    :param sensor_id: Name of the sensor id, can be found in /sys/bus/w1/devices
    :type sensor_id: string
    """
    # read the file
    try:
        file = open('/sys/bus/w1/devices/28-%s/w1_slave' % sensor_id)
        filecontent = file.read()
        file.close()
        # read temperature value and convert it
        stringvalue = filecontent.split("\n")[1].split(" ")[9]
        temperature = float(stringvalue[2:]) / 1000
    except IOError as e:
        # if an error occurs, we return -300
        temperature = float(-300)

    # format the temperature
    temp = '%6.1f' % temperature
    temp = round(temperature, 1)
    # if we set the verbose, we print the current temperature
    if verbose:
        print ("1-wire %s: temp=%.1f" % (sensor_id, temp))
    return temp


def get_available_sensors():
    """Returns all available sensors"""
    # https://github.com/rgbkrk/ds18b20/blob/master/ds18b20/__init__.py
    sensors = []
    for sensor in os.listdir("/sys/bus/w1/devices"):
        if sensor.startswith("28-"):
            # we put all sensor ids into the list (except the "28-" part)
            sensors.append(sensor[3:])
    return sensors


if __name__ == "__main__":
    try:
        # call the function to get all sensor_ids as a list
        sensors_ids = get_available_sensors()
        while True:
            for sensor_id in sensors_ids:
                sensor_DS18B20(sensor_id=sensor_id, verbose=True)
                #sensor_DS18B20("0014531448ff")
            time.sleep(2)
    except IOError as e:
        errno, strerror = e.args
        print("I/O error({0}): {1}".format(errno,strerror))
    except KeyboardInterrupt:
        print ("keyboard interrupt")


