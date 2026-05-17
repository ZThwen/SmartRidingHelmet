"""
brief MQTT 驱动集成测试脚本
note 测试 MQTT + EventBus 的事件驱动集成
     模拟 CloudService 的 send_queue + 网络线程模式
     需要 4G 网络已连接 + ConnectLab 会话有效
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (EVENT_CONFIG_UPDATE, EVENT_DATA_UPLOAD_SUCCESS,
                    EVENT_DATA_UPLOAD_FAILED, EVENT_NETWORK_CONNECTED,
                    EVENT_NETWORK_DISCONNECTED, MQTT_BROKER, MQTT_PORT,
                    MQTT_USERNAME, MQTT_PASSWORD, MQTT_CLIENT_ID,
                    MQTT_TOPIC_DATA, MQTT_TOPIC_CONFIG, MQTT_TOPIC_ALARM,
                    MQTT_TOPIC_STATUS, MQTT_KEEPALIVE)
from Drivers.network.MQTT import MQTTDriver


event_log = []


def log_event(event, payload):
    """通用事件记录"""
    event_log.append((event, payload))
    print(f"[EVENT] {event}: {payload}")


class MockCloudService:
    """
    brief 模拟 CloudService 的 MQTT 使用方式
    note 测试 send_queue + 事件驱动模式
    """

    def __init__(self, event_bus, mqtt):
        self.event_bus = event_bus
        self.mqtt = mqtt
        self.name = "mock_cloud"

        self._data = {
            "send_count": 0,
            "recv_count": 0,
            "last_data": None,
        }

        self._mqtt_connected = False
        self._send_queue = []

    def init(self):
        """初始化：设置回调 + 订阅事件"""
        self.mqtt.set_callback(self._on_mqtt_message)

        if self.event_bus:
            self.event_bus.subscribe(EVENT_NETWORK_CONNECTED, self._on_net_connected)

        print(f"[{self.name}] ✓ 初始化完成")

    def connect_mqtt(self):
        """连接 MQTT Broker"""
        result = self.mqtt.connect()
        if result:
            self._mqtt_connected = True
            self.mqtt.subscribe(MQTT_TOPIC_CONFIG)
            if self.event_bus:
                self.event_bus.publish(EVENT_NETWORK_CONNECTED, {"status": "mqtt_connected"})
        return result

    def enqueue_data(self, payload):
        """模拟 CloudService 的 send_queue.put"""
        self._send_queue.append(payload)
        print(f"[{self.name}]  入队: {payload[:50]}...")

    def flush_queue(self):
        """模拟网络线程发队列数据"""
        sent = 0
        failed = 0
        while self._send_queue:
            data = self._send_queue.pop(0)
            result = self.mqtt.publish(MQTT_TOPIC_DATA, data, qos=0)
            if result:
                sent += 1
                self._data["send_count"] += 1
                self._data["last_data"] = data
                if self.event_bus:
                    self.event_bus.publish(EVENT_DATA_UPLOAD_SUCCESS, {"topic": MQTT_TOPIC_DATA})
            else:
                failed += 1
                self._send_queue.insert(0, data)
                if self.event_bus:
                    self.event_bus.publish(EVENT_DATA_UPLOAD_FAILED, {"topic": MQTT_TOPIC_DATA})
                break
            time.sleep_ms(100)
        print(f"[{self.name}]  发送: {sent} 成功, {failed} 失败")
        return sent, failed

    def _on_mqtt_message(self, topic, msg):
        """模拟 CloudService 的 MQTT 回调"""
        self._data["recv_count"] += 1
        print(f"\n[{self.name}] << 收到云端消息")
        print(f"  topic: {topic}")
        print(f"  msg:   {msg}")

        config = eval(msg.decode()) if isinstance(msg, bytes) else eval(msg)
        if self.event_bus:
            self.event_bus.publish(EVENT_CONFIG_UPDATE, config)

    def _on_net_connected(self, payload):
        """网络连接事件回调"""
        print(f"[{self.name}]  网络已连接: {payload}")

    def get_status(self):
        return {
            "send_count": self._data["send_count"],
            "recv_count": self._data["recv_count"],
            "queue_size": len(self._send_queue),
            "mqtt_connected": self._mqtt_connected,
        }


def test_mqtt_integration():
    print("=" * 60)
    print("MQTT 驱动集成测试")
    print("=" * 60)

    event_bus = EventBus()
    event_bus.debug = True

    event_bus.subscribe(EVENT_DATA_UPLOAD_SUCCESS,
                       lambda p: log_event("DATA_UPLOAD_SUCCESS", p))
    event_bus.subscribe(EVENT_DATA_UPLOAD_FAILED,
                       lambda p: log_event("DATA_UPLOAD_FAILED", p))
    event_bus.subscribe(EVENT_NETWORK_CONNECTED,
                       lambda p: log_event("NETWORK_CONNECTED", p))
    event_bus.subscribe(EVENT_NETWORK_DISCONNECTED,
                       lambda p: log_event("NETWORK_DISCONNECTED", p))
    event_bus.subscribe(EVENT_CONFIG_UPDATE,
                       lambda p: log_event("CONFIG_UPDATE", p))

    # ==================== 创建实例 ====================
    print("\n" + "-" * 60)
    print("[步骤 1] 创建 MQTT 驱动 + MockCloudService")
    print("-" * 60)

    mqtt = MQTTDriver(event_bus)

    try:
        mqtt.init(
            broker=MQTT_BROKER,
            port=MQTT_PORT,
            client_id=MQTT_CLIENT_ID,
            user=MQTT_USERNAME,
            password=MQTT_PASSWORD,
            keepalive=MQTT_KEEPALIVE,
        )
        print("  ✓ MQTTDriver 初始化成功")
    except Exception as e:
        print(f"  ✗ MQTTDriver 初始化失败: {e}")
        return

    cloud = MockCloudService(event_bus, mqtt)
    cloud.init()
    print("  ✓ MockCloudService 初始化成功")

    # ==================== 连接 MQTT ====================
    print("\n" + "-" * 60)
    print("[步骤 2] 连接 MQTT Broker")
    print("-" * 60)
    print(f"  Broker: {MQTT_BROKER}:{MQTT_PORT}  Client ID: {MQTT_CLIENT_ID}")

    result = cloud.connect_mqtt()
    if not result:
        print("  ✗ MQTT 连接失败，退出测试")
        return

    print("  ✓ MQTT 连接成功")
    print(f"  mqtt_state: {mqtt.get_status()['mqtt_state']}")

    event_bus.pump()

    # ==================== 模拟传感器数据上传 ====================
    print("\n" + "-" * 60)
    print("[步骤 3] 模拟传感器数据入队 + 发送")
    print("-" * 60)

    test_sensor_data = [
        '{"Temp":28.5,"Humi":65.2,"GNSS":{"lat":22.5431,"lon":113.9523},"speed_kmh":25.6}',
        '{"Temp":28.6,"Humi":65.0,"GNSS":{"lat":22.5432,"lon":113.9524},"speed_kmh":26.1}',
        '{"Temp":28.4,"Humi":65.1,"GNSS":{"lat":22.5433,"lon":113.9525},"speed_kmh":24.8}',
    ]

    for i, data in enumerate(test_sensor_data):
        print(f"\n  模拟传感器数据 #{i+1}:")
        cloud.enqueue_data(data)
        sent, failed = cloud.flush_queue()
        print(f"  结果: {sent} 成功 / {failed} 失败")
        event_bus.pump()
        time.sleep_ms(200)

    # ==================== 验证上传事件 ====================
    print("\n" + "-" * 60)
    print("[步骤 4] 验证上传事件")
    print("-" * 60)
    upload_success = sum(1 for e in event_log if e[0] == "DATA_UPLOAD_SUCCESS")
    upload_failed = sum(1 for e in event_log if e[0] == "DATA_UPLOAD_FAILED")
    print(f"  DATA_UPLOAD_SUCCESS: {upload_success} 次")
    print(f"  DATA_UPLOAD_FAILED:  {upload_failed} 次")
    print(f"  总发送:              {cloud.get_status()['send_count']} 条")
    print(f"  {'✓ 数据上传正常' if upload_success > 0 else '✗ 无成功上传记录'}")

    # ==================== 模拟报警推送 ====================
    print("\n" + "-" * 60)
    print("[步骤 5] 模拟报警数据推送")
    print("-" * 60)

    alarm_data = '{"alarm_type":"collision","level":2,"location":{"lat":22.5431,"lon":113.9523}}'
    result = mqtt.publish(MQTT_TOPIC_ALARM, alarm_data, qos=1)
    print(f"  报警数据: {alarm_data}")
    print(f"  {'✓ 报警已推送' if result else '✗ 推送失败'}")

    if result:
        cloud._data["send_count"] += 1

    event_bus.pump()

    # ==================== 模拟配置下发 ====================
    print("\n" + "-" * 60)
    print("[步骤 6] 模拟云端配置下发")
    print("-" * 60)

    config_msg = '{"target":"mqtt","keepalive":120}'

    print(f"  注意：从 ConnectLab 界面手动发送以下消息:")
    print(f"  Topic: {MQTT_TOPIC_CONFIG}")
    print(f"  QoS:   1")
    print(f"  消息:  {config_msg}")
    print()
    print("  等待 5 秒以接收配置...")

    for i in range(5):
        mqtt.check_msg()
        time.sleep(1)
        print(f"  {5-i}...")

    event_bus.pump()
    print()

    config_events = [e for e in event_log if e[0] == "CONFIG_UPDATE"]
    if config_events:
        print(f"  ✓ 收到 {len(config_events)} 条配置更新")
        for e in config_events:
            print(f"     payload: {e[1]}")
    else:
        print("  - 未收到配置更新（需要在 ConnectLab 手动发送）")

    # ==================== 设备状态消息 ====================
    print("\n" + "-" * 60)
    print("[步骤 7] 设备状态上报")
    print("-" * 60)
    status_payload = '{"status":"online","client_id":"66ccff","uptime":120}'
    result = mqtt.publish(MQTT_TOPIC_STATUS, status_payload, qos=1)
    print(f"  状态消息: {status_payload}")
    print(f"  {'✓ 状态已上报' if result else '✗ 上报失败'}")

    # ==================== 断开连接 ====================
    print("\n" + "-" * 60)
    print("[步骤 8] 断开 MQTT 连接")
    print("-" * 60)
    result = mqtt.disconnect()
    print(f"  {'✓ 断开成功' if result else '✗ 断开失败'}")

    event_bus.pump()

    # ==================== 测试总结 ====================
    print("\n" + "=" * 60)
    print("集成测试总结")
    print("=" * 60)
    cloud_status = cloud.get_status()
    print(f"\nMockCloudService 状态:")
    print(f"  发送次数:   {cloud_status['send_count']}")
    print(f"  接收次数:   {cloud_status['recv_count']}")
    print(f"  MQTT 连接:  {cloud_status['mqtt_connected']}")
    print(f"\nMQTTDriver 状态:")
    mqtt_status = mqtt.get_status()
    print(f"  is_init:     {mqtt_status['is_init']}")
    print(f"  err_count:   {mqtt_status['err_count']}")
    print(f"  mqtt_state:  {mqtt_status['mqtt_state']}")
    print(f"\n事件统计:")
    for event_type in set(e[0] for e in event_log):
        count = sum(1 for e in event_log if e[0] == event_type)
        print(f"  {event_type}: {count} 次")
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_mqtt_integration()
