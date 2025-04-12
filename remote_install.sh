#!/bin/bash
# Description: Remote Installation script for rpi-mqtt-monitor

printm(){
  length=$(expr length "$1")
  length=$(($length + 4))
  printf "\n"
  printf -- '-%.0s' $(seq $length); echo ""
  printf "| $1 |\n"
  printf -- '-%.0s' $(seq $length); echo ""
}

welcome(){
  printm "Raspberry Pi MQTT Monitor installer"
  echo "Welcome to the Raspberry Pi MQTT Monitor installer."
  echo "This script will install necessary components, configure the monitor and set up a cron job or service."
  read -r -p "Ready to proceed? [y/N] " response
  if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    printf ""
  else
    exit
  fi	
}

uninstall(){
  printm "Uninstalling rpi-mqtt-monitor"

  # Ask for confirmation before proceeding
  read -r -p "Are you sure you want to uninstall rpi-mqtt-monitor? [y/N] " response
  if [[ ! "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Uninstallation canceled."
    exit
  fi
    
  # Get the absolute path of the script
  script_dir=$(dirname "$(realpath "$0")")

  # Remove the rpi-mqtt-monitor directory if it exists
  if [ -d "$script_dir" ]; then
    if [ "$(realpath rpi-mqtt-monitor)" == "$script_dir" ]; then
      # If the script is running from the installation directory, navigate out of it
      cd ..
    fi
    sudo rm -rf "$script_dir"
    echo "Removed rpi-mqtt-monitor directory."
  else
    echo "rpi-mqtt-monitor directory not found."
  fi
  
  # Remove the cron job if it exists
  if crontab -l | grep -q rpi-cpu2mqtt.py; then
    crontab -l | grep -v rpi-cpu2mqtt.py | crontab -
    echo "Removed cron job for rpi-cpu2mqtt.py."
  else
    echo "No cron job found for rpi-cpu2mqtt.py."
  fi

  # Remove the systemd service if it exists
  if [ -f /etc/systemd/system/rpi-mqtt-monitor.service ]; then
    sudo systemctl stop rpi-mqtt-monitor.service
    sudo systemctl disable rpi-mqtt-monitor.service
    sudo rm /etc/systemd/system/rpi-mqtt-monitor.service
    sudo systemctl daemon-reload
    echo "Removed systemd service for rpi-mqtt-monitor."
  else
    echo "No systemd service found for rpi-mqtt-monitor."
  fi

  # Optionally remove git if it was installed by this script
  if command -v git &> /dev/null; then
    read -r -p "Do you want to remove git? [y/N] " response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
      sudo apt-get remove --purge git
      echo "Git has been removed."
    fi
  fi
}

main(){
  welcome
  if [[ $(git --version)  ]]; then 
    git=$(which git)
  else
    sudo apt-get install git  
  fi

  printm "Cloning rpi-mqtt-monitor git repository"
  git clone https://github.com/hjelev/rpi-mqtt-monitor.git
  cd rpi-mqtt-monitor
  git pull
  bash install.sh
}

# Check for uninstall flag
if [[ "$1" == "uninstall" ]]; then
  uninstall
else
  main
fi
