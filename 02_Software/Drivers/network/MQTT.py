"""
brief MQTT协议封装驱动 (EC200U)
note 纯协议封装层，调用 umqtt.robust.MQTTClient 原生 API
     不做事件发布，状态由 CloudService 轮询
"""
import time

from umqtt.robust import MQTTClient

from core.Base_Module import BaseModule
from core.config import (EVENT_CONFIG_UPDATE, POWER_STATE_ACTIVE,
                    MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD,
                    MQTT_CLIENT_ID, MQTT_KEEPALIVE, MQTT_MAX_RETRY,
                    MQTT_WILL_TOPIC, MQTT_WILL_MESSAGE, MQTT_WILL_QOS,
                    MQTT_WILL_RETAIN)


MQTT_STATE_DISCONNECTED  = "disconnected"
MQTT_STATE_CONNECTING    = "connecting"
MQTT_STATE_CONNECTED     = "connected"
MQTT_STATE_ERROR         = "error"


class MQTTDriver(BaseModule):
    """
    brief MQTT 协议封装驱动
    note 纯硬件封装层，调用 umqtt.robust.MQTTClient 原生 API
         不包含业务逻辑，由 CloudService 调用公共接口触发通信
    """

    def __init__(self, event_bus=None):
        """
        brief 初始化 MQTT 驱动实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "mqtt"

        self.cfg = {
            "broker": MQTT_BROKER,
            "port": MQTT_PORT,
            "client_id": MQTT_CLIENT_ID,
            "user": MQTT_USERNAME,
            "password": MQTT_PASSWORD,
            "keepalive": MQTT_KEEPALIVE,
            "max_retry": MQTT_MAX_RETRY,
            "will_topic": MQTT_WILL_TOPIC,
            "will_message": MQTT_WILL_MESSAGE,
            "will_qos": MQTT_WILL_QOS,
            "will_retain": MQTT_WILL_RETAIN,
        }

        self.ctx = {
            "is_init": False,
            "is_connected": False,
            "is_busy": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
            "mqtt_state": MQTT_STATE_DISCONNECTED,
        }

        self._data = {
            "connected": False,
            "valid": False,
        }

        self.client = None
        self._callback = None

    def init(self, broker=None, port=None, client_id=None,
             user=None, password=None, keepalive=None):
        """
        brief 初始化模块：创建 MQTT 客户端实例 + 设置遗嘱消息 + 订阅事件
        param broker:    MQTT 服务器地址，默认 cfg.broker
        param port:      MQTT 服务器端口，默认 cfg.port
        param client_id: 客户端 ID，默认 cfg.client_id
        param user:      MQTT 用户名，默认 cfg.user
        param password:  MQTT 密码，默认 cfg.password
        param keepalive: 心跳间隔(秒)，默认 cfg.keepalive
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            b = broker if broker is not None else self.cfg["broker"]
            p = port if port is not None else self.cfg["port"]
            cid = client_id if client_id is not None else self.cfg["client_id"]
            u = user if user is not None else self.cfg["user"]
            pw = password if password is not None else self.cfg["password"]
            ka = keepalive if keepalive is not None else self.cfg["keepalive"]

            self.client = MQTTClient(
                client_id=cid,
                server=b,
                port=p,
                user=u,
                password=pw,
                keepalive=ka,
                ssl=None
            )

            try:
                self.client.set_last_will(
                    self.cfg["will_topic"],
                    self.cfg["will_message"],
                    self.cfg["will_retain"],
                    self.cfg["will_qos"],
                )
            except AttributeError:
                print(f"[{self.name}] WARNING set_last_will 不可用，跳过遗嘱消息")

            if self.client is None:
                raise RuntimeError("MQTT 客户端创建失败")

            if self.event_bus:
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)

            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成 | broker:{b}:{p} client_id:{cid}")

        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        """
        brief 周期调度
        note MQTT 为被动控制型设备，无主动采样需求，tick 保持空实现
              心跳更新必须在状态守卫之前，防止省电模式下误判离线
        """
        self.ctx["last_hb"] = time.ticks_ms()
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

    def connect(self, timeout_ms=None):
        """
        brief 连接 MQTT Broker
        param timeout_ms: 连接超时时间(ms)，默认 10000ms
        return bool 是否连接成功
        """
        if not self.ctx["is_init"]:
            return False

        if self.ctx["is_connected"]:
            return True

        self.ctx["mqtt_state"] = MQTT_STATE_CONNECTING
        self.ctx["is_busy"] = True

        if timeout_ms is None:
            timeout_ms = 10000

        try:
            if self._callback:
                self.client.set_callback(self._callback)

            self.client.connect()
            self.ctx["is_connected"] = True
            self._data["connected"] = True
            self._data["valid"] = True
            self.ctx["mqtt_state"] = MQTT_STATE_CONNECTED
            self.ctx["err_count"] = 0
            print(f"[{self.name}] ✓ MQTT 已连接")
            return True

        except Exception as e:
            self.ctx["err_count"] += 1
            self.ctx["mqtt_state"] = MQTT_STATE_ERROR
            self._data["connected"] = False
            self._data["valid"] = False
            self.ctx["is_connected"] = False
            print(f"[{self.name}] ✗ 连接失败: {e}")
            return False

        finally:
            self.ctx["is_busy"] = False

    def publish(self, topic, payload, qos=0):
        """
        brief 发布消息到指定 topic
        param topic:   目标主题
        param payload: 消息内容（字符串或 bytes）
        param qos:     服务质量等级 (0/1)
        return bool 是否发布成功
        """
        if not self.ctx["is_init"] or not self.ctx["is_connected"]:
            return False

        try:
            self.client.publish(topic, payload, qos=qos)
            self.ctx["err_count"] = 0
            return True
        except Exception as e:
            self.ctx["err_count"] += 1
            print(f"[{self.name}] publish 失败 ({self.ctx['err_count']}): {e}")
            if self.ctx["err_count"] >= self.cfg["max_retry"]:
                self.ctx["is_connected"] = False
                self._data["connected"] = False
            return False

    def subscribe(self, topic, qos=0):
        """
        brief 订阅指定 topic
        param topic: 要订阅的主题
        param qos:   服务质量等级 (0/1)
        return bool 是否订阅成功
        """
        if not self.ctx["is_init"] or not self.ctx["is_connected"]:
            return False

        try:
            self.client.subscribe(topic, qos=qos)
            print(f"[{self.name}] ✓ 已订阅: {topic}")
            return True
        except Exception as e:
            print(f"[{self.name}] subscribe 失败: {e}")
            return False

    def set_callback(self, fn):
        """
        brief 设置消息接收回调函数
        param fn: 回调函数 fn(topic, msg)
        note 回调在网络线程执行，内部禁止耗时操作
        """
        self._callback = fn
        if self.client and self.ctx["is_connected"]:
            try:
                self.client.set_callback(fn)
            except Exception as e:
                print(f"[{self.name}] set_callback 失败: {e}")

    def check_msg(self):
        """
        brief 非阻塞检查消息
        note 有消息时触发已注册的回调函数，适合在网络线程中循环调用
        """
        if not self.ctx["is_init"] or not self.ctx["is_connected"]:
            return

        try:
            self.client.check_msg()
        except Exception as e:
            print(f"[{self.name}] check_msg 异常: {e}")

    def disconnect(self):
        """
        brief 断开 MQTT Broker 连接
        return bool 是否成功断开
        """
        try:
            self.publish(self.cfg["will_topic"],
                        '{"status":"offline","reason":"normal"}',
                        qos=1)
            self.client.disconnect()
            self.ctx["is_connected"] = False
            self.ctx["mqtt_state"] = MQTT_STATE_DISCONNECTED
            self._data["connected"] = False
            self._data["valid"] = False
            print(f"[{self.name}] ✓ 已断开")
            return True
        except Exception as e:
            print(f"[{self.name}] ✗ 断开失败: {e}")
            return False

    def is_connected(self):
        """
        brief 查询 MQTT 连接状态
        return bool True=已连接，False=未连接
        """
        return self.ctx["is_connected"]

    def _on_config_update(self, payload):
        """
        brief 配置更新回调
        param payload: 配置事件负载
        """
        if payload.get("target") == self.name:
            if "broker" in payload:
                self.cfg["broker"] = payload["broker"]
            if "port" in payload:
                self.cfg["port"] = int(payload["port"])
            if "client_id" in payload:
                self.cfg["client_id"] = payload["client_id"]
            if "keepalive" in payload:
                self.cfg["keepalive"] = int(payload["keepalive"])

        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print(f"[{self.name}] 功耗状态: {old_state} -> {payload['power_state']}")

    def get_data(self):
        """
        brief 获取 MQTT 连接数据快照
        return dict 数据副本
        """
        return {
            "connected": self._data["connected"],
            "valid": self._data["valid"],
            "mqtt_state": self.ctx["mqtt_state"],
            "timestamp": time.ticks_ms(),
        }

    def get_status(self):
        """
        brief 查询模块运行状态
        return dict 状态快照
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_connected": self.ctx["is_connected"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
            "mqtt_state": self.ctx["mqtt_state"],
        }
