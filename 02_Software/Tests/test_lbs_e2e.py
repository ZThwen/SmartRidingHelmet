"""
brief LBS基站定位 端到端测试
note 需要真实硬件（EC200U + SIM卡 + 网络注册）
     1. 初始化 LBSDriver
     2. 执行定位
     3. 验证返回坐标
执行: 上传到板子运行 python test_lbs_e2e.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_LBS_READY
from Drivers.sensor.LBS import LBSDriver


_T0 = 0

def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    print("[%7.2fs] %s" % (elapsed / 1000.0, msg))


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" LBS 基站定位 端到端测试")
    print("=" * 50)

    bus = EventBus()
    bus.debug = True

    # 1. 初始化
    log("初始化 LBSDriver...")
    try:
        drv = LBSDriver(bus)
        drv.init()
        log("✓ LBSDriver 就绪")
    except Exception as e:
        log("✗ 初始化失败: %s" % e)
        return

    # 2. 监听事件
    results = []
    def on_lbs(data):
        results.append(data)
        log("✓ EVENT_LBS_READY: lat=%.4f lon=%.4f acc=%.0fm" % (
            data["latitude"], data["longitude"], data.get("accuracy", 0)))
    bus.subscribe(EVENT_LBS_READY, on_lbs)

    # 3. 执行定位
    log("开始定位（超时 15 秒）...")
    drv._do_positioning()
    bus.pump()

    # 4. 检查结果
    if results:
        log("✓ 定位成功")
        log("  纬度: %.4f" % results[0]["latitude"])
        log("  经度: %.4f" % results[0]["longitude"])
        log("  精度: %.0f m" % results[0].get("accuracy", 0))
    else:
        log("✗ 定位失败")
        log("  可能原因: 无 SIM 卡 / 未注册网络 / 信号太弱")

    # 5. 多次定位测试
    log("")
    log("=== 多次定位测试（3 次）===")
    for i in range(3):
        log("第 %d 次定位..." % (i + 1))
        drv._do_positioning()
        bus.pump()
        d = drv.get_data()
        if d["valid"]:
            log("  ✓ %.4f, %.4f (精度: %.0fm)" % (d["latitude"], d["longitude"], d.get("accuracy", 0)))
        else:
            log("  ✗ 失败")
        time.sleep(2)

    # 6. 清理
    drv.deinit()
    log("")
    print("=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
