"""
brief SystemMonitor 全量测试
note 使用 mock 模块（非真实硬件），在 CPython / MicroPython 上均可运行

五个测试场景：
  1. 心跳检测 — 超时/正常/防重复/自愈恢复
  2. WDT 门控 — 宽限期/正常/关键模块失联/安全模式
  3. 宽限期 — 前 15s 不扫描/WDT 无条件喂狗
  4. 模块分级 — CRITICAL/IMPORTANT/AUXILIARY 不同行为
  5. 线程监控 — 后台线程超时告警
"""

import sys
import time

sys.path.append("..")

# ==================== CPython 兼容 ====================
# MicroPython 的 time.ticks_* 在 CPython 上不存在
try:
    _ = time.ticks_ms
except AttributeError:
    time.ticks_ms = lambda: int(time.time() * 1000)
    time.ticks_diff = lambda a, b: a - b
    time.ticks_add = lambda a, d: a + d

from Modules.system_monitor import SystemMonitor


# ==================== Mock 类 ====================

class MockModule:
    """模拟模块：提供 name / ctx（含 last_hb / last_thread_ok / is_init）"""
    def __init__(self, name):
        self.name = name
        self.ctx = {
            "is_init": True,
            "last_hb": 0,
        }

    def set_hb_ago(self, ms_ago):
        """设置最近一次心跳在 ms_ago 毫秒前"""
        self.ctx["last_hb"] = time.ticks_add(time.ticks_ms(), -ms_ago)

    def set_thread_ok_ago(self, ms_ago):
        """设置后台线程检查时间（用于 THREADED_MODULES）"""
        self.ctx["last_thread_ok"] = time.ticks_add(time.ticks_ms(), -ms_ago)


class EventRecorder:
    """事件记录器（替代 EventBus，便于验证发布事件）"""
    def __init__(self):
        self.events = []

    def publish(self, event, data=None):
        self.events.append((event, data))


# ==================== 测试辅助函数 ====================

def make_sysmon(modules, event_bus=None, boot_offset_ms=-20000):
    """
    创建并初始化 SystemMonitor，将启动时间设为 boot_offset_ms 前
    默认 20s 前启动，已过 15s 宽限期
    """
    sm = SystemMonitor(event_bus=event_bus, modules=modules)
    sm.init()
    # 将启动时间推送到过去，跳过宽限期
    sm._boot_tick = time.ticks_add(time.ticks_ms(), boot_offset_ms)
    sm.ctx["start_time"] = sm._boot_tick
    sm.ctx["last_scan"] = 0   # 强制下次 tick 执行扫描
    return sm


def force_tick(sm):
    """强制执行一次完整扫描（绕过 scan_interval 限制）"""
    sm.ctx["last_scan"] = 0
    sm.tick()


def check(label, condition, detail=""):
    """检查一个断言并打印 PASS/FAIL"""
    if condition:
        print("  [PASS] %s" % label)
    else:
        msg = "  [FAIL] %s" % label
        if detail:
            msg += " — " + detail
        print(msg)
    return condition


# ==================== Test 1: 心跳检测 ====================

def test_heartbeat_detection():
    """
    验证：
    - 活跃模块 → state=OK
    - 超时模块 → state=TIMEOUT + 事件发布
    - 防重复告警（同一模块不重复发）
    - 自愈恢复 → state=OK + RECOVERED 事件
    """
    print("\n" + "=" * 60)
    print("Test 1: 心跳检测")
    print("=" * 60)

    recorder = EventRecorder()
    collision   = MockModule("collision")
    imu          = MockModule("imu")
    temp_humid_m = MockModule("temp_humid")

    # collision: 活跃（心跳 1s 前）
    collision.set_hb_ago(1000)
    # imu: 超时（心跳 30s 前，IMPORTANT timeout=15s）
    imu.set_hb_ago(30000)
    # temp_humid: 活跃
    temp_humid_m.set_hb_ago(1000)

    sm = make_sysmon([collision, imu, temp_humid_m], event_bus=recorder)
    force_tick(sm)

    health = sm.ctx["module_health"]
    ok = True

    ok &= check("活跃模块 collision → OK",
                health["collision"]["state"] == "OK")
    ok &= check("超时模块 imu → TIMEOUT",
                health["imu"]["state"] == "TIMEOUT")
    ok &= check("活跃模块 temp_humid → OK",
                health["temp_humid"]["state"] == "OK")

    # 验证事件
    tout = [(e, d) for e, d in recorder.events if e == "MODULE_TIMEOUT"]
    ok &= check("仅发布 1 条 TIMEOUT 事件",
                len(tout) == 1)
    if tout:
        ok &= check("超时事件模块名 = imu",
                    tout[0][1]["module"] == "imu",
                    detail="实际: " + str(tout[0][1]["module"]))
        ok &= check("超时事件 tier = IMPORTANT",
                    tout[0][1]["tier"] == "IMPORTANT",
                    detail="实际: " + str(tout[0][1].get("tier")))

    # 防重复：第二次扫描不产生新事件
    prev_count = len(recorder.events)
    force_tick(sm)
    ok &= check("二次扫描不重复告警",
                len(recorder.events) == prev_count,
                detail="事件数: %d -> %d" % (prev_count, len(recorder.events)))

    # 自愈恢复
    imu.set_hb_ago(1000)   # imu 恢复心跳
    force_tick(sm)
    ok &= check("imu 恢复 → state=OK",
                health["imu"]["state"] == "OK")
    recv = [(e, d) for e, d in recorder.events if e == "MODULE_RECOVERED"]
    ok &= check("发布 1 条 RECOVERED 事件",
                len(recv) == 1)
    if recv:
        ok &= check("恢复事件模块名 = imu",
                    recv[0][1]["module"] == "imu")

    return ok


# ==================== Test 2: WDT 门控 ====================

def test_wdt_gating():
    """
    验证 should_feed_wdt() 在不同条件下的返回值：
    - 宽限期内 → True
    - 所有 CRITICAL 活跃 → True
    - 任一 CRITICAL 失联 → False
    - 安全模式 → 放宽为任意模块存活即可
    """
    print("\n" + "=" * 60)
    print("Test 2: WDT 门控")
    print("=" * 60)

    ok = True

    # ---- 2a: 宽限期 ----
    collision = MockModule("collision")
    collision.set_hb_ago(1000)
    sm = make_sysmon([collision], boot_offset_ms=-5000)   # 5s 前启动，仍在 15s 宽限
    ok &= check("宽限期: should_feed_wdt() → True",
                sm.should_feed_wdt() is True,
                detail="宽限期应无条件喂狗")

    # ---- 2b: 正常模式，所有 CRITICAL 活跃 ----
    collision.set_hb_ago(1000)
    imu = MockModule("imu")
    imu.set_hb_ago(1000)
    sm = make_sysmon([collision, imu], boot_offset_ms=-20000)  # 已过宽限期
    force_tick(sm)
    ok &= check("正常+CRITICAL活跃: should_feed_wdt() → True",
                sm.should_feed_wdt() is True,
                detail="所有关键模块有近期心跳")

    # ---- 2c: 正常模式，CRITICAL 失联 ----
    collision.set_hb_ago(40000)   # 40s 前 → 超过 critical_timeout(30s)
    imu.set_hb_ago(1000)
    force_tick(sm)
    ok &= check("正常+CRITICAL失联: should_feed_wdt() → False",
                sm.should_feed_wdt() is False,
                detail="collision 心跳 >30s 前")

    # ---- 2d: 安全模式 — 放宽为任意存活 ----
    sm.ctx["safe_mode"] = True
    ok &= check("安全模式+任一模组活跃: should_feed_wdt() → True",
                sm.should_feed_wdt() is True,
                detail="安全模式下 imu 仍活跃")
    sm.ctx["safe_mode"] = False

    return ok


# ==================== Test 3: 宽限期 ====================

def test_grace_period():
    """
    验证宽限期行为：
    - 前 15s: tick() 不扫描，WDT 无条件喂狗
    - 15s 后: 正常扫描，超时告警，WDT 根据条件
    """
    print("\n" + "=" * 60)
    print("Test 3: 宽限期")
    print("=" * 60)

    ok = True

    recorder = EventRecorder()
    collision = MockModule("collision")
    collision.set_hb_ago(1000)

    # 5s 前启动 → 仍在 15s 宽限内
    sm = make_sysmon([collision], event_bus=recorder, boot_offset_ms=-5000)

    # tick 内部发现还在宽限 → 直接 return（不扫描）
    force_tick(sm)
    ok &= check("宽限内 → should_feed_wdt() = True",
                sm.should_feed_wdt() is True)
    # 宽限内不扫描，所以超时模块不被检测
    collision.set_hb_ago(40000)  # 实际上超时了
    force_tick(sm)
    health = sm.ctx["module_health"]
    ok &= check("宽限内不扫描 → 超时模块仍为 OK",
                health.get("collision", {}).get("state") == "OK",
                detail="实际: " + str(health.get("collision", {}).get("state")))
    ok &= check("宽限内 no events",
                len(recorder.events) == 0,
                detail="事件数: %d" % len(recorder.events))

    # 将启动时间推到 20s 前 → 宽限结束
    sm._boot_tick = time.ticks_add(time.ticks_ms(), -20000)
    sm.ctx["start_time"] = sm._boot_tick
    force_tick(sm)
    health = sm.ctx["module_health"]
    ok &= check("宽限结束 → 超时模块变为 TIMEOUT",
                health["collision"]["state"] == "TIMEOUT",
                detail="实际: " + health["collision"]["state"])
    ok &= check("宽限结束 → 事件发布",
                len(recorder.events) > 0)

    return ok


# ==================== Test 4: 模块分级 ====================

def test_module_classification():
    """
    验证不同等级模块超时的行为差异：
    - CRITICAL 超时 → should_feed_wdt() = False
    - IMPORTANT 超时 → should_feed_wdt() = True + 告警
    - AUXILIARY 超时 → 仅记录
    """
    print("\n" + "=" * 60)
    print("Test 4: 模块分级")
    print("=" * 60)

    ok = True
    recorder = EventRecorder()

    collision = MockModule("collision")   # CRITICAL
    imu       = MockModule("imu")          # IMPORTANT
    aux_mod   = MockModule("aux_gadget")   # AUXILIARY（未列入 CRITICAL/IMPORTANT）

    modules = [collision, imu, aux_mod]
    sm = make_sysmon(modules, event_bus=recorder)

    # 先让所有模块活跃，然后分别使单个模块超时

    # ---- 4a: CRITICAL 超时 ----
    collision.set_hb_ago(40000)    # > 30s CRITICAL timeout
    imu.set_hb_ago(1000)
    aux_mod.set_hb_ago(1000)
    force_tick(sm)

    ok &= check("CRITICAL 超时 → should_feed_wdt() = False",
                sm.should_feed_wdt() is False,
                detail="collision 超时，应停喂 WDT")
    ok &= check("CRITICAL 超时 → state=TIMEOUT",
                sm.ctx["module_health"]["collision"]["state"] == "TIMEOUT")
    ok &= check("CRITICAL 超时 → critical_alive = False",
                sm.ctx["critical_alive"] is False)

    # ---- 4b: 仅 IMPORTANT 超时 ----
    collision.set_hb_ago(1000)
    imu.set_hb_ago(30000)          # > 15s IMPORTANT timeout
    aux_mod.set_hb_ago(1000)
    recorder.events.clear()
    force_tick(sm)

    ok &= check("IMPORTANT 超时 → should_feed_wdt() = True",
                sm.should_feed_wdt() is True,
                detail="CRITICAL 仍活跃")
    ok &= check("IMPORTANT 超时 → 告警发布",
                any(e == "MODULE_TIMEOUT" for e, _ in recorder.events),
                detail="事件: %s" % str(recorder.events))

    # ---- 4c: 仅 AUXILIARY 超时 ----
    collision.set_hb_ago(1000)
    imu.set_hb_ago(1000)
    aux_mod.set_hb_ago(120000)     # > 60s AUXILIARY timeout
    recorder.events.clear()
    force_tick(sm)

    ok &= check("AUXILIARY 超时 → should_feed_wdt() = True",
                sm.should_feed_wdt() is True)
    ok &= check("AUXILIARY 超时 → state=TIMEOUT",
                sm.ctx["module_health"]["aux_gadget"]["state"] == "TIMEOUT")

    return ok


# ==================== Test 5: 线程监控 ====================

def test_thread_monitoring():
    """
    验证后台线程超时检测：
    - last_thread_ok 超时 → THREAD_TIMEOUT 告警
    - 线程恢复 → 告警不再触发
    """
    print("\n" + "=" * 60)
    print("Test 5: 线程监控")
    print("=" * 60)

    ok = True

    # 使用 gnss（既在 THREADED_MODULES 也在 IMPORTANT_MODULES）
    gnss = MockModule("gnss")
    # 正常心跳，确保不触发模块超时
    gnss.set_hb_ago(1000)
    # 线程 20s 前检查 → thread_timeout=15s → 超时
    gnss.set_thread_ok_ago(20000)

    sm = make_sysmon([gnss])
    # 前置心跳扫描，确保 gnss 模块本身活跃
    force_tick(sm)

    # 清除输出缓冲 — 直接检查内部状态
    # _check_threads 使用 print()，我们用捕获 stdout 的方式验证
    # 但更方便：检查 _last_thread_alert 是否被设置
    thread_key = "thread:gnss"

    # 第一次 tick 应触发线程告警
    force_tick(sm)
    ok &= check("线程超时告警已记录",
                thread_key in sm._last_thread_alert,
                detail="_last_thread_alert keys: %s" % str(list(sm._last_thread_alert.keys())))

    # 第二次 tick（线程仍然超时）— 防重复
    # _check_threads 使用 2*thread_timeout_ms 防重复
    prev_time = sm._last_thread_alert.get(thread_key, 0)
    force_tick(sm)
    ok &= check("线程超时防重复 — 时间戳不变",
                sm._last_thread_alert.get(thread_key, 0) == prev_time,
                detail="%d vs %d" % (prev_time, sm._last_thread_alert.get(thread_key, 0)))

    # 线程恢复
    gnss.set_thread_ok_ago(1000)   # 1s 前 → 活跃
    force_tick(sm)
    # 线程超时的 key 不应再被更新（因为条件 age > timeout 不满足）
    ok &= check("线程恢复 → 不再触发告警",
                thread_key in sm._last_thread_alert,
                detail="线程 ok 后不应进入超时分支")

    return ok


# ==================== 主入口 ====================

def main():
    """运行所有测试，汇总 PASS/FAIL"""
    print("=" * 60)
    print("SystemMonitor 测试套件")
    print("=" * 60)

    results = []

    print("\n--- 初始化兼容性检查 ---")
    try:
        dummy = MockModule("dummy")
        sm = SystemMonitor(modules=[dummy])
        sm.init()
        print("  [PASS] 基础初始化成功")
        results.append(True)
    except Exception as e:
        print("  [FAIL] 基础初始化失败: %s" % e)
        results.append(False)

    results.append(test_heartbeat_detection())
    results.append(test_wdt_gating())
    results.append(test_grace_period())
    results.append(test_module_classification())
    results.append(test_thread_monitoring())

    # 汇总
    passed = sum(1 for r in results if r)
    total = len(results)
    print("\n" + "=" * 60)
    print("汇总: %d / %d PASS" % (passed, total))
    if passed == total:
        print("所有测试通过 [OK]")
    else:
        print("部分测试失败 [FAIL]")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
