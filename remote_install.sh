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

main
