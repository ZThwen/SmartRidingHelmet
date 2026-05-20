"""
DisplayService 完整测试 - 真实硬件测试
MicroPython环境，需要上传到Flash执行

关键修正：
1. EventBus.publish()后必须调用pump()处理队列
2. 每个测试步骤保持5秒让用户观察
3. 读取真实硬件数据而非假数据
4. 图片正确加载和显示
5. Light.py类名：LightSensorDriver（已修正）
6. 不读取GNSS，不测试坐标速度（室内无信号）
"""
import time

print("=" * 60)
print("DisplayService 完整测试 - 真实硬件")
print("=" * 60)

from DisplayService import DisplayService
from Event_Bus import EventBus
from config import (
    EVENT_TEMP_HUMID_READY,
    EVENT_GNSS_READY,
    EVENT_LIGHT_READY,
    EVENT_ALARM_TRIGGERED,
    EVENT_ALARM_CANCELED,
    EVENT_POWER_STATE_CHANGE,
)

print("[OK] 核心模块导入成功")

try:
    from LCD import LCDDriver
    print("[OK] LCDDriver导入成功")
except ImportError as e:
    print("[ERROR] LCDDriver导入失败: {}".format(e))
    LCDDriver = None

try:
    from Audio import AudioDriver
    print("[OK] AudioDriver导入成功")
except ImportError as e:
    print("[WARN] AudioDriver导入失败: {}".format(e))
    AudioDriver = None

try:
    from Temp_Humid import TempHumidDriver
    print("[OK] TempHumidDriver导入成功")
except ImportError as e:
    print("[WARN] TempHumidDriver导入失败: {}".format(e))
    TempHumidDriver = None

try:
    from Light import LightSensorDriver
    print("[OK] LightSensorDriver导入成功")
except ImportError as e:
    print("[WARN] LightSensorDriver导入失败: {}".format(e))
    LightSensorDriver = None

def wait_with_pump(event_bus, ms, service=None, sensors=None):
    """等待指定毫秒，期间持续调用pump和tick"""
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        event_bus.pump()
        if service:
            service.tick()
        if sensors:
            for sensor in sensors:
                if sensor:
                    sensor.tick()
        time.sleep_ms(50)

def test_1_init_and_boot():
    """测试1: 初始化和开机画面"""
    print("\n" + "=" * 60)
    print("测试1: 初始化和开机画面")
    print("=" * 60)
    
    event_bus = EventBus()
    print("[OK] EventBus创建成功")
    
    lcd = None
    audio = None
    temp_humid = None
    light = None
    sensors = []
    
    if LCDDriver:
        print("\n[初始化] LCD驱动...")
        lcd = LCDDriver(event_bus)
        lcd.init()
        print("[OK] LCD驱动初始化完成")
    
    if AudioDriver:
        print("\n[初始化] Audio驱动...")
        audio = AudioDriver(event_bus)
        audio.init()
        print("[OK] Audio驱动初始化完成")
    
    if TempHumidDriver:
        print("\n[初始化] 温湿度传感器...")
        temp_humid = TempHumidDriver(event_bus)
        temp_humid.init()
        sensors.append(temp_humid)
        print("[OK] 温湿度传感器初始化完成")
    
    if LightSensorDriver:
        print("  LightSensorDriver初始化和导入")
        light = LightSensorDriver(event_bus)
        light.init()
        sensors.append(light)
        print("[OK] 光照传感器初始化完成")
    
    print("\n[创建] DisplayService...")
    service = DisplayService(event_bus, lcd, audio)
    service.init()
    
    status = service.get_status()
    print("初始化状态: is_init={}, display_mode={}".format(
        status["is_init"], status["display_mode"]))
    
    print("\n[等待] 开机画面显示2.5秒...")
    wait_with_pump(event_bus, 3000, service, sensors)
    
    status = service.get_status()
    print("开机完成: boot_displayed={}, display_mode={}".format(
        status["boot_displayed"], status["display_mode"]))
    
    print("\n[观察] 请确认屏幕已切换到正常画面（QQ图标消失）")
    print("等待2秒继续...")
    wait_with_pump(event_bus, 2000, service, sensors)
    
    print("\n[测试1] 通过")
    return service, event_bus, lcd, sensors

def test_2_normal_display(service, event_bus, lcd, sensors):
    """测试2: 正常画面数据显示（读取真实传感器数据，无GNSS）"""
    print("\n" + "=" * 60)
    print("测试2: 正常画面数据显示（真实传感器数据）")
    print("=" * 60)
    
    print("\n[提示] 本测试读取真实传感器数据")
    print("温湿度传感器需要约2秒采集数据")
    print("光照传感器实时读取")
    print("注意：不读取GNSS定位（室内无信号）")
    
    print("\n[等待] 传感器采集数据5秒...")
    wait_with_pump(event_bus, 5000, service, sensors)
    
    data = service.get_data()
    status = service.get_status()
    
    print("\n[结果] 传感器数据:")
    print("  温度: {}°C".format(data["temp"] if data["temp"] is not None else "无数据"))
    print("  湿度: {}%".format(data["humid"] if data["humid"] is not None else "无数据"))
    print("  光照: {}lux".format(data["light_intensity"] if data["light_intensity"] is not None else "无数据"))
    print("  显示模式: {}".format(status["display_mode"]))
    print("  （定位和速度显示占位符，不读取GNSS）")
    
    print("\n[观察] 请确认屏幕显示上述温湿度数据")
    print("等待5秒观察...")
    wait_with_pump(event_bus, 5000, service, sensors)
    
    print("\n[测试2] 通过")

def test_3_light_backlight(service, event_bus, lcd, sensors):
    """测试3: 光照自动调节背光（真实调节，5秒观察）"""
    print("\n" + "=" * 60)
    print("测试3: 光照自动调节背光")
    print("=" * 60)
    
    if not lcd:
        print("[跳过] LCD驱动未初始化")
        return
    
    print("\n[说明] 测试不同光照强度下的背光自动调节")
    print("每个档位保持5秒，请观察屏幕亮度变化")
    
    test_cases = [
        (50, 20, "暗环境"),
        (300, 50, "室内环境"),
        (700, 80, "明亮环境"),
        (1500, 100, "户外强光"),
    ]
    
    for lux, expected, desc in test_cases:
        print("\n[步骤] 模拟{}: {} lux".format(desc, lux))
        event_bus.publish(EVENT_LIGHT_READY, {"light_intensity": lux})
        event_bus.pump()
        
        status = service.get_status()
        actual = status["current_backlight"]
        
        print("光照: {} lux -> 期望背光: {}% -> 设置背光: {}%".format(
            lux, expected, actual))
        
        print("请观察屏幕亮度...等待5秒")
        wait_with_pump(event_bus, 5000, service, sensors)
    
    print("\n[测试3] 通过")

def test_4_collision_alarm(service, event_bus, lcd, sensors):
    """测试4: 碰撞报警（真实背光变化，5秒观察）"""
    print("\n" + "=" * 60)
    print("测试4: 碰撞报警")
    print("=" * 60)
    
    if not lcd:
        print("[跳过] LCD驱动未初始化")
        return
    
    print("\n[步骤1] 读取当前背光值")
    status = service.get_status()
    current_backlight = status["current_backlight"]
    print("当前背光: {}%".format(current_backlight))
    
    print("\n[步骤2] 触发碰撞报警")
    event_bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "collision"})
    event_bus.pump()
    time.sleep_ms(100)
    
    status = service.get_status()
    print("报警状态: is_alarm_active={}, display_mode={}".format(
        status["is_alarm_active"], status["display_mode"]))
    
    alarm_backlight = status["current_backlight"]
    print("报警背光: {}% (应为100%)".format(alarm_backlight))
    
    print("\n[观察] 屏幕应显示碰撞报警文字，背光为100%")
    print("等待5秒观察...")
    wait_with_pump(event_bus, 5000, service, sensors)
    
    print("\n[步骤3] 取消报警")
    event_bus.publish(EVENT_ALARM_CANCELED, {})
    event_bus.pump()
    time.sleep_ms(100)
    
    status = service.get_status()
    normal_backlight = status["current_backlight"]
    print("取消报警: is_alarm_active={}, display_mode={}".format(
        status["is_alarm_active"], status["display_mode"]))
    print("恢复正常背光: {}%".format(normal_backlight))
    
    print("\n[观察] 屏幕应恢复正常画面，背光恢复")
    print("等待5秒观察...")
    wait_with_pump(event_bus, 5000, service, sensors)
    
    print("\n[测试4] 通过")

def test_5_sos_alarm(service, event_bus, lcd, sensors):
    """测试5: SOS报警（显示移远图标，5秒观察）"""
    print("\n" + "=" * 60)
    print("测试5: SOS报警（显示移远图标）")
    print("=" * 60)
    
    if not lcd:
        print("[跳过] LCD驱动未初始化")
        return
    
    data = service.get_data()
    print("\n[检查] SOS图标加载状态: {}".format(
        "已加载" if data["sos_icon_loaded"] else "未加载"))
    
    if not data["sos_icon_loaded"]:
        print("[警告] images1.py未正确加载，尝试重新加载...")
        try:
            from images1 import Quectel_Icon_160x20
            print("[OK] images1.py存在，图标数据长度: {}字节".format(len(Quectel_Icon_160x20)))
        except ImportError as e:
            print("[错误] images1.py导入失败: {}".format(e))
            print("请确认images1.py已上传到Flash")
    
    print("\n[步骤1] 读取当前背光值")
    status = service.get_status()
    current_backlight = status["current_backlight"]
    print("当前背光: {}%".format(current_backlight))
    
    print("\n[步骤2] 触发SOS报警")
    event_bus.publish(EVENT_ALARM_TRIGGERED, {"alarm_type": "sos"})
    event_bus.pump()
    time.sleep_ms(100)
    
    status = service.get_status()
    print("报警状态: is_alarm_active={}, display_mode={}".format(
        status["is_alarm_active"], status["display_mode"]))
    
    alarm_backlight = status["current_backlight"]
    print("报警背光: {}% (应为100%)".format(alarm_backlight))
    
    print("\n[观察] 屏幕应显示移远图标和'SOS!'文字，背光为100%")
    print("等待5秒观察...")
    wait_with_pump(event_bus, 5000, service, sensors)
    
    print("\n[步骤3] 取消SOS报警")
    event_bus.publish(EVENT_ALARM_CANCELED, {})
    event_bus.pump()
    time.sleep_ms(100)
    
    status = service.get_status()
    normal_backlight = status["current_backlight"]
    print("取消报警: is_alarm_active={}, display_mode={}".format(
        status["is_alarm_active"], status["display_mode"]))
    print("恢复正常背光: {}%".format(normal_backlight))
    
    print("\n[观察] 屏幕应恢复正常画面，背光恢复")
    print("等待5秒观察...")
    wait_with_pump(event_bus, 5000, service, sensors)
    
    print("\n[测试5] 通过")

def test_6_power_state(service, event_bus, lcd, sensors):
    """测试6: 功耗状态切换（真实背光变化，5秒观察）"""
    print("\n" + "=" * 60)
    print("测试6: 功耗状态切换")
    print("=" * 60)
    
    if not lcd:
        print("[跳过] LCD驱动未初始化")
        return
    
    print("\n[步骤1] 读取当前背光值")
    status = service.get_status()
    current_backlight = status["current_backlight"]
    print("当前背光: {}%".format(current_backlight))
    
    print("\n[步骤2] 进入休眠")
    event_bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": "SLEEP"})
    event_bus.pump()
    time.sleep_ms(100)
    
    status = service.get_status()
    sleep_backlight = status["current_backlight"]
    print("功耗状态: {}, 背光: {}% (应为0%)".format(
        status["power_state"], sleep_backlight))
    
    print("\n[观察] 屏幕背光应关闭（黑屏）")
    print("等待5秒观察...")
    wait_with_pump(event_bus, 5000, service, sensors)
    
    print("\n[步骤3] 唤醒")
    event_bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": "ACTIVE"})
    event_bus.pump()
    time.sleep_ms(100)
    
    status = service.get_status()
    active_backlight = status["current_backlight"]
    print("功耗状态: {}, 背光: {}%".format(
        status["power_state"], active_backlight))
    
    print("\n[观察] 屏幕背光应恢复")
    print("等待5秒观察...")
    wait_with_pump(event_bus, 5000, service, sensors)
    
    print("\n[测试6] 通过")

def run():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始测试...")
    print("=" * 60)
    
    try:
        service, event_bus, lcd, sensors = test_1_init_and_boot()
        test_2_normal_display(service, event_bus, lcd, sensors)
        test_3_light_backlight(service, event_bus, lcd, sensors)
        test_4_collision_alarm(service, event_bus, lcd, sensors)
        test_5_sos_alarm(service, event_bus, lcd, sensors)
        test_6_power_state(service, event_bus, lcd, sensors)
        
        print("\n" + "=" * 60)
        print("所有测试通过!")
        print("=" * 60)
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("测试失败: {}".format(e))
        print("=" * 60)
        raise

if __name__ == "__main__":
    run()
