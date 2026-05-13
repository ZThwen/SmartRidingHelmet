"""
brief 音频驱动单模块测试脚本
note 用于验证 AudioDriver 的各项公共接口功能是否正常
     音频播放为异步操作，测试中通过轮询 is_playing() 等待播放完成
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (EVENT_AUDIO_PLAYBACK_START, EVENT_AUDIO_PLAYBACK_END,
                    EVENT_AUDIO_ERROR, AUDIO_TEST_FILE)
from Drivers.actuator.Audio import AudioDriver

# ==================== 回调日志记录 ====================
event_log = []

def on_playback_start(payload):
    event_log.append(("START", payload))
    print(f"\n[事件回调] EVENT_AUDIO_PLAYBACK_START")
    print(f"  类型: {payload.get('type')}")
    print(f"  文件: {payload.get('file', payload.get('text', 'N/A'))}")

def on_playback_end(payload):
    event_log.append(("END", payload))
    print(f"\n[事件回调] EVENT_AUDIO_PLAYBACK_END")
    print(f"  类型: {payload.get('type')}")
    print(f"  主动停止: {payload.get('stopped', False)}")

def on_audio_error(payload):
    event_log.append(("ERROR", payload))
    print(f"\n[事件回调] EVENT_AUDIO_ERROR")
    print(f"  来源: {payload.get('source')}")
    print(f"  错误: {payload.get('error')}")

# ==================== 测试主流程 ====================
def test_audio():
    print("=" * 60)
    print("音频驱动单模块测试")
    print("=" * 60)

    # 创建事件总线
    event_bus = EventBus()
    event_bus.debug = True

    # 订阅事件
    event_bus.subscribe(EVENT_AUDIO_PLAYBACK_START, on_playback_start)
    event_bus.subscribe(EVENT_AUDIO_PLAYBACK_END, on_playback_end)
    event_bus.subscribe(EVENT_AUDIO_ERROR, on_audio_error)

    # 创建音频驱动实例
    audio = AudioDriver(event_bus)

    # ==================== 测试 1：初始化 ====================
    print("\n" + "-" * 60)
    print("[测试 1] 初始化模块")
    print("-" * 60)
    try:
        audio.init()
        print("\n✓ 初始化成功")
    except Exception as e:
        print(f"\n✗ 初始化失败: {e}")
        return

    # ==================== 测试 2：状态查询 ====================
    print("\n" + "-" * 60)
    print("[测试 2] 查看模块状态")
    print("-" * 60)
    status = audio.get_status()
    print(f"  is_init:       {status['is_init']}")
    print(f"  is_playing:    {status['is_playing']}")
    print(f"  is_tts_playing:{status['is_tts_playing']}")
    print(f"  err_count:     {status['err_count']}")
    print(f"  power_state:   {status['power_state']}")

    data = audio.get_data()
    print(f"  音量:          {data['volume']}")
    print(f"  TTS语速:       {data['tts_speed']}")

    # ==================== 测试 3：音频文件播放 ====================
    print("\n" + "-" * 60)
    print(f"[测试 3] 音频文件播放测试 ({AUDIO_TEST_FILE})")
    print("-" * 60)
    event_log.clear()

    result = audio.play_file(AUDIO_TEST_FILE)
    print(f"\n发起播放: {'✓' if result else '✗'}")

    if result:
        # 等待播放完成（超时 5 秒）
        timeout = time.time() + 5
        while time.time() < timeout:
            event_bus.pump()
            if not audio.get_is_playing():
                break
            time.sleep(0.05)

        if audio.get_is_playing():
            print("✗ 播放未在预期时间内完成")
            audio.stop()
        else:
            print("✓ 播放完成")
            # 检查事件日志
            start_events = [e for e in event_log if e[0] == "START"]
            end_events = [e for e in event_log if e[0] == "END"]
            print(f"  收到 START 事件: {len(start_events)} 次")
            print(f"  收到 END 事件:   {len(end_events)} 次")

    # ==================== 测试 4：TTS 播报测试 ====================
    print("\n" + "-" * 60)
    print("[测试 4] TTS 播报测试")
    print("-" * 60)
    event_log.clear()

    result = audio.play_tts("智能骑行头盔音频模块测试正常")
    print(f"\n发起 TTS: {'✓' if result else '✗'}")

    if result:
        timeout = time.time() + 5
        while time.time() < timeout:
            event_bus.pump()
            if not audio.get_is_playing():
                break
            time.sleep(0.05)

        if audio.get_is_playing():
            print("✗ TTS 未在预期时间内完成")
            audio.stop()
        else:
            print("✓ TTS 播报完成")

    # ==================== 测试 5：音量/语速控制 ====================
    print("\n" + "-" * 60)
    print("[测试 5] 音量/语速控制测试")
    print("-" * 60)

    # 设置扬声器音量为 3
    result = audio.set_volume(3)
    vol = audio.get_volume()
    print(f"  set_volume(3): {'✓' if result else '✗'} | 读取音量: {vol}")

    # 设置 TTS 语速为 60
    result = audio.set_tts_speed(60)
    data = audio.get_data()
    print(f"  set_tts_speed(60): {'✓' if result else '✗'} | 读取语速: {data['tts_speed']}")

    # 设置 TTS 音量为 50
    result = audio.set_tts_volume(50)
    print(f"  set_tts_volume(50): {'✓' if result else '✗'}")

    # ==================== 测试 6：停止播放测试 ====================
    print("\n" + "-" * 60)
    print("[测试 6] 停止播放测试")
    print("-" * 60)
    event_log.clear()

    # 开始播放
    result = audio.play_file(AUDIO_TEST_FILE)
    if result:
        time.sleep(0.3)  # 等待播放启动
        # 立即停止
        result = audio.stop()
        print(f"  停止播放: {'✓' if result else '✗'}")
        print(f"  播放状态: {'停止' if not audio.get_is_playing() else '仍在播放'}")

        # 检查事件日志中是否包含 stopped=True
        event_bus.pump()
        stopped_events = [e for e in event_log if e[0] == "END" and e[1].get("stopped")]
        print(f"  收到 stopped 事件: {len(stopped_events)} 次")

    # ==================== 测试总结 ====================
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    status = audio.get_status()
    print(f"\n最终状态:")
    print(f"  is_init:    {status['is_init']}")
    print(f"  err_count:  {status['err_count']}")

    # 恢复默认音量
    audio.set_volume(5)
    print(f"\n已恢复默认音量: 5")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_audio()
