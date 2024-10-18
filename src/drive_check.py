import glob
import os

def get_hwmon_device_name(hwmon_path):
    try:
        with open(os.path.join(hwmon_path, 'name'), 'r') as f:
            return f.read().strip()
    except Exception as e:
        print(f"Error reading name for {hwmon_path}: {e}")
        return None

def get_hwmon_temp(hwmon_path):
    try:
        temp_files = glob.glob(os.path.join(hwmon_path, 'temp*_input'))
        for temp_file in temp_files:
            with open(temp_file, 'r') as tf:
                temp = int(tf.read().strip()) / 1000.0
                return temp
    except Exception as e:
        print(f"Error reading temperature for {hwmon_path}: {e}")
        return None

def check_all_drive_temps():
    drive_temps = {}
    hwmon_devices = glob.glob('/sys/class/hwmon/hwmon*')
    for hwmon in hwmon_devices:
        device_name = get_hwmon_device_name(hwmon)
        if device_name and any(keyword in device_name.lower() for keyword in ['nvme', 'sd']):
            temp = get_hwmon_temp(hwmon)
            if temp is not None:
                drive_temps[device_name] = temp
    return drive_temps

if __name__ == '__main__':
    drive_temps = check_all_drive_temps()
    for device, temp in drive_temps.items():
        print(f"{device} Temperature: {temp:.2f}°C")