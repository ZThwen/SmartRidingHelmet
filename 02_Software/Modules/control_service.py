"""
brief 统一控制服务（ControlService）
note Service层业务服务，接收BLE远端控制指令，发布事件到各模块响应

功能：
1. 订阅 EVENT_RIDE_CONTROL 事件（来自 BLE FFF3 写入）
2. 解析 JSON 控制指令
3. 发布对应控制事件（EVENT_LIGHT_CONTROL / EVENT_VOLUME_CONTROL / EVENT_ALARM_CONTROL）
4. 状态回推（EVENT_CONTROL_STATE_CHANGED）

架构：
    ControlService 不依赖任何具体模块，只通过 EventBus 发布事件
    各模块自行订阅事件并响应

数据流：
    小程序(按钮) → BLE FFF3 → EVENT_RIDE_CONTROL → ControlService → EVENT_xxx_CONTROL → 目标模块
    语音模块(未来) → UART → VoiceDriver → EVENT_VOICE_CMD → ControlService → EVENT_xxx_CONTROL → 目标模块
"""
import time
import json

from core.Base_Module import BaseModule
from core.config import (
    EVENT_RIDE_CONTROL, EVENT_CONTROL_STATE_CHANGED,
    EVENT_POWER_STATE_CHANGE, EVENT_VOICE_CMD,
    EVENT_LIGHT_CONTROL, EVENT_VOLUME_CONTROL, EVENT_ALARM_CONTROL,
    EVENT_MANUAL_ACTIVITY,
    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY,
    POWER_STATE_CUSTOM, EVENT_TTS_REQUEST,
    EVENT_TEMP_HUMID_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_BATTERY_READY, EVENT_HEARTRATE_READY,
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
    EVENT_LIGHT_BLINK_STATE, EVENT_SMS_PHONE_CONFIG,
    LIGHT_BRIGHTNESS_MAX, LIGHT_BRIGHTNESS_DEFAULT,
    CMD_TTS_MAP, PRIORITY_CTRL,
)

# CPython 兼容
try:
    _ticks_ms = time.ticks_ms
except AttributeError:
    def _ticks_ms():
        return int(time.time() * 1000)


class ControlService(BaseModule):
    """
    统一控制服务：BLE 远端 + 本地语音 → 统一入口 → 事件发布

    无模块依赖，只通过 EventBus 发布事件
    """

    _LIGHT_MODE_MAP = {"auto": 0, "manual": 1}
    _POWER_MODE_MAP = {"active": 0, "suspended": 1, "emergency": 2, "custom": 3}

    def __init__(self, event_bus=None, temp_humid=None, gnss=None, power_svc=None, heart_rate=None, ble_driver=None):
        """
        brief 初始化控制服务实例
        param event_bus: 事件总线实例引用
        param temp_humid: 温湿度驱动实例（可选，用于查询时强制读取）
        param gnss: GNSS驱动实例（可选，用于查询时强制读取）
        param power_svc: 电源管理服务实例（可选，用于查询电量）
        param heart_rate: 心率驱动实例（可选，用于查询时强制读取）
        param ble_driver: BLE驱动实例（可选，用于语音蓝牙控制）
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "control_service"
        self.temp_humid = temp_humid
        self.gnss = gnss
        self.power_svc = power_svc
        self.heart_rate = heart_rate
        self.ble_driver = ble_driver

        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            "brightness_step": 5,        # 亮度调节步长（5/50=10% 显示）
            "brightness_max": LIGHT_BRIGHTNESS_MAX,  # 最大亮度（%），满 PWM
            "volume_step": 1,            # 音量调节步长
            "volume_max": 5,             # 最大音量（对齐 AudioDriver 0-5）
            "volume_min": 0,             # 最小音量
            "default_brightness": LIGHT_BRIGHTNESS_DEFAULT,  # 开灯默认亮度
            "cmd_debounce_ms": 300,      # 指令防抖间隔 (ms)
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,
            "err_count": 0,
            "last_cmd_tick": 0,          # 上次指令时间戳（防抖）
            "last_tts_tick": 0,          # 上次 TTS 播报时间戳（防抖）
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "last_cmd": "",              # 上次执行的指令
            "last_cmd_source": "",       # 指令来源（ble / voice）
        }

        # 控制状态（乐观缓存，回推到小程序）
        self._control_state = {
            "light_mode": "auto",        # auto / manual
            "light_brightness": 0,       # 0-100
            "volume": 5,                 # 0-5（对齐 AudioDriver）
            "power_mode": "active",      # active / suspended / emergency
        }

        # 传感器数据缓存（供查询指令使用）
        self._sensor_cache = {
            "temperature": None,
            "humidity": None,
            "speed_kmh": None,
            "latitude": None,
            "longitude": None,
            "battery_level": None,
            "heart_rate": None,
            "spo2": None,
        }

        # 报警状态标志（查询时保护报警不被 TTS 中断）
        self._alarm_active = False

        # 报警前状态快照（报警取消后恢复）
        self._pre_alarm_state = None

        # 语音门控：_voice_active=False 时只响应 wake 指令
        self._voice_active = True

        # BLE 连接状态缓存
        self._ble_connected = False

        # 灯光闪烁状态（来自 LightService 事件）
        self._blink_active = False
        self._blink_duty = 0

        # 指令分发表 — 全部发布事件，不直接调用模块
        self._cmd_handlers = {
            "wake":           lambda: self._wake(),
            "light_on":       lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "on"}),
            "light_off":       lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "off"}),
            "light_auto":      lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "auto"}),
            "brightness_up":   lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "brightness_up"}),
            "brightness_down": lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "brightness_down"}),
            "volume_up":       lambda: self._pub(EVENT_VOLUME_CONTROL, {"cmd": "up"}),
            "volume_down":     lambda: self._pub(EVENT_VOLUME_CONTROL, {"cmd": "down"}),
            "alarm_cancel":    lambda: self._pub(EVENT_ALARM_CONTROL, {"cmd": "cancel"}),
            "alarm_sos":       lambda: self._pub(EVENT_ALARM_CONTROL, {"cmd": "sos"}),
            "alarm_stealth":   lambda: self._pub(EVENT_ALARM_CONTROL, {"cmd": "stealth"}),
            "power_save":      lambda: self._pub(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_SUSPENDED}),
            "power_normal":    lambda: self._pub(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_ACTIVE}),
            "power_emergency": lambda: self._pub(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_EMERGENCY}),
            "query_status":    lambda: self._query_status(),
            "query_speed":     lambda: self._query_speed(),
            "query_temp":      lambda: self._query_temp(),
            "query_humid":     lambda: self._query_humid(),
            "query_location":  lambda: self._query_location(),
            "query_battery":   lambda: self._query_battery(),
            "query_heartrate": lambda: self._query_heartrate(),
            "query_spo2":      lambda: self._query_spo2(),
            "ble_connect":     lambda: self._ble_connect(),
            "ble_disconnect":  lambda: self._ble_disconnect(),
            "voice_sleep":     lambda: self._sleep_voice(),
            "light_blink":     lambda: self._pub(EVENT_LIGHT_CONTROL, {"cmd": "blink"}),

            # SMS 手机号配置
            "set_phone":       lambda: self._set_phone(),
        }

    def init(self):
        """
        brief 初始化服务：订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_RIDE_CONTROL, self._on_ride_control)
                self.event_bus.subscribe(EVENT_VOICE_CMD, self._on_voice_cmd)
                self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid)
                self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)
                self.event_bus.subscribe(EVENT_BATTERY_READY, self._on_battery)
                self.event_bus.subscribe(EVENT_HEARTRATE_READY, self._on_heartrate)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_power_state)
                self.event_bus.subscribe(EVENT_BLE_CONNECTED, self._on_ble_connected)
                self.event_bus.subscribe(EVENT_BLE_DISCONNECTED, self._on_ble_disconnected)
                self.event_bus.subscribe(EVENT_LIGHT_BLINK_STATE, self._on_light_blink_state)

            self.ctx["is_init"] = True
            print("[{}] OK init".format(self.name))

        except Exception as e:
            print("[{}] FAIL init: {}".format(self.name, e))
            raise

    def tick(self):
        """
        brief 周期调度：纯事件驱动，tick()为空实现
        """
        self.ctx["last_hb"] = time.ticks_ms()

    # ==================== 事件发布 ====================

    def _pub(self, event, payload):
        """
        brief 发布事件到 EventBus
        param event: 事件名称常量
        param payload: 事件负载 dict
        """
        if self.event_bus:
            self.event_bus.publish(event, payload)

    # ==================== 事件回调 ====================

    def _on_ride_control(self, payload):
        """
        brief BLE 远端控制事件回调
        param payload: {"raw": "{\"a\":\"ctrl\",\"d\":{\"cmd\":\"light_on\"}}"}
        """
        raw = payload.get("raw", "")
        try:
            cmd_obj = json.loads(raw)
        except Exception as e:
            print("[{}] JSON解析失败: {} | raw={}".format(
                self.name, e, str(raw)[:50]))
            self.ctx["err_count"] += 1
            return

        if cmd_obj.get("a") != "ctrl":
            return

        d = cmd_obj.get("d", {})
        cmd = d.get("cmd", "")

        # 提取额外参数（如 phone 字段），排除 cmd 本身
        params = {}
        for k, v in d.items():
            if k != "cmd":
                params[k] = v

        self._execute_cmd(cmd, source="ble", params=params)

    def _on_voice_cmd(self, payload):
        """
        brief 语音指令事件回调（等 VoiceDriver 就绪后启用）
        param payload: {"cmd": "light_on", "id": 1}
        """
        cmd = payload.get("cmd", "")
        # 语音门控：非 wake 指令且语音休眠时忽略
        if cmd != "wake" and not self._voice_active:
            return
        self._execute_cmd(cmd, source="voice")

    # ==================== 指令执行 ====================

    def _execute_cmd(self, cmd, source="unknown", params=None):
        """
        brief 执行控制指令（统一入口）
        param cmd: 指令字符串
        param source: 指令来源（ble / voice）
        param params: 额外参数 dict（如 set_phone 的 phone 字段）
        """
        if not cmd:
            return

        # 防抖
        now = _ticks_ms()
        if time.ticks_diff(now, self.ctx["last_cmd_tick"]) < self.cfg["cmd_debounce_ms"]:
            return

        # 保存参数供 handler 使用
        if params:
            self._data["last_params"] = params

        handler = self._cmd_handlers.get(cmd)
        if handler:
            try:
                # 先处理省电模式覆盖（在发布控制事件之前）
                if cmd not in ("power_save", "power_normal", "power_emergency",
                               "alarm_sos", "alarm_cancel", "alarm_stealth") and not cmd.startswith("query_"):
                    if self._control_state["power_mode"] != "active":
                        self._control_state["power_mode"] = "custom"
                        if self.event_bus:
                            self.event_bus.publish(EVENT_POWER_STATE_CHANGE, {"power_state": POWER_STATE_CUSTOM})

                    # 通知 PowerService：用户手动操作，暂停自动省电
                    if self.event_bus:
                        self.event_bus.publish(EVENT_MANUAL_ACTIVITY, {
                            "cmd": cmd, "source": source
                        })

                handler()
                self.ctx["last_cmd_tick"] = now
                self._data["last_cmd"] = cmd
                self._data["last_cmd_source"] = source
                # 乐观更新本地状态缓存
                self._update_control_state(cmd)
                self._maybe_tts(cmd)
                self._push_state()
                print("[{}] cmd={} src={}".format(self.name, cmd, source))
            except Exception as e:
                self.ctx["err_count"] += 1
                print("[{}] cmd执行异常: {} | cmd={}".format(
                    self.name, e, cmd))
        else:
            print("[{}] unknown cmd: {}".format(self.name, cmd))

    # ==================== 状态乐观更新 ====================

    def _update_control_state(self, cmd):
        """
        brief 根据指令乐观更新本地状态缓存
        note 不依赖模块回推，足够小程序 UI 使用
        """
        if cmd == "light_on":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = self.cfg["default_brightness"]
        elif cmd == "light_off":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = 0
        elif cmd == "brightness_up":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = min(
                self._control_state["light_brightness"] + self.cfg["brightness_step"],
                self.cfg["brightness_max"])
        elif cmd == "brightness_down":
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = max(
                self._control_state["light_brightness"] - self.cfg["brightness_step"], 0)
        elif cmd == "light_auto":
            self._control_state["light_mode"] = "auto"
        elif cmd == "volume_up":
            self._control_state["volume"] = min(
                self._control_state["volume"] + self.cfg["volume_step"],
                self.cfg["volume_max"])
        elif cmd == "volume_down":
            self._control_state["volume"] = max(
                self._control_state["volume"] - self.cfg["volume_step"],
                self.cfg["volume_min"])
        elif cmd == "power_save":
            self._control_state["power_mode"] = "suspended"
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = 0
            self._pub(EVENT_LIGHT_CONTROL, {"cmd": "off"})
        elif cmd == "power_normal":
            self._control_state["power_mode"] = "active"
        elif cmd == "power_emergency":
            self._control_state["power_mode"] = "emergency"
            self._control_state["light_mode"] = "manual"
            self._control_state["light_brightness"] = 0
            self._pub(EVENT_LIGHT_CONTROL, {"cmd": "off"})
        elif cmd == "light_blink":
            self._control_state["light_mode"] = "manual"

    # ==================== 传感器缓存回调 ====================

    def _on_temp_humid(self, payload):
        if payload.get("valid"):
            self._sensor_cache["temperature"] = payload.get("temp")
            self._sensor_cache["humidity"] = payload.get("humid")

    def _on_gnss(self, payload):
        if payload.get("valid"):
            self._sensor_cache["speed_kmh"] = payload.get("speed_kmh")
            self._sensor_cache["latitude"] = payload.get("latitude")
            self._sensor_cache["longitude"] = payload.get("longitude")

    def _on_battery(self, payload):
        if payload.get("valid"):
            self._sensor_cache["battery_level"] = payload.get("level")

    def _on_heartrate(self, payload):
        """brief 缓存心率血氧数据，供语音查询使用"""
        if payload.get("valid"):
            self._sensor_cache["heart_rate"] = payload.get("heart_rate")
            self._sensor_cache["spo2"] = payload.get("spo2")

    def _on_power_state(self, payload):
        """
        brief 电源状态变更回调（来自 PowerService 或其他模块）
        note 更新本地状态缓存并推送到小程序
        param payload: {"power_state": "ACTIVE"|"SUSPENDED"|"EMERGENCY"|"CUSTOM"}
        """
        new_state = payload.get("power_state", POWER_STATE_ACTIVE)
        # 映射大写常量到 UI 字符串
        mode_map = {
            POWER_STATE_ACTIVE: "active",
            POWER_STATE_SUSPENDED: "suspended",
            POWER_STATE_EMERGENCY: "emergency",
            POWER_STATE_CUSTOM: "custom",
        }
        mapped = mode_map.get(new_state, "active")
        if self._control_state["power_mode"] != mapped:
            old_mode = self._control_state["power_mode"]
            self._control_state["power_mode"] = mapped
            self._push_state()  # 推送到 BLE → 小程序
            print("[%s] power_mode: %s -> %s" % (self.name, old_mode, mapped))

    def _on_alarm_triggered(self, payload):
        """保存报警前状态快照"""
        self._pre_alarm_state = dict(self._control_state)
        self._alarm_active = True

    def _on_alarm_canceled(self, payload):
        """恢复报警前状态"""
        self._alarm_active = False
        self._tts("报警已取消")  # alarm_active 已清除，TTS 不被阻塞
        if self._pre_alarm_state:
            self._control_state.update(self._pre_alarm_state)
            self._pre_alarm_state = None
            self._push_state()  # 推送恢复后的状态到 BLE

    # ==================== BLE 状态 & 语音控制 ====================

    def _on_ble_connected(self, payload):
        """缓存 BLE 连接状态"""
        self._ble_connected = True

    def _on_ble_disconnected(self, payload):
        """缓存 BLE 断开状态"""
        self._ble_connected = False

    def _on_light_blink_state(self, payload):
        """brief 缓存灯光闪烁状态并推送 BLE"""
        self._blink_active = payload.get("blink", False)
        self._blink_duty = payload.get("duty", 0)
        self._push_state()

    def _wake(self):
        """唤醒语音系统"""
        self._voice_active = True
        # TTS "小洛包在，有什么指示" 由 CMD_TTS_MAP 自动处理

    def _sleep_voice(self):
        """语音休眠：停止接收语音指令"""
        self._voice_active = False
        # TTS "好的" 由 CMD_TTS_MAP 自动处理

    def _ble_connect(self):
        """语音蓝牙连接"""
        if self._ble_connected:
            self._tts("蓝牙已连接")
            return
        # 未初始化（is_init=False）时 connect 内部会自动 init；已初始化时直接广播
        if self.ble_driver:
            self.ble_driver.connect()
        self._tts("蓝牙正在连接")

    def _ble_disconnect(self):
        """语音蓝牙断开"""
        if self.ble_driver and self.ble_driver.ctx.get("is_init", False):
            self.ble_driver.deinit()
        # TTS "蓝牙已断开" 由 CMD_TTS_MAP 自动处理

    # ==================== 查询指令 ====================

    def _tts(self, text):
        if self._alarm_active:
            print("[{}] TTS blocked during alarm".format(self.name))
            return
        if self.event_bus:
            self.event_bus.publish(EVENT_TTS_REQUEST, {"text": text, "priority": PRIORITY_CTRL})

    def _query_status(self):
        cs = self._control_state
        parts = []
        if cs["light_mode"] == "auto":
            parts.append("灯光自动模式")
        else:
            parts.append("灯光亮度百分之%d" % cs["light_brightness"])
        parts.append("音量%d" % cs["volume"])
        mode_map = {"active": "正常模式", "suspended": "省电模式",
                    "emergency": "超级省电", "custom": "自定义模式"}
        parts.append(mode_map.get(cs["power_mode"], cs["power_mode"]))
        self._tts("，".join(parts))

    def _query_speed(self):
        speed = self._sensor_cache.get("speed_kmh")
        if speed is None and self.gnss:
            try:
                data = self.gnss.force_read()
                if data and data.get("valid"):
                    speed = data.get("speed_kmh")
                    self._sensor_cache["speed_kmh"] = speed
                    self._sensor_cache["latitude"] = data.get("latitude")
                    self._sensor_cache["longitude"] = data.get("longitude")
            except:
                pass
        if speed is not None:
            self._tts("当前时速%d公里" % int(speed))
        else:
            self._tts("速度信息暂不可用")

    def _query_temp(self):
        temp = self._sensor_cache.get("temperature")
        if temp is None and self.temp_humid:
            try:
                data = self.temp_humid.force_read()
                if data and data.get("valid"):
                    temp = data.get("temp")
                    self._sensor_cache["temperature"] = temp
                    self._sensor_cache["humidity"] = data.get("humid")
            except:
                pass
        if temp is not None:
            self._tts("当前温度%d度" % int(temp))
        else:
            self._tts("温度信息暂不可用")

    def _query_humid(self):
        humid = self._sensor_cache.get("humidity")
        if humid is None and self.temp_humid:
            try:
                data = self.temp_humid.force_read()
                if data and data.get("valid"):
                    humid = data.get("humid")
                    self._sensor_cache["humidity"] = humid
                    self._sensor_cache["temperature"] = data.get("temp")
            except:
                pass
        if humid is not None:
            self._tts("当前湿度百分之%d" % int(humid))
        else:
            self._tts("湿度信息暂不可用")

    def _query_location(self):
        lat = self._sensor_cache.get("latitude")
        lon = self._sensor_cache.get("longitude")
        if (lat is None or lon is None) and self.gnss:
            try:
                data = self.gnss.force_read()
                if data and data.get("valid"):
                    lat = data.get("latitude")
                    lon = data.get("longitude")
                    self._sensor_cache["latitude"] = lat
                    self._sensor_cache["longitude"] = lon
                    self._sensor_cache["speed_kmh"] = data.get("speed_kmh")
            except:
                pass
        if lat is not None and lon is not None:
            self._tts("当前位置北纬%.4f东经%.4f" % (lat, lon))
        else:
            self._tts("位置信息暂不可用")

    def _query_battery(self):
        level = self._sensor_cache.get("battery_level")
        if level is not None:
            if self._alarm_active:
                return
            if self.event_bus:
                self.event_bus.publish(EVENT_TTS_REQUEST, {
                    "text": "当前电量%d档" % level,
                    "priority": PRIORITY_CTRL,
                })
        else:
            self._tts("电量信息暂不可用")

    def _query_heartrate(self):
        hr = self._sensor_cache.get("heart_rate")
        if hr is None and self.heart_rate:
            try:
                data = self.heart_rate.force_read()
                if data and data.get("valid"):
                    hr = data.get("heart_rate")
                    self._sensor_cache["heart_rate"] = hr
                    self._sensor_cache["spo2"] = data.get("spo2")
            except:
                pass
        if hr is not None:
            self._tts("当前心率%d次每分钟" % hr)
        else:
            self._tts("心率数据暂不可用")

    def _query_spo2(self):
        spo2 = self._sensor_cache.get("spo2")
        if spo2 is None and self.heart_rate:
            try:
                data = self.heart_rate.force_read()
                if data and data.get("valid"):
                    spo2 = data.get("spo2")
                    self._sensor_cache["spo2"] = spo2
                    self._sensor_cache["heart_rate"] = data.get("heart_rate")
            except:
                pass
        if spo2 is not None:
            self._tts("当前血氧饱和度百分之%d" % spo2)
        else:
            self._tts("血氧数据暂不可用")

    def _set_phone(self):
        """
        brief 配置 SMS 报警手机号
        note BLE 传入 {"a":"ctrl","d":{"cmd":"set_phone","phone":"13800138000"}}
        """
        params = self._data.get("last_params", {})
        phone = params.get("phone", "")

        if not phone or len(phone) != 11:
            print("[control_service] set_phone: invalid phone=%s" % phone)
            if self.event_bus:
                self.event_bus.publish(EVENT_TTS_REQUEST, {
                    "text": "手机号格式错误", "priority": PRIORITY_CTRL
                })
            return

        if self.event_bus:
            self.event_bus.publish(EVENT_SMS_PHONE_CONFIG, {
                "phone": phone,
                "timestamp": _ticks_ms()
            })
            print("[control_service] set_phone: phone configured %s" % phone)

    # ==================== 状态回推 ====================

    def _push_state(self):
        """
        brief 推送控制状态到 BLE（通过 EventBus）
        note 合并为 1 条消息，每条 ≤25 字节（ATT_MTU 限制）
        """
        if not self.event_bus:
            return
        cs = self._control_state
        f = 1 if self._blink_active else 0
        b = self._blink_duty if self._blink_active else cs["light_brightness"]
        self.event_bus.publish(EVENT_CONTROL_STATE_CHANGED,
            {"t": 7, "m": self._LIGHT_MODE_MAP.get(cs["light_mode"], 0),
             "b": b,
             "v": cs["volume"],
             "p": self._POWER_MODE_MAP.get(cs["power_mode"], 0),
             "f": f})

    # ==================== TTS 反馈 ====================

    def _maybe_tts(self, cmd):
        """
        brief 控制指令 TTS 播报（1 秒防抖，只播报最终状态）
        param cmd: 指令字符串
        """
        if self._alarm_active:
            return
        now = _ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tts_tick"]) < 1000:
            return
        self.ctx["last_tts_tick"] = now
        tts_text = CMD_TTS_MAP.get(cmd)
        if tts_text and self.event_bus:
            self.event_bus.publish(EVENT_TTS_REQUEST, {"text": tts_text, "priority": PRIORITY_CTRL})

    # ==================== 数据接口 ====================

    def get_data(self):
        """
        brief 获取控制数据快照
        return dict {last_cmd, last_cmd_source, control_state, timestamp}
        """
        return {
            "last_cmd": self._data["last_cmd"],
            "last_cmd_source": self._data["last_cmd_source"],
            "control_state": dict(self._control_state),
            "timestamp": _ticks_ms(),
        }

    def get_status(self):
        """
        brief 获取运行状态快照
        return dict {is_init, err_count, control_state}
        """
        return {
            "is_init": self.ctx["is_init"],
            "err_count": self.ctx["err_count"],
            "control_state": dict(self._control_state),
        }
