printm () {
  line="------"
  length=$(expr length "$1")
  printf -- '-%.0s' $(seq $length); echo ""
  echo "$1"
  printf -- '-%.0s' $(seq $length); echo ""
}

printm "Cloning rpi-mqtt-monitor git repository"
echo $line
git clone https://github.com/hjelev/rpi-mqtt-monitor.git
cd rpi-mqtt-monitor
bash install.sh
