"""
brief 自适应灯光服务模块硬件测试
note 真实场景模拟，验证需求：
      1. 白天（环境亮）→ 灯不开
      2. 下午/晚上（环境暗）→ 灯自动亮起
      3. 天越暗 → 灯越亮
      测试环境：STM32 NUCLEO-F413ZH + UniKnect Gen1-PRO
      光敏传感器：GL5528（ADC引脚PC5）
      LED：Arduino D5引脚（STM32 PE11, TIM1_CH2）
"""
import time
import sys
sys.path.append("..")

from core.config import EVENT_LIGHT_READY, EVENT_CONFIG_UPDATE, POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED
from core.Event_Bus import EventBus
from Drivers.sensor.Light import LightSensorDriver
from Drivers.actuator.PWM_LED import PWMLEDDriver
from Modules.light_service import LightService


def test_light_service():
    """
    brief 自适应灯光服务硬件测试主函数
    note 真实场景模拟，流畅测试
    """
    print("=" * 60)
    print("自适应灯光服务模块 - 硬件测试（真实场景）")
    print("=" * 60)

    print("\n[需求验证]")
    print("  1. 白天（环境亮）→ 灯不开")
    print("  2. 下午/晚上（环境暗）→ 灯自动亮起")
    print("  3. 天越暗 → 灯越亮")
    print("  4. 18W灯散热限制：峰值亮度50%")

    event_bus = EventBus()

    print("\n[步骤1] 创建Device层模块")
    light_sensor = LightSensorDriver(event_bus=event_bus)
    pwm_led = PWMLEDDriver(event_bus=event_bus)
    print("  已创建: Light, PWM_LED")

    print("\n[步骤2] 创建Service层模块")
    light_service = LightService(event_bus=event_bus, pwm_led=pwm_led)
    print("  已创建: LightService")

    print("\n[步骤3] 初始化所有模块")
    try:
        light_sensor.init()
        pwm_led.init()
        light_service.init()
        print("  OK 所有模块初始化成功")
    except Exception as e:
        print("  FAIL 初始化失败: {}".format(e))
        return

    print("\n[步骤4] 显示配置参数")
    print("  白天阈值: {} (ADC，光照强)".format(light_service.cfg["light_day_threshold"]))
    print("  晚上阈值: {} (ADC，光照弱)".format(light_service.cfg["light_night_threshold"]))
    print("  亮度范围: {}% - {}%".format(light_service.cfg["brightness_min"], light_service.cfg["brightness_max"]))
    print("  Gamma参数: {}".format(light_service.cfg["gamma"]))

    print("\n[步骤5] 设置采样间隔为100ms（真实场景）")
    light_sensor._on_config_update({
        "target": "light_Sensor",
        "sample_ms": 100
    })
    print("  OK 采样间隔已设置为100ms")

    print("\n" + "=" * 60)
    print("[测试1] 自动亮度调节（30秒，真实场景）")
    print("=" * 60)
    print("说明：请改变环境光照")
    print("  - 强光（手电筒照射）→ ADC值小 → 灯不开")
    print("  - 弱光（遮挡光敏电阻）→ ADC值大 → 灯最亮（50%）")
    print("  - 正常室内光 → ADC值中等 → 灯中等亮度")
    print("  - 峰值亮度限制为50%（18W灯散热）")

    start_time = time.ticks_ms()
    last_print_time = 0

    while True:
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, start_time)

        if elapsed >= 30000:
            break

        light_sensor.tick()
        event_bus.pump()

        if time.ticks_diff(now, last_print_time) >= 500:
            data = light_service.get_data()
            print("  [{:5.1f}s] light={:5d} ({}), brightness={:3d}%, mode={}".format(
                elapsed / 1000.0, data["light_intensity"], data["light_level"],
                data["current_brightness"], data["mode"]
            ))
            last_print_time = now

    print("\n" + "=" * 60)
    print("[测试2] 手动亮度控制（10秒）")
    print("=" * 60)
    print("说明：设置手动亮度为80%，改变环境光照")
    print("预期：LED亮度保持80%，不随光照变化")

    light_service.set_manual_brightness(80)
    print("  已切换到手动模式，亮度=80%")

    start_time = time.ticks_ms()
    last_print_time = 0

    while True:
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, start_time)

        if elapsed >= 10000:
            break

        light_sensor.tick()
        event_bus.pump()

        if time.ticks_diff(now, last_print_time) >= 1000:
            data = light_service.get_data()
            print("  [{:5.1f}s] light={:5d} ({}), brightness={:3d}%, mode={}".format(
                elapsed / 1000.0, data["light_intensity"], data["light_level"],
                data["current_brightness"], data["mode"]
            ))
            last_print_time = now

    print("\n" + "=" * 60)
    print("[测试3] 模式切换（20秒）")
    print("=" * 60)
    print("说明：恢复自动模式，改变环境光照")
    print("预期：LED亮度随光照变化")

    light_service.set_auto_mode()
    print("  已恢复自动模式")

    start_time = time.ticks_ms()
    last_print_time = 0

    while True:
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, start_time)

        if elapsed >= 20000:
            break

        light_sensor.tick()
        event_bus.pump()

        if time.ticks_diff(now, last_print_time) >= 500:
            data = light_service.get_data()
            print("  [{:5.1f}s] light={:5d} ({}), brightness={:3d}%, mode={}".format(
                elapsed / 1000.0, data["light_intensity"], data["light_level"],
                data["current_brightness"], data["mode"]
            ))
            last_print_time = now

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    print("\n模块状态:")
    status = light_service.get_status()
    print("  LightService:")
    print("    is_init:   {}".format(status["is_init"]))
    print("    auto_mode: {}".format(status["auto_mode"]))
    print("    power:     {}".format(status["power_state"]))
    print("    err_count: {}".format(status["err_count"]))

    print("\nLED状态:")
    led_data = pwm_led.get_data()
    print("  PWM_LED:")
    print("    brightness: {}%".format(led_data["duty_cycle"]))

    print("\n验收标准:")
    print("  [ ] ADC值小（光照强）→ 灯不开（brightness=0%）")
    print("  [ ] ADC值大（光照弱）→ 灯自动亮起（brightness>0%）")
    print("  [ ] ADC值越大 → 灯越亮")
    print("  [ ] 峰值亮度限制为50%（18W灯散热）")
    print("  [ ] 手动亮度控制：手动模式下亮度固定")
    print("  [ ] 模式切换：自动/手动模式正确切换")
    print("  [ ] 真实场景：流畅响应，不卡顿")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_light_service()
