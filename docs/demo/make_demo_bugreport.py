#!/usr/bin/env python3
"""Generate the sample bugreport zip used by the README demo GIF.

Produces docs/demo/bugreport-car-demo.zip — a small, fake, but structurally
faithful `adb bugreport` with one issue of each kind (native crash, Java crash,
ANR, watchdog, SELinux denials, VHAL errors) so `ailog bugreport --no-ai`
shows off the knowledge-pack triage. Re-run after changing the content below:

    python3 docs/demo/make_demo_bugreport.py
"""

import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'bugreport-car-demo.zip')

BUGREPORT = """========================================================
== dumpstate: 2026-07-13 18:20:14
========================================================

Build: UQ1A.240101.002
Build fingerprint: 'oem/car_arm64/car_arm64:14/UQ1A.240101.002/11223344:userdebug/test-keys'
Bootloader: slider-1.2-automotive
Kernel: Linux version 6.1.68-android14-11 (build@build) #1 SMP PREEMPT
Uptime: up 0 weeks, 0 days, 1 hour, 42 minutes

------ SYSTEM LOG (logcat -v threadtime -d *:v) ------

07-13 18:11:02.113  1024  1080 I CarPowerManagementService: Power state changed: WAIT_FOR_VHAL -> ON
07-13 18:11:02.377  1288  1288 I CarService: CarService started, connecting managers
07-13 18:11:04.921  2455  2455 E VehicleHal: get(HVAC_TEMPERATURE_SET, areaId=0x31) returned StatusCode: NOT_AVAILABLE
07-13 18:11:05.002  2455  2455 W CarPropertyService: getProperty failed for property HVAC_TEMPERATURE_SET

--------- beginning of crash
07-13 18:12:11.532  3902  3902 F DEBUG   : *** *** *** *** *** *** *** *** *** *** *** *** *** *** *** ***
07-13 18:12:11.532  3902  3902 F DEBUG   : Build fingerprint: 'oem/car_arm64/car_arm64:14/UQ1A.240101.002/11223344:userdebug/test-keys'
07-13 18:12:11.533  3902  3902 F DEBUG   : signal 6 (SIGABRT), code -1 (SI_QUEUE), fault addr --------
07-13 18:12:11.533  3902  3902 F DEBUG   : Abort message: 'CHECK failed: propConfig.areaConfigs.size() > 0 for property HVAC_TEMPERATURE_SET'
07-13 18:12:11.534  3902  3902 F DEBUG   :     backtrace:
07-13 18:12:11.534  3902  3902 F DEBUG   :       #00 pc 000000000004f8a4  /apex/com.android.runtime/lib64/bionic/libc.so (abort+164)
07-13 18:12:11.534  3902  3902 F DEBUG   :       #01 pc 00000000000129b0  /vendor/bin/hw/android.hardware.automotive.vehicle@2.0-service (VehicleHalManager::get+248)
07-13 18:12:11.534  3902  3902 F DEBUG   :       #02 pc 000000000001b2c4  /vendor/bin/hw/android.hardware.automotive.vehicle@2.0-service

07-13 18:13:40.211  1288  1310 E AndroidRuntime: FATAL EXCEPTION: main
07-13 18:13:40.211  1288  1310 E AndroidRuntime: Process: com.oem.hvac, PID: 5122
07-13 18:13:40.211  1288  1310 E AndroidRuntime: java.lang.IllegalStateException: Car not connected: CarService died during climate update
07-13 18:13:40.211  1288  1310 E AndroidRuntime: 	at android.car.Car.checkCarConnected(Car.java:2101)
07-13 18:13:40.211  1288  1310 E AndroidRuntime: 	at com.oem.hvac.ClimateController.setTemperature(ClimateController.java:88)
07-13 18:13:40.211  1288  1310 E AndroidRuntime: 	at com.oem.hvac.MainActivity.onSliderChange(MainActivity.java:212)

07-13 18:15:22.664  1024  1044 E ActivityManager: ANR in com.oem.telemetry
07-13 18:15:22.664  1024  1044 E ActivityManager: PID: 6240
07-13 18:15:22.664  1024  1044 E ActivityManager: Reason: Input dispatching timed out (Waiting because no window has focus)
07-13 18:15:22.664  1024  1044 E ActivityManager: Load: 12.1 / 8.4 / 5.2
07-13 18:15:22.664  1024  1044 E ActivityManager: CPU usage from 0ms to 9200ms:
07-13 18:15:22.664  1024  1044 E ActivityManager:   48% 6240/com.oem.telemetry: 41% user + 7% kernel

07-13 18:16:03.118  1024  1090 W CarWatchdog: com.oem.telemetry not responding to health check, terminating

------ KERNEL LOG (dmesg) ------

[ 6142.201332] type=1400 audit(1760367482.114:812): avc: denied { read } for comm="vehicle_hal" name="hvac_calib" dev="sda13" ino=1042 scontext=u:r:hal_vehicle_default:s0 tcontext=u:object_r:sysfs:s0 tclass=file permissive=0
[ 6142.201389] type=1400 audit(1760367482.171:813): avc: denied { write } for comm="com.oem.telemetry" name="telemetry.db" dev="sda21" ino=8811 scontext=u:r:untrusted_app:s0 tcontext=u:object_r:system_data_file:s0 tclass=file permissive=0

------ DUMPSYS (dumpsys) ------

DUMP OF SERVICE car_service:
  mCarServiceHelper connected
"""


def main():
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('bugreport-car_arm64-UQ1A.240101.002-2026-07-13-18-20-14.txt', BUGREPORT)
    print(f'wrote {OUT} ({os.path.getsize(OUT)} bytes)')


if __name__ == '__main__':
    main()
