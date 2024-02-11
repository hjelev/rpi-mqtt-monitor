welcome(){
  echo "  This script will install if not installed: python-pip and python module paho-mqtt,"
  echo "  configure Raspberry Pi MQTT monitor and create a cronjob to run it."
  read -r -p "  Do you want to proceed? [y/N] " response
  if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    printf ""
  else
    exit
  fi	
}

find_python(){
  if [[ $(python3 --version)  ]]; then 
    python=$(which python3)
    pip="python3-pip"
    pip_run='pip3'
  else
    python=$(which python)
    pip="python-pip"
    pip_run='pip'
  fi

  if [[ "$python" == *"python"* ]]; then
    print_green "+ Found: $python"

  else
    print_yellow "Python not found!\n Exiting\n"
    exit
  fi
}

printm(){
  length=$(expr length "$1")
  length=$(($length + 4))
  printf "\n"
  printf ":: $1 \n\n"
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

  pip_ver=$(${python} -m pip --version 2>&1);
  if [[ "$pip_ver" == *"No"* ]]; then
    echo "- Pip is not installed, installing it."
    sudo apt install $pip
    else
    print_green "+ Found: $pip"
  fi
}

create_venv(){
  printm "Creating virtual environment"
  # Check if python3-venv is installed
  if ! dpkg -l | grep -q python3-venv; then
    echo "python3-venv is not installed. Installing..."
    sudo apt-get install -y python3-venv
    else
    print_green "+ Found: python3-venv"
  fi

  # Create a virtual environment
  ${python} -m venv rpi_mon_env
  print_green "+ Virtual environment created"

  # Activate the virtual environment
  source rpi_mon_env/bin/activate
  if [[ $(python3 --version)  ]]; then 
    python=$(which python3)
  else
    python=$(which python)
  fi
  print_green "+ Activated virtual environment"
}

install_requirements(){
  printm "Installing requirements"
  $pip_run install -r requirements.txt
  # Deactivate the virtual environment
  print_green "+ Requirements installed"
  print_green "+ Deactivating virtual environment"
  deactivate
}

update_config(){
  print_green "+ Copy config.py.example to config.py"
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

  print_green  "+ config.py is updated with provided settings"

  # Get the local version
  local_version=$(git describe --tags)
  # Update the version in config.py
  sed -i "s/version = .*/version = '${local_version}'/" src/config.py

}

set_cron(){
  printm "Setting Cronjob"
  cwd=$(pwd)
  crontab -l > tempcron
  if grep -q rpi-cpu2mqtt.py tempcron; then
    cronfound=$(grep rpi-cpu2mqtt.py tempcron)
    print_yellow " There is already a cronjob running rpi-cpu2mqtt.py - skipping cronjob creation.\n"
    print_yellow " If you want the cronjob to be automatically created remove the line below from your\n cronjobs list and run the installer again.\n\n"
    echo " ${cronfound}"
  else
    printf "How often do you want the script to run in minutes? (default is 2): "
    read MIN
    if [ -z "$MIN" ]; then
      MIN=2
    fi
    echo "Adding the line below to your crontab"
    echo "*/${MIN} * * * * cd ${cwd}; ${python} ${cwd}/src/rpi-cpu2mqtt.py"
    echo "*/${MIN} * * * * cd ${cwd}; ${python} ${cwd}/src/rpi-cpu2mqtt.py" >> tempcron
    crontab tempcron
  fi
  rm tempcron
}

set_service(){
  printm "Setting systemd service"
  printf "How often do you want the script to run in seconds? (default is 120): "
  read MIN
  if [ -z "$MIN" ]; then
    MIN=120
  fi
  sed -i "s/120/${MIN}/" src/config.py
  cwd=$(pwd)
  user=$(whoami)
  exec_start="${python} ${cwd}/src/rpi-cpu2mqtt.py --service"
  if [ -f /etc/systemd/system/rpi-mqtt-monitor.service ]; then
    read -p "Service file already exists. Do you want to remove it? (y/n) " yn
    case $yn in
        [Yy]* ) sudo rm /etc/systemd/system/rpi-mqtt-monitor.service;;
        [Nn]* ) return;;
        * ) echo "Please answer y for yes or n for no.";;
    esac
  fi
  print_green "+ Copy rpi-mqtt-monitor.service to /etc/systemd/system/"
  sudo cp ${cwd}/rpi-mqtt-monitor.service /etc/systemd/system/
  sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=${cwd}|" /etc/systemd/system/rpi-mqtt-monitor.service
  sudo sed -i "s|User=YOUR_USER|User=root|" /etc/systemd/system/rpi-mqtt-monitor.service
  sudo sed -i "s|ExecStart=.*|ExecStart=${exec_start}|" /etc/systemd/system/rpi-mqtt-monitor.service
  home_dir=$(eval echo ~$user)
  sudo sed -i "s|Environment=\"HOME=/home/username\"|Environment=\"HOME=${home_dir}\"|" /etc/systemd/system/rpi-mqtt-monitor.service
  sudo systemctl daemon-reload
  sudo systemctl enable rpi-mqtt-monitor.service
  sudo systemctl start rpi-mqtt-monitor.service
  sudo service rpi-mqtt-monitor status
  print_green "+ Service is enabled and started"

}

main(){
  printm "Raspberry Pi MQTT Monitor installer"
  welcome
  find_python
  check_and_install_pip
  create_venv
  install_requirements 
  update_config
  
  while true; do
    read -p "Do you want to set up a (c)ron job or a (s)ervice? " cs
    case $cs in
        [Cc]* ) set_cron; break;;
        [Ss]* ) set_service; break;;
        * ) echo "Please answer c for cron or s for service.";;
    esac
  done
  
  printm "Installation is complete."
}

main
