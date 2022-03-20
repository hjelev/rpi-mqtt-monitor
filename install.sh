printm(){
  length=$(expr length "$1")
  length=$(($length + 4))
  printf "\n"
  printf -- '-%.0s' $(seq $length); echo ""
  printf "| $1 |\n"
  printf -- '-%.0s' $(seq $length); echo ""
}

find_python(){
if $(python --version); then 
	python=$(which python)
	pip="python-pip"
else
	python=$(which python3)
	pip="python3-pip"
fi
echo "$python"
}

print_green(){
  tput setaf 2; echo "$1"
  tput sgr 0
}

print_yellow(){
  tput setaf 3; printf "$1"
  tput sgr 0
}

check_and_install_pip(){
  cwd=$(pwd)
  #python=$(which python)
  pip=$(${python} -m pip --version 2>&1);
  if [[ "$pip" == *"No"* ]]; then
    echo "- Pip is not installed, installing it."
    sudo apt install $python-pip
    else
    print_green "+ Found $pip"
  fi
}

install_requirements(){
  printm "Installing requirements"
  pip install -r requirements.txt
}

update_config(){
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

set_cron(){
  printm "Setting Cronjob"

  crontab -l > tempcron
  if grep -q rpi-cpu2mqtt.py tempcron; then
    cronfound=$(grep rpi-cpu2mqtt.py tempcron)
    print_yellow " There is already a cronjob running rpi-cpu2mqtt.py - skipping cronjob creation\n"
    print_yellow " If you want the cronjob to be automatically created remove the line below from your\n cronjobs list and run the installer again.\n\n"
    echo " ${cronfound}"
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

main(){
  printm "Raspberry Pi MQTT monitor installer"
  find_python
  check_and_install_pip
  install_requirements 
  update_config
  set_cron
  printm "Done"
}

main
