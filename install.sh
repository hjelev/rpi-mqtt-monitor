printm () {
  line="------"
  length=$(expr length "$1")
  printf -- '-%.0s' $(seq $length); echo ""
  echo "$1"
  printf -- '-%.0s' $(seq $length); echo ""
}

printm "Raspberry Pi MQTT monitor installer"

check_and_install_pip () {
	cwd=$(pwd)
	python=$(which python)
	pip=$(python -m pip --version 2>&1);
	if [[ "$pip" == *"No"* ]]; then
		echo "- Pip is not installed, installing it."
		sudo apt install python-pip
		else

		tput setaf 2; echo "+ Found $pip"
		tput sgr 0
	fi
}

check_and_install_paho () {
	pip=$(pip list | grep "paho-mqtt");
	if [[ "$pip" == *"paho-mqtt"* ]]; then
		echo "+ Found $pip"

	else
		echo "- Paho-mqtt is not installed, installing it."
		pip install paho-mqtt
	fi
}

update_config () {
	printf "\nCopy config.py.example to config.py\n"

	cp src/config.py.example src/config.py

	printm "MQTT settings"


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

	printf "\nconfig.py is updated with provided settings\n"
}

set_cron () {
	printm "Setting Cronjob"

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
}

main () {
	check_and_install_pip
	check_and_install_paho 
	update_config
	set_cron
	printm "Done"
}
main
