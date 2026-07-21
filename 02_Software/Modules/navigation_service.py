"""
brief 导航指令服务 - 接收BLE导航指令，TTS播报 + LCD显示
note Service层业务服务，MicroPython环境，在真实硬件上运行

功能：
1. 订阅 EVENT_NAV_CMD 事件（来自 BLE FFF2 写入）
2. 解析 JSON 导航指令（方向、距离、路名）
3. 调用 Audio.play_tts() 播报中文导航
4. 在 LCD 底部 (y=110) 写导航摘要行

数据流：
    小程序(Tencent Map) → BLE FFF2 → EVENT_NAV_CMD → NavigationService → TTS + LCD
"""
import time
import json
from core.Base_Module import BaseModule
from core.config import (
    EVENT_NAV_CMD, EVENT_TTS_REQUEST, EVENT_NAV_DISPLAY,
    EVENT_POWER_STATE_CHANGE, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    POWER_STATE_ACTIVE, POWER_STATE_EMERGENCY,
    PRIORITY_NAV,
    TTS_NAV_ARRIVE, TTS_NAV_CANCEL,
)

# CPython 兼容：MicroPython 有 time.ticks_ms()，CPython 没有
try:
    _ticks_ms = time.ticks_ms
except AttributeError:
    def _ticks_ms():
        return int(time.time() * 1000)

# 方向映射：Tencent Maps action → 中文
_DIR_MAP = {
    "left":        "左转",
    "right":       "右转",
    "straight":    "直行",
    "slight_left":  "靠左",
    "slight_right": "靠右",
    "uturn":       "掉头",
    "arrive":      "到达目的地",
    "cancel":      "导航结束",
}

# LCD 方向符号
_DIR_SYMBOL = {
    "left":        "<",
    "right":       ">",
    "straight":    "^",
    "slight_left":  "<",
    "slight_right": ">",
    "uturn":       "U",
    "arrive":      "*",
    "cancel":      "x",
}


def _map_direction(dir_str):
    """方向字符串映射为中文，未知方向 fallback 为"直行" """
    return _DIR_MAP.get(dir_str, "直行")


def _build_tts_text(dir_str, dist, road):
    """
    构造 TTS 播报文本
    有路名: "前方200米右转进入中山路"
    无路名: "前方200米右转"
    到达:   "已到达目的地"
    取消:   "导航已结束"
    """
    if dir_str == "arrive":
        return TTS_NAV_ARRIVE
    if dir_str == "cancel":
        return TTS_NAV_CANCEL

    cn_dir = _map_direction(dir_str)
    if road:
        return "前方%d米%s进入%s" % (dist, cn_dir, road)
    else:
        return "前方%d米%s" % (dist, cn_dir)


def _build_lcd_text(dir_str, dist, road=None):
    """
    构造 LCD 导航行文本（纯 ASCII 高对比，配合高亮色块）
    left:         "<<<  LEFT  200m"
    right:        "RIGHT  200m  >>>"
    straight:     "^^^ STRAIGHT 500m"
    slight_left:  "<<  KEEP LEFT 150m"
    slight_right: "KEEP RIGHT 150m >>"
    uturn:        "U-TURN  100m"
    arrive:       "*** ARRIVED ***"
    cancel:       "--- NAV END ---"
    """
    if dir_str == "arrive":
        return "*** ARRIVED ***"
    if dir_str == "cancel":
        return "--- NAV END ---"

    if dir_str == "left":
        return "<<<  LEFT  %dm" % dist
    elif dir_str == "right":
        return "RIGHT  %dm  >>>" % dist
    elif dir_str == "slight_left":
        return "<<  KEEP LEFT %dm" % dist
    elif dir_str == "slight_right":
        return "KEEP RIGHT %dm >>" % dist
    elif dir_str == "uturn":
        return "U-TURN  %dm" % dist
    elif dir_str == "straight":
        return "^^^ STRAIGHT %dm" % dist
    else:
        sym = _DIR_SYMBOL.get(dir_str, "^")
        return "%s %dm" % (sym, dist)


class NavigationService(BaseModule):
    """
    导航指令服务：接收BLE导航指令，TTS播报 + LCD显示

    事件流：
        EVENT_NAV_CMD → 解析JSON → TTS + LCD

    注入依赖：
        audio_driver: AudioDriver.play_tts() 播报
    """

    def __init__(self, event_bus=None, audio_driver=None):
        """
        brief 初始化导航指令服务实例
        param event_bus: 事件总线实例引用
        param audio_driver: Audio 驱动实例（由主循环创建后注入）
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "navigation"

        self.audio_driver = audio_driver

        self.cfg = {
            "sample_ms": 1000,       # tick 检查间隔
        }

        self.ctx = {
            "is_init": False,
            "is_navigating": False,
            "current_dir": "",
            "current_dist": 0,
            "current_road": "",
            "last_tick": 0,
            "err_count": 0,
            "nav_paused": False,
            "power_state": "ACTIVE",
            "alarm_active": False,
            "alarm_type": "",
        }

        self._stealth_active = False

        self._data = {
            "is_navigating": False,
            "current_dir": "",
            "current_dist": 0,
            "current_road": "",
            "last_tts": "",
            "last_lcd": "",
        }

    def init(self):
        """初始化：订阅事件，启动 TTS 工作线程"""
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_NAV_CMD, self._on_nav_cmd)
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_power_state_change)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)

            self.ctx["is_init"] = True
            print("[{}] 初始化完成".format(self.name))

        except Exception as e:
            print("[{}] 初始化失败: {}".format(self.name, e))
            raise

    def tick(self):
        """事件驱动，无需轮询"""
        self.ctx["last_hb"] = time.ticks_ms()

    def _on_power_state_change(self, payload):
        """电源状态变化回调"""
        new_state = payload.get("power_state")
        self.ctx["power_state"] = new_state
        if new_state == POWER_STATE_EMERGENCY:
            self.ctx["nav_paused"] = True
            if self.ctx["is_navigating"]:
                self.ctx["is_navigating"] = False
                print("[{}] 导航暂停（紧急省电）".format(self.name))
        elif new_state == POWER_STATE_ACTIVE:
            if self.ctx["nav_paused"]:
                self.ctx["nav_paused"] = False
                self.ctx["is_navigating"] = True
                print("[{}] 导航恢复".format(self.name))

    def _on_alarm_triggered(self, payload):
        """报警触发回调"""
        self.ctx["alarm_active"] = True
        self.ctx["alarm_type"] = payload.get("alarm_type", "collision")
        self._stealth_active = (self.ctx["alarm_type"] == "stealth")

    def _on_alarm_canceled(self, payload):
        """报警取消回调"""
        self.ctx["alarm_active"] = False
        self.ctx["alarm_type"] = ""
        self._stealth_active = False

    def _on_nav_cmd(self, payload):
        """
        处理导航指令事件
        payload: {"raw": "{\"a\":\"nav\",\"d\":{\"dir\":\"right\",\"dist\":200,\"road\":\"中山路\"}}"}
        """
        # EMERGENCY 模式或暂停状态：忽略导航指令
        if self.ctx.get("power_state") == POWER_STATE_EMERGENCY or self.ctx.get("nav_paused"):
            return

        print("[nav] 收到事件: %s" % str(payload)[:80])
        raw = payload.get("raw", "")
        try:
            cmd = json.loads(raw)
        except Exception as e:
            print("[nav] JSON解析失败: %s | raw=%s" % (e, str(raw)[:50]))
            self.ctx["err_count"] += 1
            return

        action = cmd.get("a", "")
        if action != "nav":
            return

        d = cmd.get("d", {})
        dir_str = d.get("dir", "straight")
        dist = d.get("dist", 0)
        road = d.get("road", "")

        # 更新状态
        self.ctx["current_dir"] = dir_str
        self.ctx["current_dist"] = dist
        self.ctx["current_road"] = road

        if dir_str in ("arrive", "cancel"):
            self.ctx["is_navigating"] = False
        else:
            self.ctx["is_navigating"] = True

        # 同步到 _data
        self._data["is_navigating"] = self.ctx["is_navigating"]
        self._data["current_dir"] = dir_str
        self._data["current_dist"] = dist
        self._data["current_road"] = road

        # TTS 播报（通过 EventBus 发布，由 AudioService 统一调度优先级）
        # 静默报警：跳过 TTS
        if self.ctx.get("alarm_active") and self.ctx.get("alarm_type") == "stealth":
            pass  # 静默报警期间不播放导航 TTS
        elif self._stealth_active:
            pass  # 备份检查
        else:
            tts_text = _build_tts_text(dir_str, dist, road)
            self._data["last_tts"] = tts_text
            print("[nav] TTS: %s" % tts_text)

            # 发布 TTS 请求事件（由 AudioService 统一调度）
            if self.event_bus:
                self.event_bus.publish(EVENT_TTS_REQUEST, {
                    "text": tts_text,
                    "priority": PRIORITY_NAV,
                })

        # LCD 显示（通过 EventBus 发布，由 DisplayService 统一管理渲染和写入）
        lcd_text = _build_lcd_text(dir_str, dist, road)
        self._data["last_lcd"] = lcd_text
        print("[nav] LCD: %s" % lcd_text)

        # 发布导航显示事件（DisplayService 订阅并缓存，渲染时恢复）
        if self.event_bus:
            self.event_bus.publish(EVENT_NAV_DISPLAY, {
                "text": lcd_text,
                "action": dir_str,
                "dist": dist
            })

    def get_data(self):
        """获取当前导航数据"""
        return {
            "is_navigating": self._data["is_navigating"],
            "current_dir": self._data["current_dir"],
            "current_dist": self._data["current_dist"],
            "current_road": self._data["current_road"],
            "last_tts": self._data["last_tts"],
            "last_lcd": self._data["last_lcd"],
            "timestamp": _ticks_ms(),
        }

    def get_status(self):
        """获取模块运行状态"""
        return {
            "is_init": self.ctx["is_init"],
            "is_navigating": self.ctx["is_navigating"],
            "current_dir": self.ctx["current_dir"],
            "current_dist": self.ctx["current_dist"],
            "current_road": self.ctx["current_road"],
            "err_count": self.ctx["err_count"],
        }
