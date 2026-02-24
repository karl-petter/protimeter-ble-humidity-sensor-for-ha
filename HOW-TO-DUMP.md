
# Capture BLE communication

## Preparations

## Capture

1. Turn on hci
1. Interact with app so BLE communication happens
1. Export dump
    C:\Users\kalle\AppData\Local\Android\Sdk\platform-tools\adb pair 192.168.4.2:34555
    C:\Users\kalle\AppData\Local\Android\Sdk\platform-tools\adb bugreport
1.  mv .\FS\data\log\bt\btsnoop_hci.log* .

# tshark
tshark -r btsnoop-hci-logs/btsnoop_hci-2.log -Y 'btatt && (btatt.opcode==18 || btatt.opcode==82 || btatt.opcode==27 || btatt.opcode==29 || btatt.opcode==10)'   -T fields -e frame.time -e btatt.opcode -e btatt.handle -e btatt.value -E header=no -E separator=, > btsnoop_hci-2.log_output.txt

# Raspberry Pi
The bluetooth device was disabled on my Raspberry Pi 3, needed to run the following commands
sudo rfkill unblock all
sudo hciconfig hci0 up

Scan for the device: sudo hcitool lescan | grep "Protimeter"