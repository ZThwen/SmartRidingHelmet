"""
brief 云端通信服务（CloudService）
note 负责传感器数据打包上传、紧急报警推送、云端配置下发转发
     触发上传由 tick() 定时控制，不依赖 GNSS 定位状态
     网络 I/O 在独立 _thread 中执行，主线程只做 JSON 拼装入队
"""
import time
import ujson
import _thread
import math

from core.Base_Module import BaseModule
from core.config import (
    EVENT_TEMP_HUMID_READY, EVENT_IMU_READY, EVENT_GNSS_READY,
    EVENT_ALARM_TRIGGERED, EVENT_CONFIG_UPDATE,
    EVENT_NETWORK_CONNECTED, EVENT_NETWORK_DISCONNECTED,
    EVENT_DATA_UPLOAD_SUCCESS, EVENT_DATA_UPLOAD_FAILED,
    MQTT_TOPIC_DATA, MQTT_TOPIC_ALARM, MQTT_TOPIC_CONFIG,
    MQTT_QOS_DATA, MQTT_QOS_ALARM, MQTT_QOS_CONFIG,
    CLOUD_UPLOAD_INTERVAL_MS, CLOUD_GPS_TRACK_MAX,
)
from Drivers.network.Network import NetworkDriver
from Drivers.network.MQTT import MQTTDriver
from Drivers.network.thread_queue import ThreadSafeQueue


class CloudService(BaseModule):
    def __init__(self, event_bus=None):
        """
        brief 初始化云端通信服务实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "cloud"

        # ======================= cfg：静态配置 =======================
        self.cfg = {
            "upload_interval_ms": CLOUD_UPLOAD_INTERVAL_MS,
            "gps_track_max": CLOUD_GPS_TRACK_MAX,
            "max_retry": 3,
        }

        # ======================= ctx：运行时上下文 =======================
        self.ctx = {
            "is_init": False,
            "is_network_ready": False,
            "is_mqtt_ready": False,
            "thread_running": False,
            "err_count": 0,
            "last_upload": 0,
        }

        # ======================= _data：缓存与扩展字段 =======================
        # 传感器缓存（初始 None，未读到数据时 JSON 输出 null）
        self._data = {
            "latest_temp": None,
            "latest_humid": None,
            "latest_imu": None,
            "latest_gnss": None,
            "_prev_gnss": None,
            # 骑行扩展
            "total_distance": 0.0,
            "max_speed": 0.0,
            "total_ascent": 0.0,
            "collision_count": 0,
            "gps_track": [],
        }

        # Device 层对象（Service 持有 Device）
        self.network = None
        self.mqtt = None
        self.send_queue = None

    def init(self):
        """
        brief 初始化服务：创建 Device 实例 + 初始化硬件 + 订阅事件 + 启动网络线程
        note Network/MQTT 的 init() 在主线程执行（AT 指令吃栈深）
              连接重试和消息发送在网络线程执行
        """
        try:
            # ====== 1. 创建 Device 层对象 ======
            self.network = NetworkDriver()
            self.mqtt = MQTTDriver()

            # ====== 2. 初始化 Device 层硬件（主线程，栈充足）======
            self.network.init()
            self.mqtt.init()
            self.mqtt.set_callback(self._on_mqtt_message)

            # ====== 3. 创建线程安全队列 ======
            self.send_queue = ThreadSafeQueue(max_size=100)

            # ====== 4. 订阅事件 ======
            if self.event_bus:
                self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid)
                self.event_bus.subscribe(EVENT_IMU_READY, self._on_imu)
                self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm)
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)

            # ====== 5. 主线程完成连接（AT 指令，栈充足）======
            if self.network.connect():
                if self.mqtt.connect():
                    self.mqtt.subscribe(MQTT_TOPIC_CONFIG, qos=MQTT_QOS_CONFIG)
                    self.ctx["is_network_ready"] = True
                    self.ctx["is_mqtt_ready"] = True
                    if self.event_bus:
                        self.event_bus.publish(EVENT_NETWORK_CONNECTED, {})

            # ====== 6. 启动网络线程（只收发，不碰 AT）======
            self.ctx["thread_running"] = True
            old_stack = _thread.stack_size(4096)
            _thread.start_new_thread(self._network_thread, ())
            _thread.stack_size(old_stack)

            self.ctx["is_init"] = True
            print("[%s] OK init" % self.name)

        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise

    def tick(self):
        """
        brief 周期调度：定时拼装传感器数据入队 + 断连检测重连
        note 上传周期由 cfg.upload_interval_ms 控制
             实际网络发送由网络线程负责，tick 只做入队
             重连在主线程执行（AT 指令）
        """
        now = time.ticks_ms()

        # ====== 1. 断连检测重连 ======
        if not self.ctx["is_mqtt_ready"]:
            if time.ticks_diff(now, self.ctx.get("last_reconnect", 0)) < 10000:
                pass
            else:
                self.ctx["last_reconnect"] = now
                try:
                    if self.network.connect():
                        if self.mqtt.connect():
                            self.mqtt.subscribe(MQTT_TOPIC_CONFIG, qos=MQTT_QOS_CONFIG)
                            self.ctx["is_network_ready"] = True
                            self.ctx["is_mqtt_ready"] = True
                            if self.event_bus:
                                self.event_bus.publish(EVENT_NETWORK_CONNECTED, {})
                except Exception:
                    self.ctx["is_network_ready"] = False
                    self.ctx["is_mqtt_ready"] = False

        # ====== 2. 时间片控制 ======
        if time.ticks_diff(now, self.ctx["last_upload"]) < self.cfg["upload_interval_ms"]:
            return
        self.ctx["last_upload"] = now

        # ====== 3. 拼装 JSON 入队 ======
        try:
            payload = {
                "Temp": self._data["latest_temp"],
                "Humi": self._data["latest_humid"],
                "G-Sensor": self._data["latest_imu"],
                "GNSS": self._data["latest_gnss"],
                "total_distance": round(self._data["total_distance"], 3),
                "max_speed": self._data["max_speed"],
                "total_ascent": round(self._data["total_ascent"], 1),
                "collision_count": self._data["collision_count"],
                "timestamp": time.ticks_ms(),
            }
            json_str = ujson.dumps(payload)
            self.send_queue.put(json_str)

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] tick 拼装异常 (%s): %s" % (self.name, self.ctx["err_count"], e))

    # ==================== 事件回调 ====================

    def _on_temp_humid(self, payload):
        """缓存温湿度数据"""
        if not payload.get("valid", False):
            return
        self._data["latest_temp"] = payload["temp"]
        self._data["latest_humid"] = payload["humid"]

    def _on_imu(self, payload):
        """缓存 IMU 加速度数据"""
        if not payload.get("valid", False):
            return
        self._data["latest_imu"] = {
            "X": payload["acc_x"],
            "Y": payload["acc_y"],
            "Z": payload["acc_z"],
            "total": payload["acc_total"],
        }

    def _on_gnss(self, payload):
        """
        brief 缓存 GNSS 定位数据 + 更新骑行扩展字段
        note 不上传入队——上传由 tick() 定时触发
        """
        if not payload.get("valid", False):
            return

        # ====== 1. 缓存当前定位 ======
        curr = {
            "lat": payload["latitude"],
            "lon": payload["longitude"],
            "alt": payload["altitude"],
            "speed_kmh": payload["speed_kmh"],
        }
        self._data["latest_gnss"] = curr

        # ====== 2. 更新骑行扩展数据 ======
        prev = self._data["_prev_gnss"]
        if prev:
            # 累加 Haversine 距离
            self._data["total_distance"] += self._haversine(
                prev["lat"], prev["lon"],
                payload["latitude"], payload["longitude"],
            )
            # 累加爬升
            ascent = payload["altitude"] - prev["alt"]
            if ascent > 0:
                self._data["total_ascent"] += ascent

        self._data["_prev_gnss"] = {
            "lat": payload["latitude"],
            "lon": payload["longitude"],
            "alt": payload["altitude"],
        }

        # 最大速度
        if payload["speed_kmh"] > self._data["max_speed"]:
            self._data["max_speed"] = payload["speed_kmh"]

        # GPS 轨迹
        self._data["gps_track"].append({
            "lat": payload["latitude"],
            "lon": payload["longitude"],
        })
        if len(self._data["gps_track"]) > self.cfg["gps_track_max"]:
            self._data["gps_track"].pop(0)

    def _on_alarm(self, payload):
        """
        brief 报警事件回调：立即拼装报警 JSON 入队
        note 不依赖上传周期，收到后立即入队让网络线程发送
        """
        alarm_type = payload.get("alarm_type", "unknown")
        level = payload.get("level", 1)

        # ====== 1. 统计碰撞次数 ======
        if alarm_type == "collision":
            self._data["collision_count"] += 1

        # ====== 2. 拼装报警 JSON ======
        gnss = self._data["latest_gnss"]
        payload_data = {
            "alarm_type": alarm_type,
            "level": level,
            "location": {
                "lat": gnss["lat"],
                "lon": gnss["lon"],
            } if gnss else None,
            "timestamp": time.ticks_ms(),
        }
        json_str = ujson.dumps(payload_data)
        self.send_queue.put(json_str)

    # ==================== 网络线程（后台）====================

    def _network_thread(self):
        """
        brief 网络线程：只做 MQTT 数据收发，通过 EventBus 通信
        note 
            - 不发任何 AT 指令（init/connect 已在主线程完成）
            - 发送成功 → EVENT_DATA_UPLOAD_SUCCESS
            - 发送失败 → EVENT_UPLOAD_FAILED → 标记断连（主线程 tick 重连）
            - 收到下行消息 → _on_mqtt_message → publish(EVENT_CONFIG_UPDATE)
        """
        while self.ctx["thread_running"]:

            # ----- 1. 取数据发送（非阻塞等待）-----
            data = self.send_queue.get(timeout_ms=1000)
            if data and self.ctx["is_mqtt_ready"]:
                try:
                    self.mqtt.publish(MQTT_TOPIC_DATA, data, qos=MQTT_QOS_DATA)
                    if self.event_bus:
                        self.event_bus.publish(EVENT_DATA_UPLOAD_SUCCESS, {})
                    self.ctx["err_count"] = 0
                except Exception as e:
                    self.ctx["err_count"] += 1
                    self.ctx["is_mqtt_ready"] = False
                    if self.event_bus:
                        self.event_bus.publish(EVENT_DATA_UPLOAD_FAILED, {
                            "error": str(e),
                        })

            # ----- 2. 检查下行消息（非阻塞）-----
            if self.ctx["is_mqtt_ready"]:
                try:
                    self.mqtt.check_msg()
                except Exception:
                    self.ctx["is_mqtt_ready"] = False

    def _on_mqtt_message(self, topic, msg):
        """
        brief MQTT 下行消息回调（在网络线程中执行）
        param topic: 消息主题
        param msg: 消息内容
        note 解析 JSON 后转发为 EVENT_CONFIG_UPDATE 事件
             不在回调中做耗时操作
        """
        try:
            config = ujson.loads(msg)
            if self.event_bus:
                self.event_bus.publish(EVENT_CONFIG_UPDATE, config)
        except Exception as e:
            print("[cloud] MQTT 消息解析失败: %s" % e)

    # ==================== 辅助方法 ====================

    def _haversine(self, lat1, lon1, lat2, lon2):
        """
        brief 计算两点间球面距离（Haversine 公式）
        param lat1: 起点纬度
        param lon1: 起点经度
        param lat2: 终点纬度
        param lon2: 终点经度
        return float 距离（km）
        """
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) *
             math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def get_data(self):
        """
        brief 获取云端通信数据快照
        return dict 数据副本
        """
        return {
            "latest_gnss": self._data["latest_gnss"],
            "total_distance": round(self._data["total_distance"], 3),
            "max_speed": self._data["max_speed"],
            "total_ascent": round(self._data["total_ascent"], 1),
            "collision_count": self._data["collision_count"],
            "queue_size": self.send_queue.size() if self.send_queue else 0,
            "timestamp": time.ticks_ms(),
        }

    def get_status(self):
        """
        brief 获取云端通信运行状态
        return dict 状态快照
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_network_ready": self.ctx["is_network_ready"],
            "is_mqtt_ready": self.ctx["is_mqtt_ready"],
            "thread_running": self.ctx["thread_running"],
            "err_count": self.ctx["err_count"],
        }

    def _on_config_update(self, payload):
        """
        brief 配置更新回调
        param payload: 配置事件负载
        """
        if payload.get("target") == self.name:
            if "upload_interval_ms" in payload:
                self.cfg["upload_interval_ms"] = int(payload["upload_interval_ms"])
                print("[%s] 上传间隔更新为 %sms" % (self.name, self.cfg["upload_interval_ms"]))
            if "gps_track_max" in payload:
                self.cfg["gps_track_max"] = int(payload["gps_track_max"])
