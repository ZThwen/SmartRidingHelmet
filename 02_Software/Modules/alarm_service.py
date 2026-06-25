"""
brief 报警联动服务（AlarmService）
note 接收碰撞/SOS/GPS丢失等事件，协调 LED + Audio 驱动完成声光报警
      报警超时自动取消，SW按钮双击语义：空闲→SOS，报警中→取消
      Device 驱动由构造函数注入，LCD 交由 DisplayService 负责
"""
import math
import time
import _thread

from core.Base_Module import BaseModule
from core.config import (
    EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    EVENT_COLLISION_DETECTED, EVENT_BUTTON_PRESSED,
    EVENT_BATTERY_LOW, EVENT_BATTERY_CRITICAL, EVENT_GPS_LOST,
    EVENT_SMS_PHONE_CONFIG, EVENT_GNSS_READY,
    EVENT_CONFIG_UPDATE, EVENT_ALARM_CONTROL, EVENT_POWER_STATE_CHANGE,
    ALARM_DURATION_MS, ALARM_ENABLE_LOCAL,
    AUDIO_ALARM_FILE_L1, AUDIO_ALARM_FILE_L2, AUDIO_ALARM_FILE_L3,
    AUDIO_SOS_FILE,
    TTS_BATTERY_LOW, TTS_BATTERY_CRITICAL, TTS_GPS_LOST,
    POWER_STATE_ACTIVE,
    EVENT_HEARTRATE_READY, EVENT_TTS_REQUEST, PRIORITY_ALARM, PRIORITY_CTRL,
    HEARTRATE_HIGH_THRESHOLD, HEARTRATE_LOW_THRESHOLD,
    HEARTRATE_SPO2_LOW_THRESHOLD,
    HEARTRATE_TTS_HIGH, HEARTRATE_TTS_LOW, HEARTRATE_SPO2_TTS_LOW,
    HEARTRATE_ALERT_COOLDOWN_MS,
)


class AlarmService(BaseModule):
    def __init__(self, event_bus=None, led=None, audio=None, sms=None):
        """
        brief 初始化报警联动服务实例
        param event_bus: 事件总线实例引用
        param led: LED 驱动实例（由主循环创建后注入）
        param audio: Audio 驱动实例（由主循环创建后注入）
        param sms: SMS 驱动实例（由主循环创建后注入，用于发送报警短信）
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "alarm"

        # 注入的 Device 引用（可为 None，调用处有 None guard）
        self.led = led
        self.audio = audio
        self._sms_driver = sms

        # ======================= cfg：静态配置 =======================
        self.cfg = {
            "alarm_duration_ms": ALARM_DURATION_MS,
            "check_interval_ms": 100,
            "enable_local": ALARM_ENABLE_LOCAL,
        }

        # ======================= ctx：运行时上下文 =======================
        self.ctx = {
            "is_init": False,
            "last_tick": 0,
            "power_state": POWER_STATE_ACTIVE,
            "alarm_active": False,
            "alarm_type": "",
            "alarm_level": 0,
            "alarm_start": 0,
            "hr_alert_tick": 0,
        }

        # SMS 配置与 GPS 缓存
        self._sms_phone = None           # 存储配置的手机号（从 BLE 接收）
        self._gnss_cache = {}            # 缓存最新 GNSS 坐标（事件驱动更新）

        # ======================= _data：数据快照 =======================
        self._data = {
            "last_alarm": {},
        }

    def init(self):
        """
        brief 初始化服务：订阅事件 + 重置报警状态
        """
        try:
            if self.event_bus:
                self.event_bus.subscribe(EVENT_COLLISION_DETECTED, self._on_collision)
                self.event_bus.subscribe(EVENT_BUTTON_PRESSED, self._on_button_press)
                self.event_bus.subscribe(EVENT_GPS_LOST, self._on_gps_lost)
                self.event_bus.subscribe(EVENT_BATTERY_LOW, self._on_battery_low)
                self.event_bus.subscribe(EVENT_BATTERY_CRITICAL, self._on_battery_critical)
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_config_update)
                self.event_bus.subscribe(EVENT_ALARM_CONTROL, self._on_alarm_control)
                self.event_bus.subscribe(EVENT_HEARTRATE_READY, self._on_heartrate)
                self.event_bus.subscribe(EVENT_SMS_PHONE_CONFIG, self._on_sms_phone_config)
                self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)

            self.ctx["alarm_active"] = False
            self.ctx["alarm_type"] = ""
            self.ctx["alarm_level"] = 0
            self.ctx["alarm_start"] = 0
            self.ctx["is_init"] = True
            print("[%s] OK init" % self.name)

        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise

    def tick(self):
        """
        brief 周期调度：超时检查 + 时间片控制
        note 30s 超时精度 ±100ms，完全满足需求
             超时检查不受电源模式限制（碰撞报警必须能自动取消）
        """
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["check_interval_ms"]:
            return

        if self.ctx["alarm_active"]:
            # 只有 collision 类型才自动取消，SOS 和 stealth 需要手动取消
            if self.ctx["alarm_type"] == "collision":
                if time.ticks_diff(now, self.ctx["alarm_start"]) >= self.cfg["alarm_duration_ms"]:
                    self._cancel_alarm()

        self.ctx["last_tick"] = now

    # ==================== 核心方法 ====================

    def _start_alarm(self, alarm_type, level):
        """
        brief 启动报警（所有报警入口统一经过此方法）
        param alarm_type: "collision" / "sos"
        param level: 1-3
        note
            - 同类型且 level<3 → 仅刷新超时计时器
            - Level 3 碰撞 → 升级为 sos
            - SOS 打断碰撞 → 先 cancel 再重启 SOS
        """
        if alarm_type == "collision" and level >= 3:
            alarm_type = "sos"

        if self.ctx["alarm_active"]:
            if alarm_type == self.ctx["alarm_type"]:
                self.ctx["alarm_start"] = time.ticks_ms()
                return
            if alarm_type != self.ctx["alarm_type"]:
                self._cancel_alarm()

        self.ctx["alarm_active"] = True
        self.ctx["alarm_type"] = alarm_type
        self.ctx["alarm_level"] = level
        self.ctx["alarm_start"] = time.ticks_ms()

        if self.cfg["enable_local"]:
            if alarm_type == "collision":
                if self.led:
                    self.led.blink(self.cfg["alarm_duration_ms"],
                                   self._level_to_interval(level))
                if self.audio:
                    self.audio.play_file(self._level_to_file(level))
            elif alarm_type == "sos":
                if self.led:
                    self.led.blink(self.cfg["alarm_duration_ms"], 200)
                if self.audio:
                    self.audio.play_tts("SOS 报警已触发")

        if self.event_bus:
            self.event_bus.publish(EVENT_ALARM_TRIGGERED, {
                "alarm_type": alarm_type,
                "level": level,
                "timestamp": time.ticks_ms(),
            })

        # 所有报警都发送 SMS（后台线程，不阻塞主循环）
        if self._sms_phone and self._sms_driver:
            msg = self._build_sms_message(level)
            print("[%s] 发送 SMS 到 %s: %s" % (self.name, self._sms_phone, msg))
            try:
                _thread.start_new_thread(self._sms_driver.send_sms, (self._sms_phone, msg))
            except Exception as e:
                print("[%s] SMS 线程启动失败: %s" % (self.name, e))

    def _cancel_alarm(self):
        """
        brief 取消报警：关闭声光 + 发布取消事件 + 重置状态
        """
        if not self.ctx["alarm_active"]:
            return

        if self.led:
            self.led.off()
        if self.audio:
            self.audio.stop()

        if self.event_bus:
            self.event_bus.publish(EVENT_ALARM_CANCELED, {
                "duration": time.ticks_diff(
                    time.ticks_ms(), self.ctx["alarm_start"]),
                "timestamp": time.ticks_ms(),
            })

        self.ctx["alarm_active"] = False
        self.ctx["alarm_type"] = ""
        self.ctx["alarm_level"] = 0
        self.ctx["alarm_start"] = 0

    def cancel_alarm(self):
        """
        brief 外部取消报警（供 ControlService 调用）
        note 公开接口，与 _cancel_alarm 逻辑一致
        """
        self._cancel_alarm()

    def trigger_sos(self):
        """
        brief 触发 SOS 报警（供 ControlService 远端调用）
        note LED 快闪 + SOS 音，与物理按钮触发逻辑一致
        """
        self._start_alarm("sos", 3)

    def trigger_stealth_alarm(self):
        """
        brief 触发静默报警（无 LED 无声音）
        note 仅发布 EVENT_ALARM_TRIGGERED 供 BLE 通知手机
              适用于用户不想引起注意但需要记录的场景
        """
        # 先取消已有报警（如果有）
        if self.ctx["alarm_active"]:
            self._cancel_alarm()

        self.ctx["alarm_active"] = True
        self.ctx["alarm_type"] = "stealth"
        self.ctx["alarm_level"] = 1
        self.ctx["alarm_start"] = time.ticks_ms()

        # 不触发声光，只发布事件
        if self.event_bus:
            self.event_bus.publish(EVENT_ALARM_TRIGGERED, {
                "alarm_type": "stealth",
                "level": 1,
                "timestamp": time.ticks_ms(),
            })

        print("[{}] stealth alarm triggered".format(self.name))

    # ==================== 事件回调 ====================

    def _on_collision(self, payload):
        """碰撞检测事件回调"""
        level = payload.get("level", 1)
        self._start_alarm("collision", level)

    def _on_button_press(self, payload):
        """
        brief 按键事件回调（双重语义）
        note 空闲时=触发SOS，报警中=取消报警
        """
        if self.ctx["alarm_active"]:
            self._cancel_alarm()
        else:
            self._start_alarm("sos", 3)

    def _on_gps_lost(self, payload):
        """GPS 信号丢失→TTS 语音提示"""
        if self.audio:
            self.audio.play_tts(TTS_GPS_LOST)

    def _on_battery_low(self, payload):
        """低电量事件（stub，待 PowerService 就绪后启用）"""
        pass

    def _on_battery_critical(self, payload):
        """严重低电量事件（stub，待 PowerService 就绪后启用）"""
        pass

    def _on_alarm_control(self, payload):
        """
        brief 报警控制指令回调（来自 ControlService）
        param payload: {cmd: "cancel"/"sos"/"stealth"}
        """
        cmd = payload.get("cmd", "")
        if cmd == "cancel":
            self.cancel_alarm()
        elif cmd == "sos":
            self.trigger_sos()
        elif cmd == "stealth":
            self.trigger_stealth_alarm()

    def _on_config_update(self, payload):
        """配置更新回调"""
        if payload.get("target") == self.name:
            if "alarm_duration_ms" in payload:
                self.cfg["alarm_duration_ms"] = int(payload["alarm_duration_ms"])
                print("[%s] alarm_duration_ms → %sms" % (self.name, self.cfg["alarm_duration_ms"]))
            if "enable_local" in payload:
                self.cfg["enable_local"] = bool(payload["enable_local"])
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]

    def _on_heartrate(self, payload):
        """
        brief 心率异常 TTS 提醒（仅播报，不触发报警）
        note ALARM 优先级可打断导航和控制 TTS，但不打断已有碰撞/SOS
        """
        if not payload.get("valid"):
            return

        if self.ctx.get("alarm_active", False):
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["hr_alert_tick"]) < HEARTRATE_ALERT_COOLDOWN_MS:
            return

        hr = payload.get("heart_rate", 0)
        spo2 = payload.get("spo2", 0)
        tts_text = None

        if hr > HEARTRATE_HIGH_THRESHOLD:
            tts_text = HEARTRATE_TTS_HIGH
        elif hr < HEARTRATE_LOW_THRESHOLD:
            tts_text = HEARTRATE_TTS_LOW
        elif spo2 < HEARTRATE_SPO2_LOW_THRESHOLD:
            tts_text = HEARTRATE_SPO2_TTS_LOW

        if tts_text and self.event_bus:
            self.ctx["hr_alert_tick"] = now
            self.event_bus.publish(EVENT_TTS_REQUEST, {
                "text": tts_text,
                "priority": PRIORITY_ALARM,
            })

    def _on_sms_phone_config(self, payload):
        """
        brief 接收 SMS 手机号配置
        """
        phone = payload.get("phone", "")
        if phone and len(phone) == 11:
            self._sms_phone = phone
            print("[%s] SMS 手机号已配置: %s" % (self.name, phone))
            if self.event_bus:
                self.event_bus.publish(EVENT_TTS_REQUEST, {
                    "text": "手机号已配置",
                    "priority": PRIORITY_CTRL
                })

    def _on_gnss(self, payload):
        """
        brief 缓存最新 GNSS 坐标，供 SMS 发送时使用
        """
        self._gnss_cache = {
            "latitude": payload.get("latitude", 0),
            "longitude": payload.get("longitude", 0),
            "valid": payload.get("valid", False),
        }

    # ==================== SMS 辅助方法 ====================

    def _build_sms_message(self, level):
        """
        brief 构建 SMS 内容（有 GPS 时附带高德地图链接）
        param level: 报警等级 (int)
        return str SMS 文本
        """
        gnss = self._gnss_cache

        if gnss and gnss.get("valid"):
            lat = gnss.get("latitude", 0)
            lng = gnss.get("longitude", 0)

            # WGS84 → GCJ02 坐标转换
            gcj_lng, gcj_lat = self._wgs84_to_gcj02(lng, lat)

            # 生成高德地图链接
            url = "https://uri.amap.com/marker?position={:.6f},{:.6f}&name=SOS".format(gcj_lng, gcj_lat)
            return "SOS:{}(GPS):{}".format(level, url)
        else:
            return "SOS:{}".format(level)

    def _wgs84_to_gcj02(self, lng, lat):
        """
        brief WGS84 坐标转 GCJ02（高德地图坐标系）
        param lng: 经度
        param lat: 纬度
        return (gcj_lng, gcj_lat) 转换后的经纬度
        """
        PI = 3.1415926535897932384626
        A = 6378245.0
        EE = 0.00669342162296594323

        def _out_of_china(lng, lat):
            return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)

        def _transform_lat(x, y):
            ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + \
                  0.1 * x * y + 0.2 * math.sqrt(abs(x))
            ret += (20.0 * math.sin(6.0 * x * PI) +
                    20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
            ret += (20.0 * math.sin(y * PI) +
                    40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
            ret += (160.0 * math.sin(y / 12.0 * PI) +
                    320.0 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
            return ret

        def _transform_lng(x, y):
            ret = 300.0 + x + 2.0 * y + 0.1 * x * x + \
                  0.1 * x * y + 0.1 * math.sqrt(abs(x))
            ret += (20.0 * math.sin(6.0 * x * PI) +
                    20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
            ret += (20.0 * math.sin(x * PI) +
                    40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
            ret += (150.0 * math.sin(x / 12.0 * PI) +
                    300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
            return ret

        if _out_of_china(lng, lat):
            return lng, lat

        dlat = _transform_lat(lng - 105.0, lat - 35.0)
        dlng = _transform_lng(lng - 105.0, lat - 35.0)

        radlat = lat / 180.0 * PI
        magic = math.sin(radlat)
        magic = 1 - EE * magic * magic
        sqrtmagic = math.sqrt(magic)

        dlat = (dlat * 180.0) / ((A * (1 - EE)) / (magic * sqrtmagic) * PI)
        dlng = (dlng * 180.0) / (A / sqrtmagic * math.cos(radlat) * PI)

        mg_lat = lat + dlat
        mg_lng = lng + dlng
        return mg_lng, mg_lat

    # ==================== 辅助映射 ====================

    def _level_to_interval(self, level):
        """碰撞等级→LED 闪烁间隔(ms)"""
        return {1: 1000, 2: 500, 3: 200}.get(level, 1000)

    def _level_to_file(self, level):
        """碰撞等级→报警音频文件路径"""
        return {
            1: AUDIO_ALARM_FILE_L1,
            2: AUDIO_ALARM_FILE_L2,
            3: AUDIO_ALARM_FILE_L3,
        }.get(level, AUDIO_ALARM_FILE_L1)

    # ==================== 数据接口 ====================

    def get_data(self):
        """
        brief 获取报警数据快照
        return dict 数据副本
        """
        return {
            "alarm_active": self.ctx["alarm_active"],
            "alarm_type": self.ctx["alarm_type"],
            "alarm_level": self.ctx["alarm_level"],
            "last_alarm": dict(self._data["last_alarm"]),
            "timestamp": time.ticks_ms(),
        }

    def get_status(self):
        """
        brief 获取运行状态
        return dict 状态快照
        """
        return {
            "is_init": self.ctx["is_init"],
            "power_state": self.ctx["power_state"],
            "alarm_active": self.ctx["alarm_active"],
        }
