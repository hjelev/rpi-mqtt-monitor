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
  printm "Cloning rpi-mqtt-monitor git repository"
  git clone https://github.com/hjelev/rpi-mqtt-monitor.git
  cd rpi-mqtt-monitor
  bash install.sh
}
main
