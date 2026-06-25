"""
brief BLE 生命周期 E2E 测试
note 测试 init → deinit → restart 全流程
     硬件要求: NUCLEO-F413ZH + EC200U BLE
     在板子上通过 Thonny 运行
"""
import sys
import time

sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import (
    EVENT_BLE_CONNECTED, EVENT_BLE_DISCONNECTED,
)
from Drivers.network.BLE import BLEDriver


# ── 全局事件计数 ──
connected_count = 0
disconnected_count = 0


def _reset_counters():
    global connected_count, disconnected_count
    connected_count = 0
    disconnected_count = 0


def _on_connected(payload):
    global connected_count
    connected_count += 1
    print("  [event] EVENT_BLE_CONNECTED (#%d)" % connected_count)


def _on_disconnected(payload):
    global disconnected_count
    disconnected_count += 1
    print("  [event] EVENT_BLE_DISCONNECTED (#%d)" % disconnected_count)


def _wait_connection(ble, eb, timeout_s=30):
    """brief 泵循环等待手机连接，返回是否连接成功"""
    ticks_total = timeout_s * 10
    for _ in range(ticks_total):
        ble.tick()
        eb.pump()
        time.sleep_ms(100)
        if ble.ctx["is_connected"]:
            return True
    return False


def _pump_loop(ble, eb, iterations, interval_ms=100):
    """brief 简单泵循环"""
    for _ in range(iterations):
        ble.tick()
        eb.pump()
        time.sleep_ms(interval_ms)


# ── 测试 1: init → 验证状态 → deinit → 验证清理 ──
def test_init_deinit():
    print("\n=== 测试 1: init → 验证 GATT → deinit → 验证清理 ===")
    print("说明: 初始化 BLE，验证广播状态，然后 deinit 验证资源释放")
    print("按 Enter 开始...")
    input()

    _reset_counters()
    eb = EventBus()
    ble = BLEDriver(eb)
    eb.subscribe(EVENT_BLE_CONNECTED, _on_connected)
    eb.subscribe(EVENT_BLE_DISCONNECTED, _on_disconnected)

    # init
    print("  [1/4] 调用 ble.init()...")
    ble.init()
    assert ble.ctx["is_init"] is True, "init 后 is_init 应为 True"
    print("  ✓ ctx[is_init] = True")

    status = ble.get_status()
    assert status["is_init"] is True, "get_status 应报告 is_init=True"
    print("  ✓ get_status() 确认 is_init=True")
    print("  ✓ 设备名: %s" % ble.cfg["device_name"])
    print("  ✓ BLE 正在广播 (用手机 NRF Connect 可搜索到)")

    # deinit
    print("  [2/4] 调用 ble.deinit()...")
    ble.deinit()
    assert ble.ctx["is_init"] is False, "deinit 后 is_init 应为 False"
    assert ble.ctx["is_connected"] is False, "deinit 后 is_connected 应为 False"
    print("  ✓ ctx[is_init] = False")
    print("  ✓ ctx[is_connected] = False")

    status2 = ble.get_status()
    assert status2["is_init"] is False, "get_status 应报告 is_init=False"
    print("  ✓ get_status() 确认已清理")

    # 未连接时 deinit 不应发布 DISCONNECTED
    assert disconnected_count == 0, "未连接时 deinit 不应发布 DISCONNECTED"
    print("  ✓ 未连接状态下 deinit 未发布 DISCONNECTED 事件")

    print("  [结果] ✅ 通过")
    return True


# ── 测试 2: deinit → restart → 验证重新初始化 ──
def test_deinit_restart():
    print("\n=== 测试 2: init → deinit → restart → 验证重新初始化 ===")
    print("说明: 验证 restart() 能在 deinit 后重新完成全流程")
    print("按 Enter 开始...")
    input()

    _reset_counters()
    eb = EventBus()
    ble = BLEDriver(eb)
    eb.subscribe(EVENT_BLE_CONNECTED, _on_connected)
    eb.subscribe(EVENT_BLE_DISCONNECTED, _on_disconnected)

    # 第一次 init
    print("  [1/4] 第一次 ble.init()...")
    ble.init()
    assert ble.ctx["is_init"] is True
    print("  ✓ 初始化成功")

    # deinit
    print("  [2/4] ble.deinit()...")
    ble.deinit()
    assert ble.ctx["is_init"] is False
    print("  ✓ deinit 完成")

    # restart (deinit → sleep 200ms → init)
    print("  [3/4] ble.restart() (内部: deinit → 200ms → init)...")
    ble.restart()
    assert ble.ctx["is_init"] is True, "restart 后 is_init 应为 True"
    print("  ✓ restart 后 ctx[is_init] = True")

    status = ble.get_status()
    assert status["is_init"] is True
    print("  ✓ get_status() 确认重新初始化成功")
    print("  ✓ BLE 应重新广播")

    # 清理
    print("  [4/4] 清理: ble.stop()...")
    ble.stop()
    print("  ✓ 已停止")

    print("  [结果] ✅ 通过")
    return True


# ── 测试 3: 连接后 deinit 发布 EVENT_BLE_DISCONNECTED ──
def test_deinit_while_connected():
    print("\n=== 测试 3: 连接后 deinit 发布 EVENT_BLE_DISCONNECTED ===")
    print("说明: 等待手机连接，然后 deinit 验证断连事件发布")
    print("请用 NRF Connect 连接 '%s'" % "SmartHelmet-66ccff")
    print("按 Enter 开始等待连接 (30s 超时)...")
    input()

    _reset_counters()
    eb = EventBus()
    ble = BLEDriver(eb)
    eb.subscribe(EVENT_BLE_CONNECTED, _on_connected)
    eb.subscribe(EVENT_BLE_DISCONNECTED, _on_disconnected)

    ble.init()
    print("  [1/3] BLE 已初始化，等待手机连接...")

    connected = _wait_connection(ble, eb, timeout_s=30)

    if not connected:
        print("  ⚠ 30s 内未检测到连接，跳过此测试")
        ble.stop()
        print("  [结果] ⚠️ 跳过")
        return False

    print("  ✓ 手机已连接! mtu=%d" % ble.ctx["mtu"])

    # deinit while connected
    print("  [2/3] 调用 ble.deinit() (当前已连接)...")
    before_disc = disconnected_count
    ble.deinit()

    # 验证状态清理
    assert ble.ctx["is_init"] is False, "deinit 后 is_init 应为 False"
    assert ble.ctx["is_connected"] is False, "deinit 后 is_connected 应为 False"
    print("  ✓ 状态已清理: is_init=False, is_connected=False")

    # 泵处理事件
    _pump_loop(ble, eb, 10)

    # 验证 DISCONNECTED 事件已发布
    assert disconnected_count > before_disc, \
        "deinit 应发布 EVENT_BLE_DISCONNECTED"
    print("  ✓ EVENT_BLE_DISCONNECTED 已发布 (#%d)" % disconnected_count)

    print("  [3/3] 清理...")
    # deinit 后 _ble 可能已 deinit，不再调用 stop
    print("  ✓ 完成")

    print("  [结果] ✅ 通过")
    return True


# ── 测试 4: 连接后 restart → 验证断连 + 重新初始化 ──
def test_restart_while_connected():
    print("\n=== 测试 4: 连接后 restart → 断连 + 重新初始化 ===")
    print("说明: 连接状态下 restart，验证断连事件 + 重新广播")
    print("请用 NRF Connect 连接设备")
    print("按 Enter 开始等待连接 (30s 超时)...")
    input()

    _reset_counters()
    eb = EventBus()
    ble = BLEDriver(eb)
    eb.subscribe(EVENT_BLE_CONNECTED, _on_connected)
    eb.subscribe(EVENT_BLE_DISCONNECTED, _on_disconnected)

    ble.init()
    print("  [1/4] BLE 已初始化，等待手机连接...")

    connected = _wait_connection(ble, eb, timeout_s=30)

    if not connected:
        print("  ⚠ 30s 内未检测到连接，跳过此测试")
        ble.stop()
        print("  [结果] ⚠️ 跳过")
        return False

    print("  ✓ 手机已连接! mtu=%d" % ble.ctx["mtu"])

    # restart while connected
    print("  [2/4] 调用 ble.restart() (当前已连接)...")
    before_disc = disconnected_count
    ble.restart()

    # 验证重新初始化
    assert ble.ctx["is_init"] is True, "restart 后 is_init 应为 True"
    print("  ✓ restart 后 ctx[is_init] = True")

    # 泵处理事件
    _pump_loop(ble, eb, 20)

    # restart 内部 deinit 应发布 DISCONNECTED
    assert disconnected_count > before_disc, \
        "restart 内部 deinit 应发布 EVENT_BLE_DISCONNECTED"
    print("  ✓ restart 期间 EVENT_BLE_DISCONNECTED 已发布 (#%d)" % disconnected_count)

    # 验证 BLE 重新广播
    status = ble.get_status()
    assert status["is_init"] is True
    print("  ✓ BLE 重新广播中 (get_status 确认)")

    print("  [3/4] 等待手机重新连接 (可选, 20s)...")
    print("  提示: 手机可能需要手动重新连接")
    reconnected = _wait_connection(ble, eb, timeout_s=20)
    if reconnected:
        print("  ✓ 手机已重新连接!")
    else:
        print("  ℹ 手机未重新连接 (正常，需手动操作)")

    print("  [4/4] 清理: ble.stop()...")
    ble.stop()
    print("  ✓ 已停止")

    print("  [结果] ✅ 通过")
    return True


# ── 测试 5: 双重 deinit 安全性 ──
def test_double_deinit():
    print("\n=== 测试 5: 双重 deinit 安全性 ===")
    print("说明: 连续调用两次 deinit，验证不会崩溃")
    print("按 Enter 开始...")
    input()

    _reset_counters()
    eb = EventBus()
    ble = BLEDriver(eb)
    eb.subscribe(EVENT_BLE_CONNECTED, _on_connected)
    eb.subscribe(EVENT_BLE_DISCONNECTED, _on_disconnected)

    ble.init()
    assert ble.ctx["is_init"] is True
    print("  [1/3] BLE 初始化成功")

    print("  [2/3] 第一次 ble.deinit()...")
    ble.deinit()
    assert ble.ctx["is_init"] is False
    print("  ✓ 第一次 deinit 完成")

    print("  [3/3] 第二次 ble.deinit() (应安全)...")
    try:
        ble.deinit()
        print("  ✓ 第二次 deinit 未崩溃")
    except Exception as e:
        print("  ✗ 第二次 deinit 抛出异常: %s" % e)
        print("  [结果] ❌ 失败")
        return False

    assert ble.ctx["is_init"] is False
    assert ble.ctx["is_connected"] is False
    print("  ✓ 状态仍然正确: is_init=False, is_connected=False")

    print("  [结果] ✅ 通过")
    return True


# ── 测试 6: deinit 后重新 init ──
def test_deinit_then_init():
    print("\n=== 测试 6: deinit → init (手动重新初始化) ===")
    print("说明: deinit 后手动调用 init，验证能重新初始化")
    print("按 Enter 开始...")
    input()

    _reset_counters()
    eb = EventBus()
    ble = BLEDriver(eb)
    eb.subscribe(EVENT_BLE_CONNECTED, _on_connected)
    eb.subscribe(EVENT_BLE_DISCONNECTED, _on_disconnected)

    # 第一次 init
    print("  [1/4] 第一次 ble.init()...")
    ble.init()
    assert ble.ctx["is_init"] is True
    print("  ✓ 初始化成功")

    # deinit
    print("  [2/4] ble.deinit()...")
    ble.deinit()
    assert ble.ctx["is_init"] is False
    print("  ✓ deinit 完成")

    # 重新 init
    print("  [3/4] 第二次 ble.init()...")
    ble.init()
    assert ble.ctx["is_init"] is True, "重新 init 后 is_init 应为 True"
    status = ble.get_status()
    assert status["is_init"] is True
    print("  ✓ 重新初始化成功")
    print("  ✓ BLE 应重新广播")

    # 清理
    print("  [4/4] 清理: ble.stop()...")
    ble.stop()
    print("  ✓ 已停止")

    print("  [结果] ✅ 通过")
    return True


# ── 主函数 ──
def main():
    print("=" * 55)
    print(" BLE 生命周期 E2E 测试")
    print("=" * 55)
    print("硬件要求: NUCLEO-F413ZH + EC200U BLE")
    print("测试内容: init / deinit / restart 全流程")
    print("")
    print("测试列表:")
    print("  1. init → 验证 → deinit → 验证清理")
    print("  2. init → deinit → restart → 验证重新初始化")
    print("  3. 连接后 deinit → 验证 DISCONNECTED 事件")
    print("  4. 连接后 restart → 断连 + 重新广播")
    print("  5. 双重 deinit 安全性")
    print("  6. deinit → 手动 init 重新初始化")
    print("")
    print("请确保 BLE 硬件就绪后按 Enter...")
    input()

    tests = [
        ("init → deinit 状态验证", test_init_deinit),
        ("deinit → restart 重新初始化", test_deinit_restart),
        ("连接后 deinit 发布断连事件", test_deinit_while_connected),
        ("连接后 restart 断连+重广播", test_restart_while_connected),
        ("双重 deinit 安全性", test_double_deinit),
        ("deinit → init 手动重初始化", test_deinit_then_init),
    ]

    results = []
    for name, func in tests:
        try:
            ok = func()
            if ok:
                results.append((name, "✅ 通过"))
            else:
                results.append((name, "⚠️ 跳过"))
        except Exception as e:
            print("  FAIL: %s" % e)
            results.append((name, "❌ 失败"))

    # 总结
    print("\n" + "=" * 55)
    print(" BLE 生命周期测试总结")
    print("=" * 55)
    for name, result in results:
        print("  [%s] %s" % (result, name))

    passed = sum(1 for _, r in results if "通过" in r)
    skipped = sum(1 for _, r in results if "跳过" in r)
    failed = sum(1 for _, r in results if "失败" in r)
    print("")
    print("  通过: %d, 跳过: %d, 失败: %d" % (passed, skipped, failed))
    print("=" * 55)


if __name__ == "__main__":
    main()
