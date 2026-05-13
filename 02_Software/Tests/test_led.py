"""
brief LED驱动模块单模块测试
note 测试LEDDriver的初始化、常亮、熄灭、闪烁、定时器回调翻转、闪烁到期自动停止、功耗切换等功能
"""
import time
import sys

sys.path.insert(0, "/")

from config import EVENT_LED_ERROR, EVENT_CONFIG_UPDATE
from core.Event_Bus import EventBus
from LED import LEDDriver


def test_led():
    print("=" * 50)
    print("LED单模块测试开始")
    print("=" * 50)

    event_bus = EventBus()
    led = LEDDriver(event_bus=event_bus)

    # ====== [步骤1] 初始化 LEDDriver ======
    print("\n[步骤1] 初始化 LEDDriver...")
    try:
        led.init()
        print("  OK 初始化成功")
    except Exception as e:
        print("  FAIL 初始化失败: {}".format(e))
        return

    # ====== [步骤2] 查询模块状态 ======
    print("\n[步骤2] 查询模块状态...")
    status = led.get_status()
    print("  is_init:   {}".format(status["is_init"]))
    print("  power:     {}".format(status["power_state"]))
    print("  blink_mode:{}".format(status["blink_mode"]))

    # ====== [步骤3] 常亮测试 ======
    print("\n[步骤3] 常亮测试...")
    led.on()
    data = led.get_data()
    if data["state"] == "on":
        print("  OK on() 成功，state=on")
    else:
        print("  FAIL on() 失败")
    time.sleep_ms(500)

    # ====== [步骤4] 熄灭测试 ======
    print("\n[步骤4] 熄灭测试...")
    led.off()
    data = led.get_data()
    if data["state"] == "off":
        print("  OK off() 成功，state=off")
    else:
        print("  FAIL off() 失败")
    time.sleep_ms(300)

    # ====== [步骤5] 闪烁测试（定时器驱动） ======
    print("\n[步骤5] 闪烁测试 blink(3000, 500)...")
    led.blink(3000, 500)
    data = led.get_data()
    status = led.get_status()
    if status["blink_mode"] and data["blink_interval"] == 500:
        print("  OK 闪烁启动成功，interval=500ms, duration=3000ms")
    else:
        print("  FAIL 闪烁启动失败")
    print("  等待3秒观察闪烁（由Timer驱动）...")
    time.sleep_ms(3200)

    data = led.get_data()
    status = led.get_status()
    if data["state"] == "off" and not status["blink_mode"]:
        print("  OK 闪烁到期自动停止，LED已熄灭")
    else:
        print("  闪烁可能仍在运行或状态异常")

    # ====== [步骤6] 闪烁中途调on/off停止闪烁 ======
    print("\n[步骤6] 闪烁中途调on/off停止闪烁...")
    led.blink(5000, 300)
    time.sleep_ms(800)
    led.on()
    status = led.get_status()
    data = led.get_data()
    if not status["blink_mode"] and data["state"] == "on":
        print("  OK on()停止闪烁成功，state=on")
    else:
        print("  FAIL on()停止闪烁失败")
    time.sleep_ms(300)

    led.blink(5000, 300)
    time.sleep_ms(800)
    led.off()
    status = led.get_status()
    data = led.get_data()
    if not status["blink_mode"] and data["state"] == "off":
        print("  OK off()停止闪烁成功，state=off")
    else:
        print("  FAIL off()停止闪烁失败")

    # ====== [步骤7] 闪烁间隔限幅测试 ======
    print("\n[步骤7] 闪烁间隔限幅测试...")
    led.blink(5000, 50)
    data = led.get_data()
    if data["blink_interval"] == 500:
        print("  OK interval=50 限幅为默认500ms")
    else:
        print("  FAIL 限幅异常: interval={}".format(data["blink_interval"]))
    led.off()

    led.blink(5000, 9999)
    data = led.get_data()
    if data["blink_interval"] == 500:
        print("  OK interval=9999 限幅为默认500ms")
    else:
        print("  FAIL 限幅异常: interval={}".format(data["blink_interval"]))
    led.off()

    # ====== [步骤8] 功耗状态切换 ======
    print("\n[步骤8] 功耗状态切换...")
    led.on()
    led._on_config_update({"power_state": "SUSPENDED"})
    data = led.get_data()
    if data["state"] == "off":
        print("  OK 进入SUSPENDED，LED熄灭")
    else:
        print("  FAIL SUSPENDED异常")

    led._on_config_update({"power_state": "ACTIVE"})
    data = led.get_data()
    if data["state"] == "on":
        print("  OK 恢复ACTIVE，LED亮")
    else:
        print("  FAIL ACTIVE恢复异常")
    led.off()

    # ====== [步骤9] tick测试 ======
    print("\n[步骤9] tick测试...")
    led.tick()
    event_bus.pump()
    print("  OK tick()正常返回（Timer驱动模块，tick空转）")

    # ====== [步骤10] 数据/状态查询 ======
    print("\n[步骤10] 数据/状态查询...")
    led.on()
    data = led.get_data()
    status = led.get_status()
    print("  get_data:   state={}, blink_duration={}, blink_interval={}".format(
        data["state"], data["blink_duration"], data["blink_interval"]))
    print("  get_status: is_init={}, blink_mode={}, power={}".format(
        status["is_init"], status["blink_mode"], status["power_state"]))
    led.off()

    # ====== 测试总结 ======
    print("\n" + "=" * 50)
    print("LED单模块测试完成")
    print("=" * 50)


if __name__ == "__main__":
    test_led()
