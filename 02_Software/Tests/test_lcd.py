"""
brief LCD驱动模块单模块测试
note 测试LCDDriver的初始化、状态查询、数据显示、报警画面、清屏、背光、翻转、图片显示等功能
"""
import time
import sys

sys.path.insert(0, "/")

from core.config import EVENT_LCD_ERROR, EVENT_CONFIG_UPDATE
from core.Event_Bus import EventBus
from Drivers.actuator.LCD import LCDDriver

try:
    from images import QQ_ICON_40x40
    _has_images = True
except ImportError:
    _has_images = False
    print("[警告] images.py 导入失败，图片显示测试将跳过")

try:
    from images1 import Quectel_Icon_160x20
    _has_images1 = True
except ImportError:
    _has_images1 = False
    print("[警告] images1.py 导入失败，图片显示测试将跳过")


def test_lcd():
    print("=" * 50)
    print("LCD单模块测试开始")
    print("=" * 50)

    event_bus = EventBus()
    lcd = LCDDriver(event_bus=event_bus)

    # ====== [步骤1] 初始化 LCDDriver ======
    print("\n[步骤1] 初始化 LCDDriver...")
    try:
        lcd.init()
        print("  ✓ 初始化成功")
    except RuntimeError as e:
        print("  ✗ 初始化失败: {}".format(e))
        print("  请检查：SPI1是否可用、ST7735 LCD扩展板是否连接正确、dc_pin=F12/cs_pin=D14")
        return

    # ====== [步骤2] 查询模块状态 ======
    print("\n[步骤2] 查询模块状态...")
    status = lcd.get_status()
    print("  is_init:   {}".format(status["is_init"]))
    print("  is_busy:   {}".format(status["is_busy"]))
    print("  power:     {}".format(status["power_state"]))
    print("  err_count: {}".format(status["err_count"]))

    # ====== [步骤3] 手动tick测试（5次） ======
    print("\n[步骤3] 手动tick测试（5次）...")
    for i in range(5):
        lcd.tick()
        event_bus.pump()
        time.sleep_ms(100)
    print("  ✓ tick执行正常，无异常抛出")

    # ====== [步骤4] 数据显示测试 ======
    print("\n[步骤4] 数据显示测试...")

    # 4.1 正常数据画面
    print("  [4.1] 显示正常骑行数据...")
    lcd.show_normal_data(25.3, 65.2, 31.2304, 121.4737)
    data = lcd.get_data()
    if data["valid"] and data["display_mode"] == "normal":
        print("    ✓ 正常数据显示成功")
        print("    温度={}℃ 湿度={}% 纬度={} 经度={}".format(
            data["temp"], data["humid"], data["lat"], data["lon"]
        ))
    else:
        print("    ✗ 正常数据显示失败")
    time.sleep_ms(500)

    # 4.2 碰撞报警画面
    print("  [4.2] 显示碰撞报警画面...")
    lcd.show_alarm("collision")
    data = lcd.get_data()
    if data["valid"] and data["display_mode"] == "alarm_collision":
        print("    ✓ 碰撞报警画面显示成功")
    else:
        print("    ✗ 碰撞报警画面显示失败")
    time.sleep_ms(500)

    # 4.3 SOS报警画面
    print("  [4.3] 显示SOS报警画面...")
    lcd.show_alarm("sos")
    data = lcd.get_data()
    if data["valid"] and data["display_mode"] == "alarm_sos":
        print("    ✓ SOS报警画面显示成功")
    else:
        print("    ✗ SOS报警画面显示失败")
    time.sleep_ms(500)

    # 4.4 未知报警类型
    print("  [4.4] 显示未知报警类型画面...")
    lcd.show_alarm("unknown_type")
    data = lcd.get_data()
    if data["valid"] and data["display_mode"] == "alarm_unknown":
        print("    ✓ 未知报警画面显示成功（降级处理）")
    else:
        print("    ✗ 未知报警画面显示失败")
    time.sleep_ms(500)

    # 4.5 清屏
    print("  [4.5] 清屏测试...")
    lcd.clear()
    data = lcd.get_data()
    if data["display_mode"] == "normal" and data["temp"] == 0.0:
        print("    ✓ 清屏成功，数据已重置")
    else:
        print("    ✗ 清屏失败")
    time.sleep_ms(500)

    # 4.6 背光设置
    print("  [4.6] 背光亮度设置测试...")
    lcd.set_backlight(60)
    data = lcd.get_data()
    if data["backlight"] == 60:
        print("    ✓ 背光设置成功 (60%)")
    else:
        print("    ✗ 背光设置失败")

    lcd.set_backlight(150)
    data = lcd.get_data()
    if data["backlight"] == 100:
        print("    ✓ 背光边界截断成功 (150->100%)")
    else:
        print("    ✗ 背光边界截断失败")

    lcd.set_backlight(-10)
    data = lcd.get_data()
    if data["backlight"] == 0:
        print("    ✓ 背光边界截断成功 (-10->0%)")
    else:
        print("    ✗ 背光边界截断失败")

    # ====== [步骤5] 连续运行测试 ======
    print("\n[步骤5] 连续运行测试（10次切换）...")
    success_count = 0
    for i in range(10):
        if i % 2 == 0:
            lcd.show_normal_data(
                20.0 + i * 0.5, 50.0 + i,
                31.23 + i * 0.001, 121.47 + i * 0.001
            )
        else:
            lcd.show_alarm("collision" if i % 4 == 1 else "sos")

        lcd.tick()
        event_bus.pump()
        data = lcd.get_data()
        if data["valid"]:
            success_count += 1
        time.sleep_ms(200)

    print("  有效操作: {}/10".format(success_count))

    # 锁状态验证：报警中调用 show_normal_data() 应被拦截
    print("\n[步骤5.1] 状态锁验证...")
    lcd.show_alarm("collision")
    event_bus.pump()
    data = lcd.get_data()
    lock_mode = data["display_mode"]
    lcd.show_normal_data(30.0, 60.0, 31.23, 121.47)
    data = lcd.get_data()
    if data["display_mode"] == lock_mode:
        print("    ✓ 状态锁生效：报警中 normal 画面被拦截")
    else:
        print("    ✗ 状态锁失效：报警画面被覆盖")

    # ====== [步骤6] 翻转（rotation）测试 ======
    print("\n[步骤6] 翻转（rotation）测试...")
    rotation_ok = True
    for rot in range(4):
        print("  [6.{}] rotation={}".format(rot + 1, rot))
        try:
            lcd.lcd.set_rotation(rot)
            lcd.show_normal_data(25.3, 65.2, 31.2304, 121.4737)
            data = lcd.get_data()
            if data["valid"]:
                print("    ✓ rotation={} 显示正常".format(rot))
            else:
                print("    ✗ rotation={} 显示失败".format(rot))
                rotation_ok = False
            time.sleep_ms(800)
        except Exception as e:
            print("    ✗ rotation={} 异常: {}".format(rot, e))
            rotation_ok = False

    # 恢复默认rotation
    lcd.lcd.set_rotation(lcd.cfg["rotation"])
    lcd.clear()
    time.sleep_ms(300)

    # ====== [步骤7] 图片显示测试 ======
    print("\n[步骤7] 图片显示测试...")
    image_ok = True

    # 7.1 images.py - QQ_ICON_40x40
    if _has_images:
        print("  [7.1] 显示images.py QQ图标 (40x40)...")
        try:
            lcd.show_image(0, 0, 40, 40, QQ_ICON_40x40)
            data = lcd.get_data()
            print("    ✓ QQ图标显示成功")
            time.sleep_ms(800)
        except Exception as e:
            print("    ✗ QQ图标显示异常: {}".format(e))
            image_ok = False
    else:
        print("  [7.1] 跳过 images.py 导入失败")
        image_ok = False

    # 7.2 images1.py - Quectel_Icon_160x20
    if _has_images1:
        print("  [7.2] 显示images1.py Quectel图标 (160x20)...")
        try:
            lcd.clear()
            time.sleep_ms(200)
            lcd.show_image(0, 54, 160, 20, Quectel_Icon_160x20)
            data = lcd.get_data()
            print("    ✓ Quectel图标显示成功")
            time.sleep_ms(800)
        except Exception as e:
            print("    ✗ Quectel图标显示异常: {}".format(e))
            image_ok = False
    else:
        print("  [7.2] 跳过 images1.py 导入失败")
        image_ok = False

    # ====== 测试总结 ======
    print("\n" + "=" * 50)
    if success_count >= 8 and rotation_ok and image_ok:
        print("✓ LCD单模块测试通过")
    else:
        print("✗ 测试失败（翻转:{} 图片:{}）".format(
            "通过" if rotation_ok else "失败",
            "通过" if image_ok else "失败"
        ))
    print("=" * 50)


if __name__ == "__main__":
    test_lcd()
