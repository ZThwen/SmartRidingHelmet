"""
brief 4G网络驱动单模块测试脚本
note 用于验证 NetworkDriver 的各项公共接口功能是否正常
     需要插入SIM卡且在4G信号覆盖区域
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_CONFIG_UPDATE
from Drivers.network.Network import NetworkDriver, NET_STATE_DISCONNECTED, NET_STATE_CONNECTED


event_log = []


def on_config_update(payload):
    event_log.append(("CONFIG_UPDATE", payload))
    print(f"\n[事件回调] EVENT_CONFIG_UPDATE")
    print(f"  target: {payload.get('target')}")


def test_network():
    print("=" * 60)
    print("4G网络驱动单模块测试")
    print("=" * 60)

    event_bus = EventBus()
    event_bus.debug = True

    event_bus.subscribe(EVENT_CONFIG_UPDATE, on_config_update)

    net = NetworkDriver(event_bus)

    # ==================== 测试 1：初始化 ====================
    print("\n" + "-" * 60)
    print("[测试 1] 初始化模块")
    print("-" * 60)
    try:
        net.init()
        print("\n✓ 初始化成功")
    except Exception as e:
        print(f"\n✗ 初始化失败: {e}")
        return

    # ==================== 测试 2：状态查询 ====================
    print("\n" + "-" * 60)
    print("[测试 2] 查看模块状态")
    print("-" * 60)
    status = net.get_status()
    data = net.get_data()
    print(f"  is_init:      {status['is_init']}")
    print(f"  err_count:    {status['err_count']}")
    print(f"  power_state:  {status['power_state']}")
    print(f"  net_state:    {status['net_state']}")
    print(f"  sim_present:  {data['sim_present']}")

    if data["valid"]:
        print(f"  ip:           {data['ip']}")
    else:
        print("  ip:           未连接")

    # ==================== 测试 3：4G 连接测试 ====================
    print("\n" + "-" * 60)
    print("[测试 3] 4G 网络连接测试")
    print("-" * 60)
    print("  正在连接 4G 网络（超时 60 秒）...")
    result = net.connect()
    if result:
        print("  ✓ 4G 网络连接成功")
    else:
        print("  ✗ 4G 网络连接失败（请检查 SIM 卡和信号）")

    # ==================== 测试 4：连接状态查询 ====================
    print("\n" + "-" * 60)
    print("[测试 4] 连接状态验证")
    print("-" * 60)
    connected = net.is_connected()
    print(f"  is_connected(): {connected}")
    data = net.get_data()
    print(f"  net_state:      {data['net_state']}")
    print(f"  valid:          {data['valid']}")
    print(f"  {'✓ 连接状态正常' if connected else '✗ 连接状态异常'}")

    # ==================== 测试 5：配置更新 ====================
    print("\n" + "-" * 60)
    print("[测试 5] 配置更新测试")
    print("-" * 60)
    print(f"\n  更新前 timeout: {net.cfg['connect_timeout_ms']}ms")
    event_bus.publish(EVENT_CONFIG_UPDATE, {
        "target": "network",
        "connect_timeout_ms": 30000
    })
    event_bus.pump()
    time.sleep_ms(100)
    print(f"  更新后 timeout: {net.cfg['connect_timeout_ms']}ms")
    print(f"  {'✓ 配置更新成功' if net.cfg['connect_timeout_ms'] == 30000 else '✗ 配置更新失败'}")

    # ==================== 测试 6：断开连接 ====================
    print("\n" + "-" * 60)
    print("[测试 6] 断开网络连接")
    print("-" * 60)
    result = net.disconnect()
    status = net.get_status()
    print(f"  disconnect():   {'✓' if result else '✗'}")
    print(f"  断开后状态:      {status['net_state']} (期望: {NET_STATE_DISCONNECTED})")
    print(f"  {'✓ 断开成功' if result and status['net_state'] == NET_STATE_DISCONNECTED else '✗ 断开异常'}")

    # ==================== 测试 7：数据字段完整性 ====================
    print("\n" + "-" * 60)
    print("[测试 7] 数据字段完整性验证")
    print("-" * 60)
    data = net.get_data()
    expected_fields = ["ip", "sim_present", "valid", "net_state", "timestamp"]
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
    status = net.get_status()
    print(f"\n模块状态:")
    print(f"  is_init:   {status['is_init']}")
    print(f"  err_count: {status['err_count']}")
    print(f"  net_state: {status['net_state']}")
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    test_network()
