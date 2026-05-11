"""
brief 音频模块集成测试
note 测试 AudioDriver 在完整系统环境下的工作情况（事件流转、模块协作）
     验证 play_file、play_tts、stop 等操作是否能正确发布事件
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (EVENT_SYSTEM_READY, EVENT_AUDIO_PLAYBACK_START,
                    EVENT_AUDIO_PLAYBACK_END, EVENT_AUDIO_ERROR,
                    EVENT_CONFIG_UPDATE, AUDIO_TEST_FILE)
from Audio import AudioDriver


class IntegrationTest:
    def __init__(self):
        self.event_bus = None
        self.modules = []
        self.test_results = {
            "playback_event_ok": False,
            "playback_end_ok": False,
            "tts_event_ok": False,
            "stop_event_ok": False,
            "config_update_ok": False
        }

    def setup(self):
        """
        brief 搭建集成测试环境
        """
        print("=" * 60)
        print("集成环境测试 - 音频模块")
        print("=" * 60)

        # 1. 创建事件总线
        print("\n[步骤 1] 创建事件总线")
        self.event_bus = EventBus()
        self.event_bus.debug = True

        # 2. 订阅关键事件
        print("\n[步骤 2] 订阅系统事件")
        self.event_bus.subscribe(EVENT_SYSTEM_READY, self._on_system_ready)
        self.event_bus.subscribe(EVENT_AUDIO_PLAYBACK_START, self._on_playback_start)
        self.event_bus.subscribe(EVENT_AUDIO_PLAYBACK_END, self._on_playback_end)
        self.event_bus.subscribe(EVENT_AUDIO_ERROR, self._on_audio_error)
        print("  ✓ 已订阅: SYSTEM_READY, AUDIO_PLAYBACK_START, AUDIO_PLAYBACK_END, AUDIO_ERROR")

        # 3. 创建模块实例
        print("\n[步骤 3] 创建模块实例")
        audio = AudioDriver(self.event_bus)
        self.modules.append(audio)
        print(f"  ✓ 已创建: {audio.name}")

    def _on_system_ready(self, payload):
        """
        brief 系统就绪事件回调
        """
        print(f"\n[事件回调] SYSTEM_READY")
        print(f"  模块数量: {payload['modules_count']}")

    def _on_playback_start(self, payload):
        """
        brief 音频开始播放事件回调
        """
        event_type = payload.get("type")
        print(f"\n[事件回调] AUDIO_PLAYBACK_START")
        print(f"  类型: {event_type}")
        if event_type == "playback":
            print(f"  文件: {payload.get('file')}")
        elif event_type == "tts":
            print(f"  文本: {payload.get('text')}")

    def _on_playback_end(self, payload):
        """
        brief 音频播放结束事件回调
        """
        event_type = payload.get("type")
        stopped = payload.get("stopped", False)
        print(f"\n[事件回调] AUDIO_PLAYBACK_END")
        print(f"  类型: {event_type} | 主动停止: {stopped}")

        if event_type == "playback" and not stopped:
            self.test_results["playback_end_ok"] = True

    def _on_audio_error(self, payload):
        """
        brief 音频错误事件回调
        """
        print(f"\n[事件回调] AUDIO_ERROR")
        print(f"  来源: {payload.get('source')}")
        print(f"  错误: {payload.get('error')}")

    def init_modules(self):
        """
        brief 初始化所有模块
        """
        print("\n[步骤 4] 初始化模块")
        for mod in self.modules:
            try:
                print(f"  -> 初始化 {mod.name}...")
                mod.init()
                print(f"  ✓ {mod.name} 初始化成功")
            except Exception as e:
                print(f"  ✗ {mod.name} 初始化失败: {e}")
                raise

        self.event_bus.publish(EVENT_SYSTEM_READY, {"modules_count": len(self.modules)})
        print(f"\n✅ 系统就绪，共启动 {len(self.modules)} 个模块")

    def wait_for_playback(self, timeout_ms=5000):
        """
        brief 等待播放结束（轮询 is_playing）
        param timeout_ms: 超时时间（毫秒）
        return bool 是否正常结束
        """
        audio = self.modules[0]
        deadline = time.ticks_ms() + timeout_ms
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            for mod in self.modules:
                mod.tick()
            self.event_bus.pump()
            if not audio.get_is_playing():
                return True
            time.sleep_ms(50)
        return False

    # ==================== 测试用例 ====================
    def test_playback_event(self):
        """
        brief 测试音频文件播放事件流转
        """
        print("\n" + "-" * 60)
        print("[测试 1] 音频文件播放事件测试")
        print("-" * 60)

        audio = self.modules[0]
        self.test_results["playback_event_ok"] = False

        # 发起播放
        result = audio.play_file(AUDIO_TEST_FILE)
        print(f"\n发起播放: {'✓' if result else '✗'}")

        if not result:
            print("✗ 播放发起失败")
            return

        # 处理事件（应收到 START 事件）
        time.sleep_ms(100)
        self.event_bus.pump()

        # 等待播放完成
        print("等待播放完成...")
        completed = self.wait_for_playback(5000)

        if completed:
            print("✓ 播放正常结束")
            self.test_results["playback_event_ok"] = True
        else:
            print("✗ 播放超时")
            audio.stop()

    def test_tts_event(self):
        """
        brief 测试 TTS 播报事件流转
        """
        print("\n" + "-" * 60)
        print("[测试 2] TTS 播报事件测试")
        print("-" * 60)

        audio = self.modules[0]

        # 发起 TTS 播报
        result = audio.play_tts("智能骑行头盔集成测试正常")
        print(f"\n发起 TTS: {'✓' if result else '✗'}")

        if not result:
            print("✗ TTS 发起失败")
            return

        # 等待播报完成
        print("等待 TTS 播报完成...")
        completed = self.wait_for_playback(5000)

        if completed:
            print("✓ TTS 播报正常结束")
            self.test_results["tts_event_ok"] = True
        else:
            print("✗ TTS 超时")
            audio.tts_stop()

    def test_stop_event(self):
        """
        brief 测试停止播放事件
        """
        print("\n" + "-" * 60)
        print("[测试 3] 停止播放事件测试")
        print("-" * 60)

        audio = self.modules[0]
        self.test_results["stop_event_ok"] = False

        # 开始播放
        result = audio.play_file(AUDIO_TEST_FILE)
        if not result:
            print("✗ 播放发起失败")
            return

        # 等一会儿让播放启动
        time.sleep_ms(300)
        self.event_bus.pump()

        # 立即停止
        result = audio.stop()
        time.sleep_ms(100)
        self.event_bus.pump()

        if not audio.get_is_playing():
            print("✓ 播放已停止")
            self.test_results["stop_event_ok"] = True
        else:
            print("✗ 停止失败")

    def test_config_update(self):
        """
        brief 测试动态配置更新
        """
        print("\n" + "-" * 60)
        print("[测试 4] 配置更新测试")
        print("-" * 60)

        audio = self.modules[0]
        self.test_results["config_update_ok"] = False

        # 发布配置更新事件：修改音量和语速
        print("\n发布配置更新事件:")
        print("  target: audio | speaker_volume: 4 | tts_speed: 80")
        self.event_bus.publish(EVENT_CONFIG_UPDATE, {
            "target": "audio",
            "speaker_volume": 4,
            "tts_speed": 80
        })

        self.event_bus.pump()
        time.sleep_ms(100)

        # 验证配置已更新
        if (audio.cfg["speaker_volume"] == 4 and
                audio.cfg["tts_speed"] == 80):
            print("✓ 配置更新成功")
            self.test_results["config_update_ok"] = True
        else:
            print(f"✗ 配置更新失败")
            print(f"  当前音量: {audio.cfg['speaker_volume']} (期望: 4)")
            print(f"  当前语速: {audio.cfg['tts_speed']} (期望: 80)")

    def print_summary(self):
        """
        brief 打印测试总结
        """
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)

        print("\n模块状态:")
        for mod in self.modules:
            status = mod.get_status()
            print(f"  {mod.name}:")
            print(f"    is_init:    {status['is_init']}")
            print(f"    err_count:  {status['err_count']}")

        print("\n测试结果:")
        results = [
            ("播放事件", self.test_results["playback_event_ok"]),
            ("播放完成", self.test_results["playback_end_ok"]),
            ("TTS 事件", self.test_results["tts_event_ok"]),
            ("停止事件", self.test_results["stop_event_ok"]),
            ("配置更新", self.test_results["config_update_ok"]),
        ]
        for name, ok in results:
            print(f"  {name}: {'✓' if ok else '✗'}")

        all_ok = all(v for v in self.test_results.values())
        print(f"\n总体评估: {'✅ 测试通过' if all_ok else '❌ 测试失败'}")
        print("=" * 60)

    def run(self):
        """
        brief 执行集成测试
        """
        try:
            self.setup()
            self.init_modules()

            self.test_playback_event()
            self.test_tts_event()
            self.test_stop_event()
            self.test_config_update()

            self.print_summary()

        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    test = IntegrationTest()
    test.run()
