line="------"
echo $line
echo "Raspberry Pi MQTT monitor installer"
echo $line

echo "Cloning git repository"
echo $line
git clone https://github.com/hjelev/rpi-mqtt-monitor.git
cd rpi-mqtt-monitor

echo "MQTT settings"
echo $line
cwd=$(pwd)
python=$(which python)

cp src/config.py.example src/config.py
printf "Enter mqtt_host: "
read HOST
sed -i "s/ip address or host/${HOST}/" src/config.py

printf "Enter mqtt_user: "
read USER
sed -i "s/username/${USER}/" src/config.py

printf "Enter mqtt_password: "
read PASS
sed -i "s/\"password/\"${PASS}/" src/config.py

printf "Enter mqtt_port (default is 1883): "
read PORT
if [ -z "$PORT" ]; then
	PORT=1883
fi
sed -i "s/1883/${PORT}/" src/config.py

printf "Enter mqtt_topic_prefix (default is rpi-MQTT-monitor): "
read TOPIC
if [ -z "$TOPIC" ]; then
	TOPIC=rpi-MQTT-monitor
fi
sed -i "s/rpi-MQTT-monitor/${TOPIC}/" src/config.py


echo $line
echo "Setting Cronjob"
echo $line
crontab -l > tempcron
if grep -q rpi-cpu2mqtt.py tempcron; then
	cronfound=$(grep rpi-cpu2mqtt.py tempcron)
	echo " There is already a cronjob running rpi-cpu2mqtt.py - skipping cronjob creation"
	printf " If you want the cronjob to be automatically created remove the line below from your\n cronjobs list and run the installer again.\n"
	echo "${cronfound}"
else

	printf "How often do you want the script to run in minutes? "
	read MIN
	echo "Adding the line below to your crontab"
	echo "*/${MIN} * * * * ${python} ${cwd}/src/rpi-cpu2mqtt.py"
	echo "*/${MIN} * * * * ${python} ${cwd}/src/rpi-cpu2mqtt.py" >> tempcron
	crontab tempcron
fi

rm tempcron
echo $line
echo "Done"
