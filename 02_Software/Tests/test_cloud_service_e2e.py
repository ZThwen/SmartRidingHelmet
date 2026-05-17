"""
brief CloudService 端到端测试（真机 + 真实联网）
note 插卡，跑真实传感器 + 4G + MQTT 到 ConnectLab
      验证完整链路：传感器采集 → CloudService 拼装 → MQTT 上传
执行: 上传到板子运行 python test_cloud_service_e2e.py
"""
import sys
sys.path.append("..")
import time

from core.Event_Bus import EventBus
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_IMU_READY, EVENT_LIGHT_READY,
    EVENT_DATA_UPLOAD_SUCCESS, EVENT_DATA_UPLOAD_FAILED,
    EVENT_NETWORK_CONNECTED,
)
from Drivers.sensor.Temp_Humid import TempHumidDriver
from Drivers.sensor.imu import IMUDriver
from Drivers.sensor.Light import LightSensorDiver
from Modules.cloud_service import CloudService


# ==================== 测试全局状态 ====================
upload_count = 0
upload_fail_count = 0
network_ready = False
last_temp = None
last_humid = None
last_light = None
tick_counts = {}


def on_upload_success(payload):
    global upload_count
    upload_count += 1


def on_upload_failed(payload):
    global upload_fail_count
    upload_fail_count += 1


def on_network_connected(payload):
    global network_ready
    network_ready = True


def main():
    global upload_count, upload_fail_count, network_ready
    global last_temp, last_humid, last_light, tick_counts

    print("\n=== CloudService E2E Test (30s) ===")
    print("Ensure SIM card inserted and antenna connected.\n")

    # ====== 1. 创建 EventBus ======
    event_bus = EventBus()

    # ====== 2. 订阅统计事件 ======
    event_bus.subscribe(EVENT_DATA_UPLOAD_SUCCESS, on_upload_success)
    event_bus.subscribe(EVENT_DATA_UPLOAD_FAILED, on_upload_failed)
    event_bus.subscribe(EVENT_NETWORK_CONNECTED, on_network_connected)

    # 订阅传感器事件（记录最新值）
    def on_temp_humid(p):
        global last_temp, last_humid
        if p.get("valid"):
            last_temp = p["temp"]
            last_humid = p["humid"]

    def on_light(p):
        global last_light
        if p.get("valid"):
            last_light = p["light_intensity"]

    event_bus.subscribe(EVENT_TEMP_HUMID_READY, on_temp_humid)
    event_bus.subscribe(EVENT_LIGHT_READY, on_light)

    # ====== 3. 创建模块实例 ======
    temp_humid = TempHumidDriver(event_bus)
    imu = IMUDriver(event_bus)
    light = LightSensorDiver(event_bus)
    cloud = CloudService(event_bus)

    modules = [temp_humid, imu, light, cloud]

    # ====== 4. 初始化所有模块 ======
    print("[init] Initializing all modules...")
    for mod in modules:
        try:
            mod.init()
            print("  OK  %s" % mod.name)
        except Exception as e:
            print("  FAIL %s: %s" % (mod.name, e))
            print("  ABORT: module init failure")
            return

    print("")

    # ====== 5. 主循环 90 秒 ======
    start = time.ticks_ms()
    duration_ms = 30000
    last_report = 0

    while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
        # 调度所有模块
        for mod in modules:
            try:
                mod.tick()
                name = mod.name
                tick_counts[name] = tick_counts.get(name, 0) + 1
            except Exception as e:
                print("[tick err] %s: %s" % (mod.name, e))

        # 事件泵
        event_bus.pump()

        # 每 10 秒打印状态
        now = time.ticks_ms()
        elapsed_s = time.ticks_diff(now, start) // 1000
        if elapsed_s // 10 > last_report:
            last_report = elapsed_s // 10
            queue_size = cloud.send_queue.size() if cloud.send_queue else -1
            print("[%3ds] net:%s mqtt:%s up:%d fail:%d queue:%d"
                  % (elapsed_s,
                     "Y" if network_ready else "N",
                     "Y" if cloud.ctx.get("is_mqtt_ready") else "N",
                     upload_count, upload_fail_count, queue_size))

        time.sleep_ms(10)

    # ====== 6. 停止网络线程 ======
    cloud.ctx["thread_running"] = False

    # ====== 7. 打印最终报告 ======
    print("\n========== E2E Test Results ==========")
    print("Duration: 30s")
    print("")

    tick_str = ", ".join(["%s: %d" % (k, v) for k, v in tick_counts.items()])
    print("Tick counts: %s" % tick_str)
    print("")

    print("Sensor values:")
    print("  Temp:         %s" % ("%s C" % last_temp if last_temp is not None else "N/A"))
    print("  Humid:        %s" % ("%s %%" % last_humid if last_humid is not None else "N/A"))
    print("  Light:        %s" % ("%d" % last_light if last_light is not None else "N/A"))
    print("  GNSS:         N/A (indoor test)")
    print("")

    print("Network:")
    print("  Connected:    %s" % ("YES" if network_ready else "NO"))
    print("  MQTT ready:   %s" % ("YES" if cloud.ctx.get("is_mqtt_ready") else "NO"))
    print("")

    print("Upload:")
    print("  Success:      %d" % upload_count)
    print("  Failed:       %d" % upload_fail_count)
    print("  Queue size:   %d" % (cloud.send_queue.size() if cloud.send_queue else -1))
    print("")

    if upload_count > 0:
        print("RESULT: PASS (data uploaded to ConnectLab)")
    elif network_ready:
        print("RESULT: PARTIAL (network OK but no uploads - check MQTT config)")
    else:
        print("RESULT: FAIL (no network connection - check SIM card)")

    print("")
    print("Login ConnectLab and verify helmet/data topic received JSON data.")
    print("========================================")


if __name__ == "__main__":
    main()
