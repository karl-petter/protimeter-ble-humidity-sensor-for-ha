# Reverse Engineering the Protimeter BLE Protocol

This document describes how the BLE protocol was discovered and verified.
The full decoded protocol is in [PROTOCOL.md](PROTOCOL.md).

---

## Overview

The Protimeter BLE humidity sensor communicates over standard BLE GATT.
The official Android app (`ProtimeterBLE.apk`) is a Xamarin/.NET application —
the actual parsing logic lives in a compiled .NET DLL (`ProtimeterApp.dll`)
inside the APK, not in the Java layer. Decompiling that DLL gave exact formulas
and lookup tables.

---

## Step 1 — HCI log capture

Android developer mode includes a Bluetooth HCI snoop log that records all
BLE traffic at the radio level.

1. Enable **Developer options** on the phone
2. Enable **Bluetooth HCI snoop log** in Developer options
3. Open the Protimeter app and perform all actions to capture (connect, read
   current values, export full history)
4. Pull the log via ADB:

```
# Pair ADB over WiFi first if needed:
adb pair <phone-ip>:<port>

# Pull the bugreport (contains the HCI log):
adb bugreport

# Extract the log from the bugreport zip:
# Path inside zip: FS/data/log/bt/btsnoop_hci.log
```

---

## Step 2 — tshark analysis

Filter GATT write and notification packets to isolate commands and responses:

```bash
tshark -r btsnoop_hci.log \
  -Y 'btatt && (btatt.opcode==18 || btatt.opcode==82 || btatt.opcode==27 || btatt.opcode==29 || btatt.opcode==10)' \
  -T fields \
  -e frame.time -e btatt.opcode -e btatt.handle -e btatt.value \
  -E header=no -E separator=, \
  > output.txt
```

GATT opcode reference:

| Opcode | Description |
| --- | --- |
| 10 (0x0A) | Read Request |
| 18 (0x12) | Write Request (with response) |
| 27 (0x1B) | Handle Value Notification |
| 29 (0x1D) | Handle Value Indication |
| 82 (0x52) | Write Command (without response) |

Cross-referencing write payloads with values visible on-screen in the app
identified the command codes (`S`, `R`, `C`, `O`) and response formats.

---

## Step 3 — APK decompilation

The APK is a standard ZIP. Extract `ProtimeterApp.dll` from inside it:

```bash
unzip ProtimeterBLE.apk -d apk_extracted
# DLL is at: apk_extracted/assemblies/ProtimeterApp.dll
```

Decompile to CIL (Common Intermediate Language) bytecode using Mono's `monodis`:

```bash
monodis --output=ProtimeterApp.il ProtimeterApp.dll
```

`jadx` can decompile the Java/Kotlin layer but the Xamarin boilerplate it produces
is not useful — all protocol logic is in the .NET DLL.

---

## Step 4 — Extracting formulas from IL

Key classes in `ProtimeterApp.dll`:

| Class | Contents |
| --- | --- |
| `ProtimeterApp.Bluetooth.ServiceIds` | GATT service UUIDs |
| `ProtimeterApp.Bluetooth.CharacteristicIds` | Characteristic UUIDs |
| `ProtimeterApp.Bluetooth.CommandCodes` | ASCII command bytes |
| `ProtimeterApp.Helpers.ByteHelper` | All parsing formulas and lookup tables |
| `ProtimeterApp.Services.BluetoothService` | BLE connection and command flow |

`ByteHelper` contains:
- `GetHumidityFromLowHighBytes` — humidity decoding
- `GetTemperatureFromLowHighBytes` — temperature decoding
- `GetWmeAdcValue` — raw int → ADC scale
- `GetRawWmeFromAdc` — ADC → raw WME via `AdcTable`
- `GetTemperatureCompensatedWmeValue` — temperature compensation
- `GetCalibratedWme` — calibration interpolation using O-command data and `NominalCalibrationConstants`
- `GetVoltageCompensatedWme` — battery voltage correction using `BatteryLevelTable`

The static constructor (`.cctor`) initialises `AdcTable` and `BatteryLevelTable`
with all their literal values — these are transcribed verbatim into `parser.py`.

---

## Verification

All formulas were verified against:

1. Raw bytes from the HCI log, cross-referenced with values shown on screen in
   the app (humidity, temperature)
2. Live HA debug log output compared against the official app's display values
   after deploying the integration (WME confirmed to 0.1 % accuracy for both
   sensors)

Real device bytes used as unit test inputs are in `tests/test_parser.py`.
