# SystemMonitor — 系统监控服务 (简化版)

> **版本**：v2（简化设计）
> **目标**：轻量心跳扫描 + WDT 门控，不修改模块内部逻辑，不尝试自动恢复
> **核心约束**：非侵入式，单 tick <5ms，不依赖模块 deinit 能力

---

## 1. 概述

SystemMonitor 是一个轻量监控层，运行在 main.py 主循环中。它通过扫描模块的 `ctx["last_hb"]` 心跳标记检测模块失效，并根据失效模块的等级决定是否继续喂 WDT。如果关键模块（碰撞检测、报警、BLE）失联，SystemMonitor 会停止喂狗，让硬件 WDT 在超时后复位整机。SystemMonitor 不做模块恢复——恢复需要更高层级的 LifecycleManager 配合，不属于当前设计范围。它的价值在于提前检测到无声故障（模块静默挂死、后台线程退出），并在关键模块失效时缩短故障响应时间，而不是等用户在几十秒后才发现功能丢失。

---

## 2. 不做什么（明确边界）

- **不修改现有模块的 deinit/recovery 逻辑**。大部分模块没有可靠的 deinit 方法，强行调用可能使系统状态更糟。SystemMonitor 只读心跳标记，不触碰模块内部状态机。
- **不尝试自动恢复模块**。恢复需要感知依赖关系、重建订阅、重置硬件，这是 LifecycleManager 的职责。SystemMonitor 只发现故障，不修复故障。
- **不处理 I2C 总线问题**。AHT20 的 82ms 测量时间是传感器正常工作行为，不需要总线清空或脉冲恢复。之前分析的 I2C 锁死场景在实际测试中未复现，暂不处理。
- **不替代 WDT**。WDT 是系统最后防线：任何导致主循环停滞的问题最终都会触发 WDT 复位。SystemMonitor 是提前预警——在 WDT 复位前通过日志和 BLE 通知告知用户哪个模块出了问题。
- **不修改模块的 `_abandoned` 机制**。现有 `_abandoned` 是模块内部的自保护逻辑，SystemMonitor 不需要干涉。连续 10 次失败后模块自我禁用属于合理降级行为。

---

## 3. 架构

SystemMonitor 不运行独立线程，所有逻辑嵌入主循环的 `tick()` 调用：

```
main.py 主循环
    │
    ▼
for mod in modules:
    mod.tick()              # 模块更新 ctx["last_hb"]
    │
    ▼
sysmon.tick()               # SystemMonitor 监控
    ├── 心跳扫描
    │   └── 遍历模块，检查 ctx["last_hb"] 超时
    │       ├── 首次超时 → 记录告警（不重复）
    │       └── 自愈检测 → 清除告警状态
    ├── 关键模块判定
    │   └── CRITICAL 模块失联 → WDT 门控停喂
    └── 后台线程检查
        └── ctx["last_thread_ok"] 超时 → 告警（不恢复）
    │
    ▼
bus.pump()                  # 事件分发
    │
    ▼
if sysmon.should_feed_wdt():
    wdt.feed()              # WDT 喂狗（集成在主循环）
    │
    ▼
time.sleep_ms(10)
```

**数据流**：模块每轮 tick 写入 `ctx["last_hb"]` → SystemMonitor 每 5 秒扫描一次 → 判定是否超时 → 超时后控制 WDT 喂狗条件和事件告警。全部是单向只读，不修改模块状态。

---

## 4. 模块分级

所有 23 个模块按功能重要性分为三级，仅用于监控告警和 WDT 门控判断，不涉及恢复策略。

### CRITICAL（失联时停喂 WDT）

| 模块 | 文件名 | 分级理由 |
|------|--------|----------|
| CollisionService | `Modules/collision_service.py` | 碰撞检测——骑行者安全核心 |
| AlarmService | `Modules/alarm_service.py` | 报警流程——生命攸关 |
| BLEService | `Modules/ble_service.py` | BLE 通信——唯一用户交互通道 |

这三个模块任何一个失效，系统已经失去了核心安全功能，继续运行没有意义。WDT 复位让系统重新启动，有可能恢复。

### IMPORTANT（失联时告警）

| 模块 | 文件名 | 备注 |
|------|--------|------|
| TempHumidDriver | `Drivers/sensor/Temp_Humid.py` | 温湿度，数据驱动显示 |
| IMUDriver | `Drivers/sensor/imu.py` | 加速度数据，碰撞检测输入 |
| GNSSDriver | `Drivers/sensor/Gnss.py` | 定位，有后台线程 |
| HeartRateDriver | `Drivers/sensor/HeartRate.py` | 心率血氧，健康监测 |
| BLEDriver | `Drivers/network/BLE.py` | BLE 硬件驱动 |
| AudioDriver | `Drivers/actuator/Audio.py` | 音频输出驱动 |
| DisplayService | `Modules/display_service.py` | 显示服务 |

这些模块失效会丢失部分功能，但系统可以降级运行（例如 IMU 失效则碰撞检测降级，显示失效则头盔仍需工作）。

### AUXILIARY（失联时仅记录）

| 模块 | 文件名 | 备注 |
|------|--------|------|
| LightSensorDriver | `Drivers/sensor/Light.py` | 光照强度，非安全 |
| BatteryDriver | `Drivers/sensor/Battery.py` | 电量检测 |
| Button | `Drivers/interface/Button.py` | 按键输入 |
| VoiceDriver | `Drivers/interface/Voice.py` | 语音识别 |
| LEDDriver | `Drivers/actuator/LED.py` | 状态指示灯 |
| LCDDriver | `Drivers/actuator/LCD.py` | 液晶屏显示 |
| PWMLEDDriver | `Drivers/actuator/PWM_LED.py` | 大功率照明灯 |
| SMSDriver | `Drivers/network/SMS.py` | 短信发送 |
| LightService | `Modules/light_service.py` | 自适应灯光 |
| ControlService | `Modules/control_service.py` | 统一控制中心 |
| NavigationService | `Modules/navigation_service.py` | 导航服务 |
| PowerService | `Modules/power_service.py` | 电源管理 |

这些模块失效影响小，系统完全不受影响，仅记录日志供调试使用。

---

## 5. 心跳机制

### 5.1 模块侧改动（唯一侵入点）

每个模块的 `tick()` 方法首行增加：

```python
def tick(self):
    self.ctx["last_hb"] = time.ticks_ms()   # ← 新增
    # ... 原有逻辑 ...
```

有后台线程的模块（GNSSDriver、AudioService、BLEService、SMSDriver）额外增加：

```python
def _background_loop(self):
    while self._running:
        self.ctx["last_thread_ok"] = time.ticks_ms()  # ← 新增
        # ... 原有循环逻辑 ...
```

23 个模块各加一行，总改动 23 行。这是 SystemMonitor 唯一的模块侵入。

### 5.2 扫描参数

| 参数 | 值 | 说明 |
|------|----|------|
| `scan_interval_ms` | 5000 | 每隔 5s 执行一次全量扫描 |
| `timeout_critical_ms` | 30000 | CRITICAL 模块 30s 无心跳→停喂 WDT |
| `timeout_important_ms` | 15000 | IMPORTANT 模块 15s 无心跳→告警 |
| `timeout_auxiliary_ms` | 60000 | AUXILIARY 模块 60s 无心跳→仅记录 |
| `thread_timeout_ms` | 15000 | 后台线程 15s 无标记→告警 |

### 5.3 超时判定逻辑

```python
def _check_heartbeat(self, mod):
    now = time.ticks_ms()
    age = time.ticks_diff(now, mod.ctx.get("last_hb", 0))
    tier = self._tiers[mod.name]
    threshold = self._timeouts[tier]

    if age > threshold:
        if mod.ctx.get("_hb_state") != "TIMEOUT":
            mod.ctx["_hb_state"] = "TIMEOUT"
            self._publish_timeout(mod, tier, age)
    else:
        if mod.ctx.get("_hb_state") == "TIMEOUT":
            mod.ctx["_hb_state"] = "OK"
            self._publish_recovered(mod)  # 自愈恢复事件
```

**要点**：
- 首次超时才发布告警事件，后续扫描不再重复告警（避免事件风暴）
- 模块恢复后自动检测并发布恢复事件（自愈检测）
- 不触发任何恢复动作，只做告警

### 5.4 后台线程检查

```python
def _check_threads(self):
    now = time.ticks_ms()
    for mod in self._threaded_modules:
        last = mod.ctx.get("last_thread_ok", 0)
        age = time.ticks_diff(now, last)
        if age > self._thread_timeout_ms:
            self._log("THREAD_TIMEOUT", mod.name, f"age={age}ms")
```

后台线程超时仅告警，不尝试重启线程。重启线程需要模块级别的 deinit/init 重建，当前大部分模块不支持。

---

## 6. WDT 门控

### 6.1 初始化

SystemMonitor 不直接初始化 WDT。WDT 由 `main.py` 在启动宽限期后创建，SystemMonitor 通过 `should_feed_wdt()` 返回决策结果。这样保持 WDT 所有权在 main.py，SystemMonitor 只做判断。

```python
# main.py 中
from machine import WDT

# 启动宽限期内先创建 WDT 但一直喂狗
wdt = WDT(timeout=8000)   # 8 秒硬件超时
```

### 6.2 喂狗判定

```python
def should_feed_wdt(self):
    """返回 True 表示喂狗，False 表示停喂"""
    now = time.ticks_ms()

    # 1. 启动宽限期：前 15s 无条件喂狗
    if time.ticks_diff(now, self._boot_tick) < self._boot_grace_ms:
        return True

    # 2. 安全模式：放宽为任意模块存活即可
    if self._safe_mode:
        for mod in self._modules:
            age = time.ticks_diff(now, mod.ctx.get("last_hb", 0))
            if age < self._timeouts["CRITICAL"] * 2:
                return True
        return False

    # 3. 正常模式：所有 CRITICAL 模块必须存活
    for mod_name in self._critical_list:
        mod = self._module_map[mod_name]
        age = time.ticks_diff(now, mod.ctx.get("last_hb", 0))
        if age > self._timeouts["CRITICAL"]:
            return False

    return True
```

### 6.3 主循环集成（WDT 在 main.py）

```python
# 主循环 — WDT 喂狗在 sysmon.tick() 之后显式执行
while True:
    for mod in modules:
        if mod.ctx.get("is_init", False):
            mod.tick()        # 模块更新 last_hb

    sysmon.tick()             # SystemMonitor 心跳扫描 + 门控判定

    bus.pump()                # 事件分发

    if sysmon.should_feed_wdt():
        wdt.feed()            # WDT 喂狗

    time.sleep_ms(10)
```

**为什么 WDT 放在主循环而非 SystemMonitor.tick() 内部**？因为 WDT 的创建和所有权应当属于 main.py——系统启动流程的主控者。SystemMonitor 只做决策（should_feed_wdt 返回 bool），main.py 执行喂狗动作。职责分离更清晰。

### 6.4 WDT 超时选择

WDT 超时设定为 8000ms（8 秒）。这个值的选择基于：

- **大于最长单次阻塞操作**：EC200U AT 命令最长超时约 5000ms，8 秒有足够余量
- **小于用户可感知等待**：8 秒复位对用户来说是可接受的等待时间
- **留有余地应对 GC**：MicroPython 的 GC 可能暂停数十毫秒，8 秒覆盖最坏情况

---

## 7. 启动宽限期

系统启动后前 15 秒为宽限期。在此期间：

- 心跳扫描不执行（模块尚未全部完成初始化）
- `should_feed_wdt()` 始终返回 True
- 模块的 `last_hb` 可能尚未写入，跳过判定避免误报

宽限期结束后，SystemMonitor 开始正常心跳扫描。

**实现方式**：SystemMonitor 初始化时记录 `self._boot_tick = time.ticks_ms()`，在 `should_feed_wdt()` 中判断 `ticks_diff(now, self._boot_tick) < 15000`。

---

## 8. 安全模式

### 8.1 触发条件

系统连续 3 次 WDT 复位后进入安全模式。复位次数记录在持久化文件 `sysmon_reset.cnt` 中。

```python
def _check_safe_mode(self):
    if not hasattr(self, "_reset_count"):
        self._reset_count = self._load_reset_count()
    if self._reset_count >= 3:
        self._safe_mode = True
        self._log("SAFE_MODE_ENTER", "3 consecutive resets detected")
```

### 8.2 行为变化

| 特征 | 正常模式 | 安全模式 |
|------|----------|----------|
| WDT 喂狗条件 | 所有 CRITICAL 模块存活 | 任意模块存活即可 |
| 心跳扫描 | 全量扫描 + 告警 | 仅扫描，不触发告警事件 |
| 恢复策略 | 无恢复（仅检测） | 无恢复（仅检测） |

安全模式的核心思想：系统已经反复重启，说明存在系统性故障。此时降低检测门槛，只要还有任何一个模块在工作，就维持系统运行，等待远程诊断或用户干预。

### 8.3 复位计数持久化

```python
def _save_reset_count(self, count):
    try:
        with open("sysmon_reset.cnt", "w") as f:
            f.write(str(count))
    except:
        pass

def _load_reset_count(self):
    try:
        with open("sysmon_reset.cnt", "r") as f:
            return int(f.read().strip())
    except:
        return 0

def _clear_reset_count(self):
    try:
        import os
        os.remove("sysmon_reset.cnt")
    except:
        pass
```

### 8.4 退出安全模式

- 连续正常运行 5 分钟后退出安全模式
- 复位计数清零（删除持久化文件）
- 通过 BLE 推送状态通知

---

## 9. 配置常量（config.py 新增）

在 `02_Software/core/config.py` 末尾添加：

```python
# ================= SystemMonitor / WDT 配置 =================
SYSMON_SCAN_INTERVAL_MS      = 5000     # 心跳扫描间隔 (ms)
SYSMON_GRACE_MS              = 15000    # 启动宽限期 (ms)
SYSMON_CRITICAL_TIMEOUT_MS   = 30000    # CRITICAL 模块超时 (ms)
SYSMON_IMPORTANT_TIMEOUT_MS  = 15000    # IMPORTANT 模块超时 (ms)
SYSMON_AUXILIARY_TIMEOUT_MS  = 60000    # AUXILIARY 模块超时 (ms)
SYSMON_THREAD_TIMEOUT_MS     = 15000    # 后台线程超时 (ms)
SYSMON_SAFE_MODE_THRESHOLD   = 3        # 连续复位次数触发安全模式
WDT_TIMEOUT_MS               = 8000     # 硬件看门狗超时 (ms)
```

---

## 10. 改动量

| 文件 | 内容 | 行数 |
|------|------|:---:|
| `02_Software/Modules/system_monitor.py` | 新文件：SystemMonitor 主类 | +120 |
| `02_Software/core/config.py` | 新增 SYSMON_* + WDT_TIMEOUT_MS | +8 |
| `02_Software/core/main.py` | 集成 SystemMonitor + WDT 喂狗 | +15 |
| 23 个模块各加一行 `last_hb` | 每个模块 tick() 首行 | +23 |

**总计**：1 个新文件，~166 行新增代码。无现有文件修改（main.py 和 config.py 的增量添加不影响原有逻辑）。

### 内存占用估算

| 项目 | 占用 |
|------|------|
| SystemMonitor 实例 | ~1.2 KB（模块引用列表、分级映射、定时器状态） |
| 每个模块心跳字段 | ~30 B × 23 ≈ 690 B |
| 复位计数文件 | ~10 B |
| **总计** | **~2 KB** |

---

## 11. 测试计划

### 11.1 test_system_monitor.py

测试文件位于 `02_Software/Tests/test_system_monitor.py`（PC 端语法检查 + 硬件运行）。

**Phase 1：心跳扫描**

| 测试 | 验证内容 |
|------|----------|
| 正常心跳 | 模块 last_hb 小于阈值 → hb_state=OK，无告警 |
| 单模块超时 | 冻结模块心跳 → 检测到 TIMEOUT，发布 EVENT_MODULE_TIMEOUT |
| 自愈检测 | 超时后恢复心跳 → hb_state 从 TIMEOUT 回到 OK |
| 不重复告警 | 持续超时 → 只发布一次告警 |

**Phase 2：WDT 门控**

| 测试 | 验证内容 |
|------|----------|
| 全部正常 | should_feed_wdt() 返回 True |
| CRITICAL 失联 | CollisionService 超时 → should_feed_wdt() 返回 False |
| IMPORTANT 失联 | TempHumid 超时 → should_feed_wdt() 返回 True（不影响 WDT） |
| 安全模式 | safe_mode=True 且任一模块存活 → should_feed_wdt() 返回 True |

**Phase 3：启动宽限期**

| 测试 | 验证内容 |
|------|----------|
| 宽限期内 | should_feed_wdt() 始终返回 True |
| 宽限期后 | 正常判定逻辑生效 |

**Phase 4：安全模式**

| 测试 | 验证内容 |
|------|----------|
| 复位计数加载 | `sysmon_reset.cnt` 内容为 3 → safe_mode=True |
| 计数清零 | 正常退出安全模式后文件被删除 |

### 11.2 硬件集成测试

| 测试 | 前置条件 | 验证 |
|------|----------|------|
| CRITICAL 模块停心跳 | 在 REPL 中手动设置 `ble_svc.ctx["last_hb"] = 0` | 30s 后 WDT 复位整机 |
| 启动后立即测试 | 上电后 15s 内检查 WDT | 宽限期内不触发复位 |
| 安全模式模拟 | 连续写 3 次 `sysmon_reset.cnt` 后重启 | 进入安全模式，模块失联不复位 |

### 11.3 已有 WDT 测试

`02_Software/Tests/test_wdt_hardware.py` 已存在，验证 WDT 超时后硬件能复位。SystemMonitor 的 WDT 门控逻辑与该测试互补——硬件测试验证 WDT 本身，SystemMonitor 验证喂狗条件。

---

## 附录 A：SystemMonitor 类接口原型

```python
class SystemMonitor:
    """系统监控服务——心跳扫描 + WDT 门控"""

    def __init__(self, modules, event_bus, critical_list=[],
                 boot_grace_ms=15000):
        """
        param modules: list of all module instances (23 modules)
        param event_bus: EventBus instance
        param critical_list: list of CRITICAL module names
        param boot_grace_ms: 启动宽限期
        """

    def init(self):
        """初始化：记录启动时间、模块分级、加载复位计数、检测安全模式"""

    def tick(self):
        """心跳扫描 + 后台线程检查（<2ms，非扫描轮次 <0.5ms）"""

    def get_status(self):
        """返回监控状态 dict"""

    def should_feed_wdt(self):
        """判断是否应该喂狗——供 main.py 调用"""

    def _scan_modules(self):
        """遍历所有模块检查心跳超时（每 5s 执行）"""

    def _check_threads(self):
        """检查后台线程活跃度"""

    def _publish_timeout(self, mod, tier, age):
        """发布模块超时事件"""

    def _publish_recovered(self, mod):
        """发布模块自愈事件"""

    def _check_safe_mode(self):
        """检测是否需要进入安全模式"""
```

---

## 附录 B：与现有设计的一致性检查

| 现有规则 | SystemMonitor 遵守情况 |
|----------|----------------------|
| tick() < 5ms | √ 心跳扫描 5s 一次（非每轮），非扫描轮次直接返回 <0.5ms |
| 禁止 time.sleep() | √ 使用 ticks_diff 守卫，无阻塞等待 |
| 禁止跨层调用 | √ SystemMonitor 在 App 层，只读心跳标记 |
| 禁止模块间直接调用 | √ 通过 EventBus 发布告警事件 |
| 状态封装在 ctx | √ 心跳标记在 `ctx["last_hb"]`，完全沿用现有 Pattern |
| 初始化有序 | √ 最后初始化，不依赖其他模块的状态 |
| 非侵入式 | √ 唯一改动：各模块 tick() 首行加 `self.ctx["last_hb"] = time.ticks_ms()` |

---

## 附录 C：与 v1 设计的关键差异

| 特性 | v1（原始草案） | v2（简化版） |
|------|---------------|-------------|
| 分步恢复状态机 | PAUSE→DEINIT→INIT→RESUME | 移除（模块缺乏 deinit） |
| I2C 总线恢复 | 9 脉冲时钟清空 | 移除（AHT20 82ms 正常行为） |
| _abandoned 修改 | 替换为 need_recovery | 移除（不干涉模块自保护） |
| 后台线程重启 | deinit+init 重建线程 | 仅告警，不重启 |
| WDT 所有权 | SystemMonitor 内部 | main.py 显式调用 |
| WDT 超时 | 60s | 8s（更快速复位） |
| CRITICAL 模块 | 5 个（含 AudioService、GNSS） | 3 个（仅核心安全模块） |
| 代码量 | ~220 行 | ~120 行 |
