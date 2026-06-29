"""
brief SystemMonitor — 系统监控服务：心跳扫描 + WDT 门控
note 非侵入式监控层，只读模块 ctx["last_hb"]，不修改模块内部状态

架构：
  main.py 主循环 → sysmon.tick() → 心跳扫描 → should_feed_wdt() → wdt.feed()

模块分级：
  CRITICAL  （碰撞/报警/BLE） — 失联 → 停喂 WDT
  IMPORTANT（传感器/显示）   — 失联 → 告警
  AUXILIARY（其余）         — 失联 → 仅记录

关键规则：
  - 每 5 秒全量扫描（非扫描轮次 <0.5ms）
  - 宽限期 15s 内无条件喂狗
  - 安全模式：连续 5 次 WDT 复位后放宽检测条件
  - 后台线程超时仅告警，不尝试重启
"""

import time

from core.Base_Module import BaseModule


# 本地事件常量（暂不引入 config.py，后续迁移）
EVENT_MODULE_TIMEOUT   = "MODULE_TIMEOUT"
EVENT_MODULE_RECOVERED = "MODULE_RECOVERED"


class SystemMonitor(BaseModule):
    """
    系统监控服务。

    功能：
    1. 扫描所有模块心跳（ctx["last_hb"]）
    2. 模块超时检测 + 防重复告警 + 自愈恢复检测
    3. WDT 喂狗决策（should_feed_wdt）
    4. 启动宽限期内无条件喂狗
    5. 安全模式：连续 WDT 复位后放宽检测
    6. 后台线程健康检查
    """

    # ==================== 模块分级定义 ====================
    # CRITICAL：失联时停喂 WDT（系统核心安全功能）
    CRITICAL_MODULES = [
        "collision",       # CollisionService — 碰撞检测
        "alarm",           # AlarmService — 报警流程
        "ble_service",     # BLEService — BLE 通信（唯一用户通道）
    ]

    # IMPORTANT：失联时告警（功能降级运行）
    IMPORTANT_MODULES = [
        "temp_humid",      # TempHumidDriver — 温湿度
        "imu",             # IMUDriver — 加速度
        "gnss",            # GNSSDriver — 定位
        "heartrate",       # HeartRateDriver — 心率血氧
        "ble",             # BLEDriver — BLE 硬件驱动
        "audio",           # AudioDriver — 音频输出
        "audio_service",   # AudioService — 音频服务
        "display",         # DisplayService — 显示服务
    ]

    # 有后台线程的模块名（需额外检查 last_thread_ok）
    THREADED_MODULES = [
        "gnss",
        "audio_service",
        "ble_service",
    ]

    def __init__(self, event_bus=None, modules=None):
        """
        brief 初始化系统监控实例
        param event_bus: 事件总线实例（可选）
        param modules: 所有模块实例列表
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "system_monitor"

        # 保存模块列表并建立名称映射
        self._modules = modules if modules is not None else []
        self._module_map = {}
        for mod in self._modules:
            if hasattr(mod, 'name'):
                self._module_map[mod.name] = mod

        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            "scan_interval_ms":      5000,   # 心跳扫描间隔 (ms)
            "grace_ms":              15000,  # 启动宽限期 (ms)
            "critical_timeout_ms":   30000,  # CRITICAL 模块超时 (ms)
            "important_timeout_ms":  15000,  # IMPORTANT 模块超时 (ms)
            "auxiliary_timeout_ms":  60000,  # AUXILIARY 模块超时 (ms)
            "safe_mode_threshold":   5,      # 连续 WDT 复位次数 → 安全模式
            "thread_timeout_ms":     15000,  # 后台线程超时 (ms)
            "safe_mode_exit_ms":     300000, # 安全模式退出时间 (5 分钟)
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init":         False,
            "start_time":      0,            # 启动时间戳（ticks_ms）
            "last_scan":       0,            # 上次扫描时间戳
            "safe_mode":       False,        # 安全模式标志
            "reset_count":     0,            # 连续 WDT 复位计数
            "critical_alive":  True,         # 所有关键模块存活
            "any_alive":       True,         # 任一模块存活（安全模式用）
            "module_health":   {},           # {name: {state, age_ms, tier, timeout_ms}}
        }

        # ===================== 内部状态 =====================
        self._boot_tick = 0                   # 启动 tick（init 时记录）
        self._grace_reported = False          # 宽限期日志是否已打印
        self._last_alert_time = {}            # {name: ticks_ms} 防重复告警
        self._last_thread_alert = {}          # {name: ticks_ms} 线程超时防重复

        # 分级列表（init 时填充）
        self._critical = []                   # CRITICAL 模块实例列表
        self._important = []                  # IMPORTANT 模块实例列表
        self._auxiliary = []                  # AUXILIARY 模块实例列表
        self._threaded = []                   # 有后台线程的模块实例列表

    # ==================== 核心生命周期 ====================

    def init(self):
        """
        brief 初始化：记录启动时间、模块分级、复位计数、安全模式检测
        note 在 main.py 初始化顺序中最后执行
        """
        try:
            # 1. 记录启动时间
            self._boot_tick = time.ticks_ms()
            self.ctx["start_time"] = self._boot_tick

            # 2. 模块分级
            self._classify_modules()

            # 3. 检测复位原因（WDT 复位 → 递增计数，非 WDT → 清零）
            self._check_reset_cause()

            # 4. 判断是否进入安全模式
            self._check_safe_mode()

            # 5. 初始化模块健康状态
            for mod in self._modules:
                name = mod.name if hasattr(mod, 'name') else "unknown"
                self.ctx["module_health"][name] = {
                    "state": "OK",
                    "age_ms": 0,
                    "tier": self._get_tier(name),
                    "timeout_ms": self._get_timeout(name),
                    "last_hb": 0,
                }

            self.ctx["is_init"] = True
            print("[system_monitor] init OK (reset_count=%d, safe_mode=%s)" %
                  (self.ctx["reset_count"], self.ctx["safe_mode"]))

        except Exception as e:
            print("[system_monitor] init FAIL: %s" % e)
            raise

    def tick(self):
        """
        brief 周期调度：心跳扫描 + 后台线程检查
        note 每 5 秒执行一次全量扫描，非扫描轮次直接返回（<0.5ms）
        """
        if not self.ctx.get("is_init", False):
            return

        now = time.ticks_ms()

        # 宽限期内不做扫描
        if time.ticks_diff(now, self._boot_tick) < self.cfg["grace_ms"]:
            if not self._grace_reported:
                self._grace_reported = True
                print("[system_monitor] 启动宽限期 %d ms" % self.cfg["grace_ms"])
            return

        # 时间片校验：仅每 scan_interval_ms 执行一次
        last_scan = self.ctx["last_scan"]
        if last_scan > 0 and time.ticks_diff(now, last_scan) < self.cfg["scan_interval_ms"]:
            return

        self.ctx["last_scan"] = now

        # 执行全量扫描（带异常保护，单模块损坏不崩溃整个监控）
        try:
            self._scan_modules(now)
        except Exception as e:
            print("[system_monitor] scan error: %s" % e)
        try:
            self._check_threads(now)
        except Exception as e:
            print("[system_monitor] thread check error: %s" % e)

        # 安全模式退出检测
        if self.ctx["safe_mode"]:
            self._check_safe_mode_exit(now)

    # ==================== WDT 门控 ====================

    def should_feed_wdt(self):
        """
        brief 判断是否应该喂狗
        return bool True=喂狗, False=停喂（让硬件 WDT 复位）
        note 由 main.py 在主循环中调用，不在 tick 内部执行

        判定逻辑：
        1. 启动宽限期（前 15s）：无条件 True
        2. 安全模式：任意已初始化的模块有近期心跳 → True
        3. 正常模式：所有 CRITICAL 模块必须存活
        """
        now = time.ticks_ms()

        # 1. 启动宽限期：前 15s 无条件喂狗
        if time.ticks_diff(now, self._boot_tick) < self.cfg["grace_ms"]:
            return True

        # 空 critical 列表安全守卫（无关键模块时宁可复位也不盲目喂狗）
        if not self._critical:
            return False

        # 2. 安全模式：放宽为任意模块存活即可
        if self.ctx["safe_mode"]:
            return self._any_module_alive(now)

        # 3. 正常模式：所有 CRITICAL 模块必须存活
        for mod in self._critical:
            name = mod.name if hasattr(mod, 'name') else "unknown"
            last_hb = mod.ctx.get("last_hb", 0) if hasattr(mod, 'ctx') else 0
            age = time.ticks_diff(now, last_hb)
            if age > self.cfg["critical_timeout_ms"]:
                return False

        return True

    # ==================== 数据 / 状态接口 ====================

    def get_data(self):
        """
        brief 获取监控数据快照
        return dict 包含安全模式状态、复位计数、关键模块存活状态
        """
        return {
            "safe_mode": self.ctx["safe_mode"],
            "reset_count": self.ctx["reset_count"],
            "critical_alive": self.ctx["critical_alive"],
            "any_alive": self.ctx["any_alive"],
        }

    def get_status(self):
        """
        brief 获取详细运行状态（含模块健康摘要）
        return dict 包含所有运行时信息
        """
        now = time.ticks_ms()
        boot_age = time.ticks_diff(now, self._boot_tick) if self._boot_tick > 0 else 0
        in_grace = boot_age < self.cfg["grace_ms"]

        # 统计各级模块数量
        ok_count = 0
        timeout_count = 0
        for h in self.ctx["module_health"].values():
            if h["state"] == "OK":
                ok_count += 1
            else:
                timeout_count += 1

        return {
            "is_init": self.ctx.get("is_init", False),
            "safe_mode": self.ctx["safe_mode"],
            "reset_count": self.ctx["reset_count"],
            "boot_age_ms": boot_age,
            "in_grace_period": in_grace,
            "critical_alive": self.ctx["critical_alive"],
            "any_alive": self.ctx["any_alive"],
            "total_modules": len(self._modules),
            "critical_count": len(self._critical),
            "important_count": len(self._important),
            "auxiliary_count": len(self._auxiliary),
            "threaded_count": len(self._threaded),
            "ok_count": ok_count,
            "timeout_count": timeout_count,
            "module_health": dict(self.ctx["module_health"]),
        }

    # ==================== 模块分级 ====================

    def _classify_modules(self):
        """遍历所有模块实例，按名称分级"""
        self._critical = []
        self._important = []
        self._auxiliary = []
        self._threaded = []

        for mod in self._modules:
            name = mod.name if hasattr(mod, 'name') else "unknown"

            if name in SystemMonitor.CRITICAL_MODULES:
                self._critical.append(mod)
            elif name in SystemMonitor.IMPORTANT_MODULES:
                self._important.append(mod)
            else:
                self._auxiliary.append(mod)

            if name in SystemMonitor.THREADED_MODULES:
                self._threaded.append(mod)

    def _get_tier(self, name):
        """获取模块等级名称"""
        if name in SystemMonitor.CRITICAL_MODULES:
            return "CRITICAL"
        if name in SystemMonitor.IMPORTANT_MODULES:
            return "IMPORTANT"
        return "AUXILIARY"

    def _get_timeout(self, name):
        """获取模块超时阈值 (ms)"""
        if name in SystemMonitor.CRITICAL_MODULES:
            return self.cfg["critical_timeout_ms"]
        if name in SystemMonitor.IMPORTANT_MODULES:
            return self.cfg["important_timeout_ms"]
        return self.cfg["auxiliary_timeout_ms"]

    # ==================== 心跳扫描 ====================

    def _scan_modules(self, now):
        """
        brief 遍历所有模块检查心跳超时
        param now: 当前 ticks_ms

        对每个模块：
        - 读取 ctx["last_hb"]
        - 与超时阈值比较
        - 首次超时 → 发布告警（不重复）
        - 自愈检测 → 发布恢复事件
        """
        any_alive = False
        critical_alive = True

        for mod in self._modules:
            name = mod.name if hasattr(mod, 'name') else "unknown"
            last_hb = mod.ctx.get("last_hb", 0) if hasattr(mod, 'ctx') else 0
            age = time.ticks_diff(now, last_hb)

            timeout = self._get_timeout(name)
            health = self.ctx["module_health"].get(name, {})
            prev_state = health.get("state", "OK")

            if last_hb > 0 and age > timeout:
                # ---- 超时 ----
                health["state"] = "TIMEOUT"
                health["age_ms"] = age
                health["last_hb"] = last_hb

                # 首次超时 → 告警（防重复）
                if prev_state != "TIMEOUT":
                    self._report_timeout(name, self._get_tier(name), age)

            elif last_hb > 0:
                # ---- 正常 ----
                health["state"] = "OK"
                health["age_ms"] = age
                health["last_hb"] = last_hb

                # 自愈检测：之前超时现在恢复
                if prev_state == "TIMEOUT":
                    self._report_recovered(name)

            # 更新全局存活状态
            if last_hb > 0:
                any_alive = True
            if name in SystemMonitor.CRITICAL_MODULES and (last_hb == 0 or age > timeout):
                critical_alive = False

        self.ctx["critical_alive"] = critical_alive
        self.ctx["any_alive"] = any_alive

    def _check_threads(self, now):
        """
        brief 检查后台线程活跃度
        param now: 当前 ticks_ms
        note 后台线程超时仅告警，不尝试重启线程
        """
        for mod in self._threaded:
            name = mod.name if hasattr(mod, 'name') else "unknown"
            last_ok = mod.ctx.get("last_thread_ok", 0) if hasattr(mod, 'ctx') else 0
            age = time.ticks_diff(now, last_ok)

            if last_ok > 0 and age > self.cfg["thread_timeout_ms"]:
                # 防重复告警
                key = "thread:" + name
                last_alert = self._last_thread_alert.get(key, 0)
                if time.ticks_diff(now, last_alert) > self.cfg["thread_timeout_ms"] * 2:
                    self._last_thread_alert[key] = now
                    print("[system_monitor] THREAD_TIMEOUT: %s age=%dms" %
                          (name, age))

    # ==================== 告警发布 ====================

    def _report_timeout(self, name, tier, age_ms):
        """
        brief 发布模块超时事件
        param name: 模块名
        param tier: 等级（CRITICAL/IMPORTANT/AUXILIARY）
        param age_ms: 心跳年龄 (ms)
        """
        print("[system_monitor] TIMEOUT: %s (tier=%s, age=%dms)" %
              (name, tier, age_ms))

        if self.event_bus:
            self.event_bus.publish(EVENT_MODULE_TIMEOUT, {
                "source": self.name,
                "module": name,
                "tier": tier,
                "age_ms": age_ms,
            })

    def _report_recovered(self, name):
        """
        brief 发布模块自愈恢复事件
        param name: 模块名
        """
        print("[system_monitor] RECOVERED: %s" % name)

        if self.event_bus:
            self.event_bus.publish(EVENT_MODULE_RECOVERED, {
                "source": self.name,
                "module": name,
            })

    # ==================== 复位计数持久化 ====================

    def _check_reset_cause(self):
        """检测复位原因：WDT 复位则递增计数，非 WDT 则清零"""
        try:
            from machine import reset_cause, WDT_RESET
            cause = reset_cause()
            if cause == WDT_RESET:
                print("[system_monitor] 上次复位: WDT_RESET")
                self._increment_reset_count()
            else:
                print("[system_monitor] 上次复位: %s (非 WDT，计数清零)" % cause)
                self._clear_reset_count()
        except ImportError:
            # PC 测试环境无 machine 模块
            count = self._load_reset_count_file()
            if count > 0:
                # 无法判断复位原因，保守递增
                self.ctx["reset_count"] = count + 1
                self._save_reset_count_file(count + 1)
                print("[system_monitor] 无 machine 模块，复位计数: %d" %
                      self.ctx["reset_count"])
            else:
                self.ctx["reset_count"] = 0
        except Exception as e:
            print("[system_monitor] reset_cause 检测异常: %s" % e)

    def _increment_reset_count(self):
        """递增复位计数并保存"""
        count = self._load_reset_count_file() + 1
        self.ctx["reset_count"] = count
        self._save_reset_count_file(count)
        print("[system_monitor] 复位计数: %d" % count)

    def _clear_reset_count(self):
        """清零复位计数"""
        self.ctx["reset_count"] = 0
        self._clear_reset_count_file()

    def _save_reset_count_file(self, count):
        """将复位计数写入持久化文件 sysmon_reset.cnt"""
        try:
            with open("sysmon_reset.cnt", "w") as f:
                f.write(str(count))
        except Exception:
            pass

    def _load_reset_count_file(self):
        """从 sysmon_reset.cnt 读取复位计数"""
        try:
            with open("sysmon_reset.cnt", "r") as f:
                return int(f.read().strip())
        except Exception:
            return 0

    def _clear_reset_count_file(self):
        """删除复位计数持久化文件"""
        try:
            import os
            try:
                os.remove("sysmon_reset.cnt")
            except OSError:
                pass
        except Exception:
            pass

    # ==================== 安全模式 ====================

    def _check_safe_mode(self):
        """判断是否应进入安全模式"""
        threshold = self.cfg["safe_mode_threshold"]
        if self.ctx["reset_count"] >= threshold:
            self.ctx["safe_mode"] = True
            print("[system_monitor] 安全模式已激活 (reset_count=%d >= %d)" %
                  (self.ctx["reset_count"], threshold))

    def _check_safe_mode_exit(self, now):
        """
        brief 检查是否退出安全模式
        param now: 当前 ticks_ms
        note 连续正常运行 5 分钟且所有关键模块存活 → 退出安全模式
        """
        boot_age = time.ticks_diff(now, self._boot_tick)
        if boot_age > self.cfg["safe_mode_exit_ms"] and self.ctx["critical_alive"]:
            self.ctx["safe_mode"] = False
            self._clear_reset_count_file()
            print("[system_monitor] 退出安全模式，复位计数已清零")

    def _any_module_alive(self, now):
        """
        brief 安全模式下判断是否有任意模块存活
        param now: 当前 ticks_ms
        return bool 至少一个已初始化的模块有近期心跳
        """
        for mod in self._modules:
            name = mod.name if hasattr(mod, 'name') else "unknown"
            if not hasattr(mod, 'ctx'):
                continue
            is_init = mod.ctx.get("is_init", False)
            last_hb = mod.ctx.get("last_hb", 0)
            age = time.ticks_diff(now, last_hb)
            if is_init and last_hb > 0 and age < self.cfg["critical_timeout_ms"] * 2:
                return True
        return False
