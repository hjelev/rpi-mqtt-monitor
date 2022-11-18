#!/bin/bash
printm(){
  length=$(expr length "$1")
  length=$(($length + 4))
  printf "\n"
  printf -- '-%.0s' $(seq $length); echo ""
  printf "| $1 |\n"
  printf -- '-%.0s' $(seq $length); echo ""
}

main(){
  if [[ $(git --version)  ]]; then 
    git=$(which git)
  else
    sudo apt-get install git  
  fi

  printm "Cloning rpi-mqtt-monitor git repository"
  git clone https://github.com/hjelev/rpi-mqtt-monitor.git
  cd rpi-mqtt-monitor
  bash install.sh
}

main
