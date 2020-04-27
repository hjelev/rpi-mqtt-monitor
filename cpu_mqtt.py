# Python 2 script to check cpu load, cpu temperature and free space,
# on a Raspberry Pi computer and publish the data to a MQTT server.
# RUN pip install paho-mqtt
# RUN sudo apt-get install python-pip

from __future__ import division
import subprocess, time, socket, os
import paho.mqtt.client as paho

#get device host name - used in mqtt topic
hostname = socket.gethostname()

#mqtt server configuration
mqtt_host = "192.168.0.13"
mqtt_user = "homeassistant"
mqtt_password = "xyMaSokO123"
mqtt_port = "1883"
mqtt_topic_prefix = "masoko"

def check_used_space(path):
        st = os.statvfs(path)
        free_space = st.f_bavail * st.f_frsize
        total_space = st.f_blocks * st.f_frsize
        used_space = int(100 - ((free_space / total_space) * 100))
        return used_space

def check_cpu_load():
        #bash command to get cpu load from uptime command
        p = subprocess.Popen("uptime", shell=True, stdout=subprocess.PIPE).communicate()[0]
        cpu_load = p.split("average:")[1].split(",")[0].replace(' ', '')
        return cpu_load

def check_cpu_temp():
        #bash command to get rpi cpu temp
        full_cmd = "/opt/vc/bin/vcgencmd measure_temp"
        p = subprocess.Popen(full_cmd, shell=True, stdout=subprocess.PIPE).communicate()[0]
        cpu_temp = p.replace('\n', ' ').replace('\r', '').split("=")[1].split("'")[0]
        return cpu_temp

def publish_to_mqtt (cpu_load, cpu_temp, used_space):
        #connect to mqtt server
        client = paho.Client()
        client.username_pw_set(mqtt_user, mqtt_password)
        client.connect(mqtt_host, mqtt_port)

        #publish cpu load mqtt message
        client.publish(mqtt_topic_prefix+"/"+hostname+"/cpuload", cpu_load, qos=1)
        time.sleep(1)

        #publish cpu temperature mqtt message
        client.publish(mqtt_topic_prefix+"/"+hostname+"/cputemp", cpu_temp, qos=1)
        time.sleep(1)

        #publish used space mqtt message
        client.publish(mqtt_topic_prefix+"/"+hostname+"/diskusage", used_space, qos=1)

        #disconect from mqtt server
        client.disconnect()

if __name__ == '__main__':
        #check cpu load
        cpu_load = check_cpu_load()
        #check cpu temp
        cpu_temp = check_cpu_temp()
        #check used space
        used_space = check_used_space('/')
        #Publish messages
        publish_to_mqtt(cpu_load, cpu_temp, used_space)
