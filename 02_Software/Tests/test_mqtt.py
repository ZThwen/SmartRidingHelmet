"""
brief MQTT 驱动单模块测试脚本
note 用于验证 MQTTDriver 的各项公共接口功能是否正常
     需要 4G 网络已连接 + ConnectLab 会话有效
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (EVENT_CONFIG_UPDATE, MQTT_BROKER, MQTT_PORT,
                    MQTT_USERNAME, MQTT_PASSWORD, MQTT_CLIENT_ID,
                    MQTT_TOPIC_DATA, MQTT_TOPIC_CONFIG, MQTT_TOPIC_STATUS)
from Drivers.network.MQTT import (MQTTDriver, MQTT_STATE_DISCONNECTED,
                                MQTT_STATE_CONNECTED, MQTT_STATE_ERROR)


event_log = []


def on_mqtt_message(topic, msg):
    """MQTT 消息回调"""
    event_log.append(("MQTT_MSG", topic, msg))
    print(f"\n[消息回调] topic: {topic}  msg: {msg}")


def on_config_update(payload):
    """配置更新回调"""
    event_log.append(("CONFIG_UPDATE", payload))
    print(f"\n[事件回调] EVENT_CONFIG_UPDATE: {payload}")


def test_mqtt():
    print("=" * 60)
    print("MQTT 驱动单模块测试")
    print("=" * 60)

    event_bus = EventBus()
    event_bus.debug = True

    event_bus.subscribe(EVENT_CONFIG_UPDATE, on_config_update)

    mqtt = MQTTDriver(event_bus)

    # ==================== 测试 1：初始化 ====================
    print("\n" + "-" * 60)
    print("[测试 1] 初始化模块")
    print("-" * 60)
    try:
        mqtt.init(
            broker=MQTT_BROKER,
            port=MQTT_PORT,
            client_id=MQTT_CLIENT_ID,
            user=MQTT_USERNAME,
            password=MQTT_PASSWORD,
        )
        print("\n✓ 初始化成功")
    except Exception as e:
        print(f"\n✗ 初始化失败: {e}")
        return

    # ==================== 测试 2：状态查询 ====================
    print("\n" + "-" * 60)
    print("[测试 2] 查看模块初始状态")
    print("-" * 60)
    status = mqtt.get_status()
    data = mqtt.get_data()
    print(f"  is_init:       {status['is_init']}")
    print(f"  is_connected:  {status['is_connected']}")
    print(f"  err_count:     {status['err_count']}")
    print(f"  mqtt_state:    {status['mqtt_state']}")
    print(f"  connected:     {data['connected']}")
    print(f"  valid:         {data['valid']}")

    # ==================== 测试 3：连接 MQTT Broker ====================
    print("\n" + "-" * 60)
    print("[测试 3] 连接 MQTT Broker")
    print("-" * 60)
    print(f"  Broker: {MQTT_BROKER}:{MQTT_PORT}")
    print(f"  Client ID: {MQTT_CLIENT_ID}")
    print("  正在连接...")

    result = mqtt.connect()
    if result:
        print("  ✓ MQTT 连接成功")
    else:
        print("  ✗ MQTT 连接失败（请检查 ConnectLab 会话是否有效）")
        print("  跳过后续测试")
        return

    # ==================== 测试 4：连接状态验证 ====================
    print("\n" + "-" * 60)
    print("[测试 4] 连接状态验证")
    print("-" * 60)
    connected = mqtt.is_connected()
    data = mqtt.get_data()
    print(f"  is_connected(): {connected}")
    print(f"  mqtt_state:     {data['mqtt_state']}")
    print(f"  connected:      {data['connected']}")
    print(f"  valid:          {data['valid']}")
    print(f"  {'✓ 连接状态正常' if connected else '✗ 连接状态异常'}")

    # ==================== 测试 5：消息发布 ====================
    print("\n" + "-" * 60)
    print("[测试 5] 发布测试消息")
    print("-" * 60)
    test_payload = '{"test": "hello from helmet_66ccff", "value": 123}'
    result = mqtt.publish(MQTT_TOPIC_DATA, test_payload, qos=0)
    print(f"  topic:   {MQTT_TOPIC_DATA}")
    print(f"  payload: {test_payload}")
    print(f"  qos:     0")
    print(f"  {'✓ 发布成功' if result else '✗ 发布失败'}")

    # ==================== 测试 6：设置回调 + 订阅 ====================
    print("\n" + "-" * 60)
    print("[测试 6] 设置回调 + 订阅 Topic")
    print("-" * 60)
    mqtt.set_callback(on_mqtt_message)
    result = mqtt.subscribe(MQTT_TOPIC_CONFIG)
    print(f"  topic:   {MQTT_TOPIC_CONFIG}")
    print(f"  {'✓ 订阅成功' if result else '✗ 订阅失败'}")

    # ==================== 测试 7：检查消息（非阻塞） ====================
    print("\n" + "-" * 60)
    print("[测试 7] 非阻塞消息检查")
    print("-" * 60)
    print("  注意：此时可以从 ConnectLab 界面向发送消息")
    print(f"  topic: {MQTT_TOPIC_CONFIG}")
    print("  等待 5 秒以接收消息...")

    for i in range(5):
        mqtt.check_msg()
        time.sleep(1)
        print(f"  .", end="")
    print()

    if event_log:
        print(f"  ✓ 收到 {len(event_log)} 条消息")
    else:
        print("  - 未收到消息（这可能是正常的，需要在 ConnectLab 手动发送）")

    # ==================== 测试 8：配置更新 ====================
    print("\n" + "-" * 60)
    print("[测试 8] 配置更新测试")
    print("-" * 60)
    print(f"\n  更新前 keepalive: {mqtt.cfg['keepalive']}")
    event_bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "mqtt",
        "keepalive": 120
    })
    event_bus.pump()
    time.sleep_ms(100)
    print(f"  更新后 keepalive: {mqtt.cfg['keepalive']}")
    print(f"  {'✓ 配置更新成功' if mqtt.cfg['keepalive'] == 120 else '✗ 配置更新失败'}")

    # ==================== 测试 9：状态消息发布 ====================
    print("\n" + "-" * 60)
    print("[测试 9] 设备状态消息")
    print("-" * 60)
    status_payload = '{"status":"online","client_id":"66ccff"}'
    result = mqtt.publish(MQTT_TOPIC_STATUS, status_payload, qos=1)
    print(f"  {'✓ 状态消息已发送' if result else '✗ 发送失败'}")

    # ==================== 测试 10：断开连接 ====================
    print("\n" + "-" * 60)
    print("[测试 10] 断开 MQTT 连接")
    print("-" * 60)
    result = mqtt.disconnect()
    status = mqtt.get_status()
    print(f"  disconnect():   {'✓' if result else '✗'}")
    print(f"  断开后状态:      {status['mqtt_state']} (期望: {MQTT_STATE_DISCONNECTED})")
    print(f"  {'✓ 断开成功' if result and status['mqtt_state'] == MQTT_STATE_DISCONNECTED else '✗ 断开异常'}")

    # ==================== 测试 11：数据字段完整性 ====================
    print("\n" + "-" * 60)
    print("[测试 11] 数据字段完整性验证")
    print("-" * 60)
    data = mqtt.get_data()
    expected_fields = ["connected", "valid", "mqtt_state", "timestamp"]
    missing = [f for f in expected_fields if f not in data]
    if not missing:
        print("  ✓ get_data() 包含所有预期字段")
        print(f"    字段列表: {list(data.keys())}")
    else:
        print(f"  ✗ get_data() 缺少字段: {missing}")

    # ==================== 测试总结 ====================
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    status = mqtt.get_status()
    print(f"\n模块状态:")
    print(f"  is_init:       {status['is_init']}")
    print(f"  is_connected:  {status['is_connected']}")
    print(f"  err_count:     {status['err_count']}")
    print(f"  mqtt_state:    {status['mqtt_state']}")
    print(f"  event_log:     {len(event_log)} 条事件")
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_mqtt()
