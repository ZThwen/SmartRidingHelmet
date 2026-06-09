"""
brief 导航 TTS 播报测试
note 验证导航指令触发 TTS 播报：
     板子收到 nav 命令 → play_tts() 被调用
     中文路名正确播报
     到达目的地播报
执行: 上传到板子运行
"""
import sys
sys.path.append("../../..")
import time
import json

from core.Event_Bus import EventBus
from core.config import EVENT_NAV_CMD
from Drivers.network.BLE import BLEDriver
from Modules.ble_service import BLEService
from Modules.navigation_service import NavigationService
from Drivers.actuator.Audio import AudioDriver


_LOG_PATH = "Tests/miniprogram/step_b/04_navigation_mode/test_nav_tts.log"
_T0 = 0


def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    line = "[%7.2fs] %s" % (elapsed / 1000.0, msg)
    print(line)
    try:
        with open(_LOG_PATH, "a") as f:
            f.write(line + "\n")
    except:
        pass


def countdown(sec, msg):
    log("⏱ 倒计时: %ds — %s" % (sec, msg))
    for i in range(sec, 0, -1):
        log("  %ds..." % i)
        time.sleep(1)


def wait_ble(bus, ble_svc, timeout_s=20):
    log("▶ 等待 BLE 连接...")
    end = time.ticks_ms() + timeout_s * 1000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        bus.pump()
        if ble_svc.ctx.get("ble_connected"):
            return True
        time.sleep_ms(100)
    return False


def pump_for(bus, ble_svc, duration_ms):
    end = time.ticks_ms() + duration_ms
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" 导航 TTS 播报测试")
    print("=" * 50)

    bus = EventBus()

    log("初始化 Audio...")
    try:
        audio = AudioDriver(bus)
        audio.init()
        log("✓ Audio 就绪")
    except Exception as e:
        log("✗ Audio 失败: %s" % e)
        return

    log("初始化 BLE...")
    try:
        ble_driver = BLEDriver(bus)
        ble_driver.init()
        ble_svc = BLEService(bus, ble_driver=ble_driver)
        ble_svc.init()
        log("✓ BLE 就绪")
    except Exception as e:
        log("✗ BLE 失败: %s" % e)
        return

    log("初始化 NavigationService...")
    nav_svc = NavigationService(bus, audio_driver=audio, lcd_driver=None)
    nav_svc.init()
    log("✓ NavigationService 就绪")

    countdown(15, "请在小程序点击「连接」")
    if not wait_ble(bus, ble_svc, 20):
        log("✗ 未连接")
        return
    log("✓ BLE 已连接")

    # === 测试 1: 模拟 nav 命令（板子本地）===
    log("")
    log("=" * 40)
    log(" 测试 1: 模拟 nav 命令 → TTS 播报")
    log("=" * 40)
    log("  请听板子喇叭是否有 TTS 播报")

    cmds = [
        {"a": "nav", "d": {"dir": "straight", "dist": 300, "road": "长安大道"}},
        {"a": "nav", "d": {"dir": "right", "dist": 150, "road": "雁南一路"}},
        {"a": "nav", "d": {"dir": "left", "dist": 80, "road": ""}},
        {"a": "nav", "d": {"dir": "arrive", "dist": 0, "road": ""}},
    ]

    for i, cmd in enumerate(cmds):
        raw = json.dumps(cmd)
        d = cmd["d"]
        if d["dir"] == "arrive":
            desc = "到达目的地"
        else:
            dir_cn = {"straight": "直行", "right": "右转", "left": "左转"}.get(d["dir"], d["dir"])
            desc = "前方%d米%s" % (d["dist"], dir_cn)
            if d["road"]:
                desc += "进入%s" % d["road"]

        log("  [%d/%d] %s" % (i + 1, len(cmds), desc))
        bus.publish(EVENT_NAV_CMD, {"raw": raw})
        bus.pump()
        pump_for(bus, ble_svc, 100)

        # 等 TTS 播完（约 3-5 秒）
        log("  等待 TTS 播报...")
        pump_for(bus, ble_svc, 4000)

    log("")
    log("⏱ 观察窗口: 5 秒")
    log("  [ ] TTS: 播报「前方300米直行进入长安大道」")
    log("  [ ] TTS: 播报「前方150米右转进入雁南一路」")
    log("  [ ] TTS: 播报「前方80米左转」")
    log("  [ ] TTS: 播报「已到达目的地」")
    pump_for(bus, ble_svc, 5000)

    # === 测试 2: 小程序实际导航 ===
    log("")
    log("=" * 40)
    log(" 测试 2: 小程序实际导航 (30 秒)")
    log("=" * 40)
    log("  请在小程序「开始骑行」→「设置目的地」→「开始导航」")
    log("  观察: 板子 TTS 是否播报导航指令")

    end = time.ticks_ms() + 30000
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        ble_svc.tick()
        bus.pump()
        time.sleep_ms(100)

    log("")
    log("=" * 50)
    print(" 测试完成")
    print("=" * 50)
    log("  [ ] 模拟 nav: TTS 播报正常")
    log("  [ ] 小程序导航: TTS 播报正常")
    log("  [ ] 中文路名: 不乱码")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
