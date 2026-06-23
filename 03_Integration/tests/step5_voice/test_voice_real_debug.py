"""
brief 语音模块真实集成环境诊断测试（UART2 原始数据监听）
note 使用真实 UART2 持续监听 ASRPRO 语音模块输出
      每收到一个字节即打印 hex 值和映射后的指令名
      用于排查"小洛包"无应答等问题
usage 上传到板子运行: python test_voice_real_debug.py
      按 Ctrl+C 停止测试
"""
import sys
import time

sys.path.append("../../../02_Software")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_VOICE_CMD, VOICE_CMD_MAP,
    VOICE_UART_ID, VOICE_UART_BAUDRATE,
)
from Drivers.interface.Voice import VoiceDriver
from Modules.control_service import ControlService

# CPython 兼容
try:
    _ticks_ms = time.ticks_ms
    _ticks_diff = time.ticks_diff
    _sleep_ms = time.sleep_ms
except AttributeError:
    _ticks_ms = lambda: int(time.time() * 1000)
    _ticks_diff = lambda a, b: a - b
    _sleep_ms = lambda ms: time.sleep(ms / 1000.0)


def main():
    print("\n" + "=" * 60)
    print("=== Voice UART2 诊断测试 ===")
    print("=" * 60)

    # ===== UART 配置信息 =====
    print("\nUART 配置: id=%d, baudrate=%d" % (VOICE_UART_ID, VOICE_UART_BAUDRATE))
    print("VOICE_CMD_MAP: %d 条指令映射" % len(VOICE_CMD_MAP))
    print("  wake(0x00) light(0x01-0x05) volume(0x06-0x07) alarm(0x08-0x0A)")
    print("  power(0x0B-0x0D) query(0x0E-0x13)")
    print("")

    # ===== 初始化系统 =====
    bus = EventBus()

    print("初始化 VoiceDriver (UART%d)..." % VOICE_UART_ID)
    voice = VoiceDriver(bus, uart_id=VOICE_UART_ID, baudrate=VOICE_UART_BAUDRATE)
    try:
        voice.init()
        print("  VoiceDriver OK: uart=%d, baud=%d" % (VOICE_UART_ID, VOICE_UART_BAUDRATE))
    except Exception as e:
        print("  VoiceDriver FAIL: %s" % e)
        print("  请检查:")
        print("    - UART%d 引脚连接 (D52 TX, D53 RX)" % VOICE_UART_ID)
        print("    - ASRPRO 是否已上电")
        return

    print("初始化 ControlService...")
    ctrl = ControlService(bus)
    try:
        ctrl.init()
        print("  ControlService OK")
    except Exception as e:
        print("  ControlService FAIL: %s" % e)
        return

    print("\n等待 ASRPRO 发送数据...")
    print("请通过语音唤醒 '小洛包' 测试")
    print("按 Ctrl+C 停止测试\n")
    print("-" * 60)

    # ===== 主循环 =====
    start_ticks = _ticks_ms()
    last_heartbeat = start_ticks
    last_data_ticks = start_ticks
    byte_count = 0
    idle_printed = False
    warning_printed = False

    try:
        while True:
            now = _ticks_ms()

            # ===== 读取 UART 原始字节 =====
            if voice.uart and voice.uart.any():
                data = voice.uart.read(1)
                if data and len(data) > 0:
                    hex_val = data[0]
                    cmd = VOICE_CMD_MAP.get(hex_val, "UNKNOWN")
                    elapsed = _ticks_diff(now, start_ticks) / 1000.0

                    # 更新 VoiceDriver 内部状态
                    voice._data["last_hex"] = hex_val
                    voice._data["last_cmd"] = cmd

                    print("[%.1fs] 收到字节: 0x%02X -> %s" % (elapsed, hex_val, cmd))

                    if cmd != "UNKNOWN":
                        # 重置 ControlService 防抖，确保诊断模式每条指令都执行
                        ctrl.ctx["last_cmd_tick"] = 0
                        ctrl.ctx["last_tts_tick"] = 0
                        # 发布事件到 EventBus → ControlService 级联处理
                        bus.publish(EVENT_VOICE_CMD, {"cmd": cmd})
                        print("  -> ControlService 执行: %s" % cmd)
                    else:
                        print("  -> UNKNOWN (未映射指令)")

                    byte_count += 1
                    last_data_ticks = _ticks_ms()
                    warning_printed = False

            # ===== 泵送事件总线 (drain 级联事件) =====
            bus.pump()

            # ===== 每 5 秒心跳 =====
            now = _ticks_ms()
            if _ticks_diff(now, last_heartbeat) >= 1000:
                elapsed = _ticks_diff(now, start_ticks) / 1000.0
                status = voice.get_status()
                data = voice.get_data()
                print("[%.1fs] 心跳: err_count=%d, last_cmd=%s, total_bytes=%d" % (
                    elapsed,
                    status.get("err_count", 0),
                    data.get("last_cmd", "none"),
                    byte_count))
                last_heartbeat = now

            # ===== 初始空闲提示 (1 秒后) =====
            if not idle_printed and byte_count == 0:
                idle_ms = _ticks_diff(now, start_ticks)
                if idle_ms >= 1000:
                    elapsed = idle_ms / 1000.0
                    print("[%.1fs] UART 空闲，等待中..." % elapsed)
                    idle_printed = True

            # ===== 长时间无数据警告 (30 秒后) =====
            idle_ms = _ticks_diff(now, last_data_ticks)
            if idle_ms >= 30000 and not warning_printed:
                elapsed = _ticks_diff(now, start_ticks) / 1000.0
                print("[%.1fs] 提示: %d秒未收到数据，请检查 ASRPRO 连接" % (
                    elapsed, idle_ms // 1000))
                print("  - 确认 ASRPRO 已上电")
                print("  - 确认 UART%d (D52 TX, D53 RX) 引脚连接" % VOICE_UART_ID)
                print("  - 尝试语音指令: '小洛包' (唤醒词)")
                warning_printed = True
            elif idle_ms < 30000:
                warning_printed = False

            _sleep_ms(10)

    except KeyboardInterrupt:
        print("\n用户中断测试")
    except Exception as e:
        print("\n异常: %s" % e)
        try:
            import sys as _sys
            _sys.print_exception(e)
        except Exception:
            pass
    finally:
        print("\n测试结束")
        print("共收到 %d 字节" % byte_count)
        try:
            voice.deinit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
