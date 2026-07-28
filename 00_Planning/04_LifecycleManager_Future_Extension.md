# 生命周期管理器 — 未来扩展设计文档

> **本文档目的**：为赛后重构提供完整的 LifecycleManager 设计方案。当前比赛阶段使用硬编码 init_order 列表，本设计不要求立即实现。
>
> **文档状态**：设计参考 v0.1 — 非实现计划
>
> **预期收益**：模块自动发现、依赖排序、引用计数挂起、统一电源协调、故障恢复

---

## 1. 设计动机

### 1.1 当前架构的问题

当前系统初始化采用 `main.py` 中的硬编码列表：

```python
init_order = [temp_humid, imu, gnss, light, battery_drv, heart_rate,
              button, led, audio, lcd, pwm_led, ble, sms,
              collision, audio_svc, alarm, display, control_svc, power_svc,
              light_svc, ble_svc, nav_svc, voice]
```

该方案在 23 个模块时勉强可用，但存在以下问题：

| 问题 | 具体表现 | 后果 |
|------|---------|------|
| **模块发现靠手动** | 新增模块需在 `main.py` 中手动 import + 实例化 + 加入 init_order | 遗漏风险，忘记加模块直接不可用 |
| **依赖关系隐式** | 初始化顺序靠注释约定，无编译期/运行期校验 | HeartRate 必须在 quectel 模块之后这种约束靠人工记忆 |
| **状态跟踪分散** | 每个模块自己维护 `ctx["is_init"]`，无法全局查询 | 故障时难定位是哪个模块卡住 |
| **无停用通道** | 模块要么全初始化和运行，要么全关 | 想单独禁用 Voice 必须改代码 |
| **无状态保持** | 模块只有 init/tick 两种状态 | 无法按需激活、挂起、恢复 |
| **电源协调混乱** | PowerService 发布 `EVENT_POWER_STATE_CHANGE` 事件，各模块各自响应 | 同步时序难保证，不能统一管理谁该挂起谁不该 |
| **故障恢复缺失** | 初始化失败仅跳过打印，无重试机制 | 偶发硬件失败需要手动复位整机 |
| **无引用计数** | 多个 Service 依赖同一个 Driver，但 Driver 不知道自己是否被引用 | 无法判断何时可以安全挂起共享总线 |

### 1.2 LifecycleManager 要解决的问题

1. **模块注册中心**：所有模块通过 `register()` 统一声明，自动管理生命周期
2. **依赖排序**：通过 `depends_on` 字段自动计算拓扑序，消除隐式顺序约定
3. **状态机管理**：每个模块经历 UNREGISTERED → IDLE → ACTIVE → SUSPENDING → SUSPENDED → ERROR 状态
4. **引用计数激活**：get/put 模式，模块在引用计数归零后自动挂起
5. **自动挂起策略**：非关键模块按空闲超时自动进入低功耗
6. **电源协同**：`set_power_mode()` 统一协调所有模块的电源模式切换
7. **故障隔离与恢复**：模块出错后可独立重启，不牵连系统

### 1.3 行业参考

- **Zephyr Device Runtime Power Management**：设备驱动注册到子系统，支持 `pm_device_runtime_get/put` 引用计数，自动管理设备挂起和恢复。每个设备可配置是否支持运行时 PM，系统在引用归零后自动挂起。
- **Linux Runtime PM (pm_runtime_get/put)**：设备模型的核心机制。驱动通过 `pm_runtime_get_sync()` 唤醒设备，`pm_runtime_put()` 释放引用，PM 核心在引用归零且有足够空闲时间后执行 `suspend` 回调。
- **Hubble Network Power State Machine**：嵌入式无线设备的 5 状态电源模型（OFF → SLEEP → IDLE → ACTIVE → TX），与模块生命周期状态机类似，通过引用计数管理共享外设。
- **Peter Hinch micropower library**：MicroPython 低功耗管理库，提供调度器和设备抽象，支持 tick-less 休眠、定时唤醒、外设电源管理。适合低功耗物联网应用。
- **MicroPython PR #18424（multi-level init/deinit）**：社区提案的模块化 init/deinit 框架，标准化 MicroPython 固件的模块初始化层级和停用流程。尚在讨论阶段，但反映了未来方向。

---

## 2. 核心概念

### 2.1 模块状态

每个模块在生命周期管理器中处于以下状态之一：

| 状态 | 含义 | 说明 |
|------|------|------|
| `UNREGISTERED` | 未注册 | 模块尚未被 LifecycleManager 知晓 |
| `IDLE` | 空闲 | 模块已注册，依赖满足，但未激活（硬件未初始化） |
| `ACTIVE` | 运行中 | 模块已初始化，tick() 正常调度 |
| `SUSPENDING` | 挂起中 | 正在执行挂起回调，等待关联模块释放（过渡态） |
| `SUSPENDED` | 已挂起 | 模块已释放硬件资源，tick() 跳过 |
| `ERROR` | 错误 | 模块初始化或运行时出现不可恢复错误 |

### 2.2 核心机制

#### 引用计数（get/put 模式）

引用计数是 LifecycleManager 的核心协调机制：

- `get(name)`：请求激活模块。计数从 0 → 1 时触发实际激活（硬件 init）。每次调用计数 +1。
- `put(name)`：释放模块引用。计数从 1 → 0 时触发实际挂起（硬件 deinit/suspend）。每次调用计数 -1。

典型场景：

```
BLEService.get("gnss")     → GNSS 引用计数: 0→1, 激活 GNSS
NavigationService.get("gnss") → GNSS 引用计数: 1→2, 沿用已有激活
BLEService.put("gnss")     → GNSS 引用计数: 2→1, 保持激活
NavigationService.put("gnss") → GNSS 引用计数: 1→0, 触发挂起
```

**关键规则**：
- `get()` 调用次数必须与 `put()` 匹配，不能多也不能少
- 嵌套 `get` 安全：同一模块多次 get 只激活一次硬件，引用计数递增
- 强行 `suspend(name)` 需等待引用归零，或抛出异常阻止

#### 自动挂起（Auto-suspend with Hysteresis）

非关键模块可在注册时指定 `idle_timeout_ms`。当引用计数为 0 且持续空闲超过超时值时，LifecycleManager 自动发起挂起。

带有滞后机制（hysteresis）防止频繁状态翻转：
- 挂起后，至少等待 `min_idle_ms` 才允许重新激活
- 距离上次 tick 超过 `idle_timeout_ms` 才判定为空闲
- 避免 GNSS 因短暂信号丢失被挂起后又立即唤醒

#### 依赖感知（Dependency Awareness）

模块间通过 `depends_on` 声明依赖。LifecycleManager 在挂起一个模块前，先检查 `depends_on` 链上的引用：

- **共享总线场景**：I2C1 总线是 TempHumid 和 IMU 的共同依赖。只有当两个传感器都释放 I2C1，且 I2C1 的引用计数为 0 时，总线才能挂起。
- **AT 通道场景**：UART AT 通道被 GNSS、SMS 共用，必须所有子设备释放后才能关闭 AT 通道。
- **依赖排序**：初始化时按拓扑序排列，保证父依赖先初始化。

#### 上下文保存/恢复（Save/Restore Context）

可挂起模块应实现两个可选回调：

| 回调 | 调用时机 | 用途 |
|------|---------|------|
| `save_context()` | 挂起前 | 保存寄存器状态、最后有效数据、配置 |
| `restore_context()` | 恢复前 | 恢复保存的上下文，避免重新校准 |

对于 I2C 传感器（如 AHT20），恢复时不需要重新校准，调用 `init()` 即可。但对于需要校准的模块（如 IMU 偏移补偿），保存/恢复上下文可以跳过校准过程，加速恢复。

---

## 3. 接口设计

### 3.1 LifecycleManager 类

```python
class LifecycleManager:
    """
    brief 生命周期管理器
    note 模块注册、状态追踪、依赖排序、引用计数挂起、电源协调
    """

    def register(self, module, name, can_suspend=True,
                 idle_timeout_ms=0, depends_on=None, needed_by=None):
        """
        brief 注册模块到管理器
        param module: 模块实例（继承 BaseModule）
        param name: 模块名称（唯一标识符，用于 get/put 引用）
        param can_suspend: 是否允许自动挂起
        param idle_timeout_ms: 空闲超时（0 表示不自动挂起）
        param depends_on: 依赖的模块名称列表
        param needed_by: 被哪些模块依赖（自动计算，可不填）
        """
        pass

    def init_all(self):
        """
        brief 按依赖拓扑序初始化所有模块
        note 先计算拓扑排序，再逐模块 init()
        返回: (success: int, failed: [(name, error)])
        """
        pass

    def tick_all(self):
        """
        brief 遍历所有 ACTIVE 模块执行 tick()
        note 跳过 SUSPENDED / ERROR 状态模块
        """
        pass

    def activate(self, name):
        """
        brief 强制激活模块（不管引用计数）
        param name: 模块名称
        返回: True/False
        """
        pass

    def suspend(self, name, force=False):
        """
        brief 挂起模块（释放硬件资源）
        param name: 模块名称
        param force: 强制挂起（忽略引用计数，不推荐）
        返回: True/False
        note 非 force 模式下，模块引用计数 > 0 时挂起失败
        """
        pass

    def get(self, name):
        """
        brief 获取模块引用（引用计数 +1）
        param name: 模块名称
        note 若模块处于 SUSPENDED 状态，自动触发 restore/resume
        返回: True/False
        """
        pass

    def put(self, name):
        """
        brief 释放模块引用（引用计数 -1）
        param name: 模块名称
        note 引用归零时，若 idle_timeout_ms > 0，启动超时定时器
        返回: True/False
        """
        pass

    def get_state(self, name):
        """
        brief 获取指定模块状态
        param name: 模块名称
        返回: state (str), ref_count (int), last_tick (int)
        """
        pass

    def health_report(self):
        """
        brief 生成所有模块的健康报告
        返回: dict {name: {state, ref_count, err_count, last_tick, uptime_ms}}
        """
        pass

    def restart(self, name):
        """
        brief 重启指定模块（deinit → init）
        param name: 模块名称
        返回: True/False
        note 适合故障恢复场景，模块进入 ERROR 状态后调用
        """
        pass

    def set_power_mode(self, mode):
        """
        brief 统一设置电源模式
        param mode: POWER_STATE_ACTIVE / SUSPENDED / EMERGENCY / CUSTOM
        note 自动决定各模块应该挂起还是继续运行，
             覆盖模块自身的 idle_timeout 策略
        """
        pass

    def get_dependency_graph(self):
        """
        brief 返回当前依赖图（用于调试和文档生成）
        返回: {name: [depends_on], name: [needed_by]}
        """
        pass
```

### 3.2 BaseModule 扩展接口

需要在 BaseModule 中添加以下可选接口（全部提供空默认实现，向后兼容）：

```python
class BaseModule:
    # ... 现有接口 ...

    def deinit(self):
        """
        brief 反初始化，释放硬件资源
        note 被 LifecycleManager.suspend() 调用
             空默认实现，可挂起模块应重写此方法
        """
        pass

    def save_context(self):
        """
        brief 保存运行上下文（挂起前调用）
        note 可选实现，用于保存需恢复的寄存器/校准数据
        """
        pass

    def restore_context(self):
        """
        brief 恢复运行上下文（恢复后调用）
        note 可选实现，配合 save_context 使用
        """
        pass

    def on_suspend(self):
        """
        brief 挂起通知回调
        note 模块被挂起前调用，用于发送"即将离线"通知
        """
        pass

    def on_resume(self):
        """
        brief 恢复通知回调
        note 模块被恢复后调用，用于发送"已重新上线"通知
        """
        pass
```

### 3.3 内部数据结构

每个注册模块维护以下元数据：

```python
class _ModuleEntry:
    def __init__(self, module, name, can_suspend, idle_timeout_ms,
                 depends_on, needed_by):
        self.module = module          # 模块实例
        self.name = name              # 模块名称（唯一）
        self.can_suspend = can_suspend
        self.idle_timeout_ms = idle_timeout_ms
        self.depends_on = depends_on  # [str] 依赖列表
        self.needed_by = needed_by    # [str] 被依赖列表
        self.state = "UNREGISTERED"   # 当前状态
        self.ref_count = 0            # 引用计数
        self.last_tick = 0            # 上次 tick 时间戳
        self.last_active = 0          # 上次被使用的时间戳
        self.error_count = 0          # 错误计数
        self.init_time = 0            # 初始化耗时（用于性能分析）
```

---

## 4. 模块状态机

```
                           ┌──────────────────────────────┐
                           │         UNREGISTERED          │
                           └──────────┬───────────────────┘
                                      │ register()
                                      ▼
                           ┌──────────────────────────────┐
                      ┌───│            IDLE               │
                      │   │   (已注册, 硬件未初始化)       │
                      │   └──────────┬───────────────────┘
                      │              │ activate() / get()
                      │              ▼
                      │   ┌──────────────────────────────┐
                      │   │          ACTIVE               │
                      │   │  (硬件已 init, tick 正常调度) │
                      │   └──────┬───────────┬───────────┘
                      │          │           │
                      │          │           │ ref_count=0
                      │          │           │ 且 idle_timeout 到
                      │          │           ▼
                      │          │   ┌──────────────────────────────┐
                      │          │   │         SUSPENDING            │
                      │          │   │  (等待 save_context 完成)    │
                      │          │   └──────────┬───────────────────┘
                      │          │              │ deinit() 成功
                      │          │              ▼
                      │          │   ┌──────────────────────────────┐
                      │          │   │         SUSPENDED             │
                      │          │   │  (硬件 deinit, tick 跳过)    │
                      │          │   └──────────┬───────────────────┘
                      │          │              │ get() / activate()
                      │          └──────────────┘
                      │              restore_context() + init()
                      │
                      │   ┌──────────────────────────────┐
                      │   │           ERROR               │
                      │   │  (init/deinit 失败, 错误累计) │
                      │   └──────────┬───────────────────┘
                      │              │ restart()
                      └──────────────┘
                           (进入 IDLE 重新 init)
```

### 状态转换条件详细说明

| 当前状态 | 目标状态 | 触发条件 | 动作 |
|---------|---------|---------|------|
| UNREGISTERED | IDLE | `register()` | 注册模块信息，检查依赖是否存在 |
| IDLE | ACTIVE | `activate()` / `get()` | 调用 `module.init()`；不满足依赖时阻塞等待 |
| ACTIVE | ACTIVE | — | `tick()` 正常调度 |
| ACTIVE | SUSPENDING | `ref_count==0` 且 `idle_timeout` 到 | `on_suspend()` → `save_context()` |
| SUSPENDING | SUSPENDED | `deinit()` 成功 | 释放硬件资源，标记状态 |
| SUSPENDING | ACTIVE | `get()` 在挂起完成前到达 | 取消挂起，状态回退 |
| SUSPENDED | ACTIVE | `get()` / `activate()` | `init()` → `restore_context()` → `on_resume()` |
| ACTIVE | ERROR | `tick()` 连续失败超过阈值 | 捕获异常，累计 err_count |
| SUSPENDING | ERROR | `deinit()` 失败 | 捕获异常，置 ERROR |
| ERROR | IDLE | `restart()` | 重置错误计数，准备重新 init |

---

## 5. 自动挂起策略

### 5.1 可挂起模块表

| 模块 | 可挂起 | 空闲超时 | 恢复延迟 | 省电预估 | 策略说明 |
|------|--------|---------|---------|---------|---------|
| GNSS | ✅ 是 | 5 min IDLE | ~3-5s 搜星 | ~30 mA | 夜间停车/静止时挂起，恢复需重新搜星 |
| GNSS 后台线程 | ✅ 是 | 跟随 GNSS | — | ~5 mA | 线程随 GNSS 一并停掉 |
| Voice | ✅ 是 | 2 min 无语音 | ~50 ms | ~5 mA | 语音交互频次低，空闲挂起不影响体验 |
| HeartRate | ✅ 是 | 10 min 无有效数据 | ~2 s | ~3 mA | 无人佩戴或无有效信号时挂起 |
| Temp_Humid | ✅ 是 | 30 min 静止态 | ~100 ms | ~0.3 mA | 静止时降频即可，不一定要挂起 |
| LightSensor | ✅ 是 | 手动模式 30s | ~1 ms | ~0.1 mA | 手动灯光模式下可大幅降低采样 |
| LCD | ✅ 是 | 屏幕关闭 5 min | ~200 ms | ~50 mA | 大片背光功耗，挂起收益高 |
| Button | ❌ 否 | — | — | — | SOS 按键必须随时响应 |
| BLE | ❌ 否 | — | — | — | 保持广播/连接，手机控制入口 |
| Audio | ❌ 否 | — | — | — | 报警/TTS 随时可能触发 |
| CollisionService | ❌ 否 | — | — | — | 碰撞检测必须常驻 |
| AlarmService | ❌ 否 | — | — | — | 报警联动必须常驻 |
| PWM_LED | ❌ 否 | — | — | — | 用户开关灯/自动模式需要即时响应 |
| SMS | ✅ 是 | 跟随 AT 通道 | ~1.5 s | ~2 mA | AT 通道挂起时一并挂起 |
| DisplayService | ✅ 是 | LCD 挂起跟随 | ~200 ms | — | 跟随 LCD 硬件状态 |

### 5.2 共享总线挂起策略

某些硬件资源被多个模块共享，必须所有使用者释放后才能挂起：

| 共享资源 | 使用者 | 挂起条件 | 说明 |
|---------|-------|---------|------|
| I2C1 总线 | Temp_Humid, IMU | 两者引用均为 0 | 创建虚拟 `i2c_bus` 模块，Temp_Humid 和 IMU 注册为 `depends_on=["i2c_bus"]` |
| AT 通道（EC200U） | GNSS, SMS | 两者引用均为 0 | AT 通道挂起时关闭串口，挂起前需等待当前 AT 命令完成 |
| SPI1 总线 | LCD | LCD 释放 | LCD 是唯一受控用户，挂起时机由 LCD 状态决定 |
| BLE 协议栈 | BLE, BLEService | BLE 不能挂起 | 例外：BLE 为常驻模块 |
| EC200U 电源域 | BLE, Audio, SMS, GNSS | 全部释放 | 整体 EC200U 休眠需在所有子模块挂起后触发（功耗收益 ~50 mA） |

### 5.3 EC200U 整体休眠策略

EC200U 整机休眠是最具省电收益的场景（~200 mA → ~5 mA），但协调复杂：

```python
# 虚拟协调模块（不出现在模块列表中，仅做计数）
ec200u_power_domain = {
    "children": ["ble", "audio", "sms", "gnss"],
    "state": "ACTIVE",
    "defer_count": 0,  # 暂缓休眠计数（有 AT 命令进行中时递增）
}

ec200u_power_domain_suspend_conditions:
    - 所有子模块状态 == SUSPENDED
    - defer_count == 0
    - 无 pending AT 命令
    - 无音频正在播放

ec200u_power_domain_resume_triggers:
    - BLE 有连接保持 → 不触发整机休眠
    - Audio 正在播放 → 不触发整机休眠
    - 任一子模块 get() → 唤醒 EC200U 整机
```

**注意**：EC200U 整机休眠需要在 Quectel 固件层面支持 `quectel.power_save()` API。在验证该 API 可用前，建议优先实现模块级挂起（通过调整采样间隔等效省电），而不是整机休眠。

---

## 6. 与现有架构的差异

### 6.1 对比表

| 维度 | 当前架构 (init_order 硬编码) | LifecycleManager |
|------|---------------------------|-----------------|
| **模块发现** | 手动 import + 手动实例化 + 手动加入列表 | 通过 `register()` 统一注册，可选自动扫描 |
| **状态跟踪** | 分散在各模块的 `ctx["is_init"]` | 集中管理每个模块的 state、ref_count、last_tick |
| **初始化顺序** | 手动排序，靠注释约定 | 依赖拓扑自动排序，`depends_on` 声明即确定 |
| **反初始化** | 仅少数模块有 `deinit()`，格式不统一 | 标准化 `deinit()` + `save_context()` / `restore_context()` |
| **模块重启** | 无标准机制，需手动联系所有引用 | `lm.restart(name)` 自动处理 deinit → init 流程 |
| **电源协调** | PowerService 发布 POWER_STATE_CHANGE 事件，各模块自行响应 | `lm.set_power_mode()` 统一调度，自动管理子模块挂起/恢复 |
| **引用管理** | 无。Driver 不知道自己被谁引用 | `get()/put()` 引用计数，引用归零后自动挂起 |
| **错误处理** | 初始化失败仅跳过打印 | ERROR 状态 + `restart()` 隔离恢复 |
| **空闲管理** | 无。所有模块一直 tick | `idle_timeout_ms` 自动挂起非关键模块 |
| **性能监控** | 主循环手动测量 each tick 耗时 | `health_report()` 提供所有模块的 tick 耗时、状态、错误计数 |
| **依赖可见性** | 阅读架构文档才能了解 | `get_dependency_graph()` 运行期可查 |
| **代码复杂度** | main.py 171 行，清晰简单 | 引入管理器增加 ~300-500 行框架代码 |
| **内存开销** | 无额外开销 | 每个模块 ~200 字节元数据（23 模块 ~4.6 KB） |

### 6.2 当前框架的最小入侵

LifecycleManager 设计遵循对现有模块**零修改原则**：

- BaseModule 添加的 `deinit()` / `save_context()` / `restore_context()` 全部提供空默认实现
- 现有模块不改任何代码即可被 LifecycleManager 管理（只是不能挂起）
- `register()` 可以包装成装饰器，不侵入模块构造函数
- `init_all()` 和 `tick_all()` 与原有 init_order 循环 100% 兼容

---

## 7. 迁移路径

### Step 1: BaseModule 添加 deinit()

```python
class BaseModule:
    # ... 现有代码 ...

    def deinit(self):
        """
        brief 反初始化，释放硬件资源
        note 空默认实现，保持向后兼容
        """
        pass
```

**影响范围**：仅修改 `Base_Module.py`，引入空方法。所有现有模块不受影响。

---

### Step 2: 为关键模块实现 deinit()

需要实现 `deinit()` 的模块：

| 模块 | deinit 内容 | 原因 |
|------|------------|------|
| GNSSDriver | 停止后台线程 + `gnss.stop()` | 后台线程持续运行，占用 EC200U 资源 |
| HeartRateDriver | 发送停止指令 0xFE + UART 关闭 | UART 通道释放 |
| BLEDriver | `ble.stop()` + `ble.deinit()` | 已有 deinit，对齐接口签名 |
| SMSDriver | 释放 SMS 实例 | AT 通道释放 |
| AudioDriver | 停止播放 + 释放音频资源 | EC200U 音频通道释放 |
| PWM_LED | Timer 停用 | 释放 TIM1_CH2 |
| Temp_Humid | `i2c.deinit()` | 释放 I2C1 总线 |
| IMUDriver | `i2c.deinit()` | 释放 I2C1 总线 |
| VoiceDriver | UART 关闭 | UART 通道释放 |

---

### Step 3: 创建 LifecycleManager 类

位置：`02_Software/core/LifecycleManager.py`

实现核心功能：
- `register()` — 注册模块，存储元数据
- `_topological_sort()` — DFS 拓扑排序，检测循环依赖
- `init_all()` — 按拓扑序逐模块 init，记录失败
- `tick_all()` — 遍历 ACTIVE 模块执行 tick，跳过其他状态
- `activate()` / `suspend()` — 状态切换 + deinit/init 回调
- `get()` / `put()` — 引用计数管理
- `health_report()` — 健康报告生成

**注意**：此步骤实现基本框架，不启用自动挂起。仅替换 init_order 循环。

---

### Step 4: 替换 main.py 的 init_order

```python
# 旧代码
init_order = [temp_humid, imu, gnss, light, ...]
for mod in init_order:
    mod.init()

# 新代码
lm = LifecycleManager()
lm.register(temp_humid, "temp_humid", depends_on=["i2c_bus"])
lm.register(imu, "imu", depends_on=["i2c_bus"])
lm.register(gnss, "gnss", depends_on=["at_channel"])
# ... 所有模块注册 ...
lm.init_all()  # 自动拓扑排序

# 主循环中
while True:
    lm.tick_all()  # 替换 for mod in init_order: mod.tick()
    event_bus.pump()
    time.sleep_ms(10)
```

**向后兼容**：`init_all()` 和 `tick_all()` 的行为与旧循环 100% 一致，只是排序变为自动。

---

### Step 5: 添加引用计数到 Service 模块

先在 Service 模块中选择几个进行改造：

1. **NavigationService**：使用 GNSS 时 `lm.get("gnss")`，释放时 `lm.put("gnss")`
2. **BLEService**：使用 GNSS 时 `lm.get("gnss")`（推送定位数据到手机）
3. **ControlService**：查询速度和位置时 `lm.get("gnss")`

引用计数激活模式示例：

```python
class NavigationService(BaseModule):
    def __init__(self, event_bus, lm, audio_driver=None):
        super().__init__()
        self.lm = lm
        # ...

    def _on_nav_cmd(self, payload):
        # 导航开始时获取 GNSS 引用
        self.lm.get("gnss")
        self.lm.get("audio")
        # ...

    def _on_nav_end(self):
        # 导航结束释放 GNSS 引用
        self.lm.put("gnss")
        self.lm.put("audio")
```

---

### Step 6: 添加 save/restore 回调到 Driver 模块

对有校准状态或初始化开销大的模块实现：

```python
class IMUDriver(BaseModule):
    def save_context(self):
        """保存校准偏移值"""
        return {
            "offset_x": self._data.get("offset_x", 0),
            "offset_y": self._data.get("offset_y", 0),
            "offset_z": self._data.get("offset_z", 0),
        }

    def restore_context(self, ctx):
        """恢复校准偏移值，跳过校准流程"""
        self._offset_x = ctx.get("offset_x", 0)
        self._offset_y = ctx.get("offset_y", 0)
        self._offset_z = ctx.get("offset_z", 0)
        # 跳过完整的 re-calibration
```

---

### Step 7: 启用自动挂起

在 Step 5-6 完成后，为可挂起的模块设置 `idle_timeout_ms`：

```python
lm.register(gnss, "gnss",
            can_suspend=True,
            idle_timeout_ms=300000,  # 5 分钟
            depends_on=["at_channel"])

lm.register(voice, "voice",
            can_suspend=True,
            idle_timeout_ms=120000)  # 2 分钟
```

LifecycleManager 内部启用超时轮询线程（或集成到主循环检查）：

```python
def tick_all(self):
    now = time.ticks_ms()
    for entry in self._entries.values():
        if entry.state == "ACTIVE":
            if entry.can_suspend and entry.ref_count == 0:
                idle_for = time.ticks_diff(now, entry.last_active)
                if idle_for > entry.idle_timeout_ms:
                    self._suspend(entry.name)  # 自动挂起
            try:
                entry.module.tick()
            except Exception as e:
                # 错误处理...
```

---

### Step 8: 全系统集成测试

测试用例：

| 测试 | 步骤 | 预期 |
|------|------|------|
| 普通初始化 | 启动系统 | 所有模块按拓扑序初始化成功 |
| 模块初始化失败 | 模拟 GNSS 初始化抛异常 | 仅 GNSS 进入 ERROR，其他模块正常 |
| 引用计数激活 | NavigationService.get("gnss") | GNSS 从 SUSPENDED → ACTIVE |
| 引用计数释放 | NavigationService.put("gnss") | GNSS 引用归零，idle_timeout 后挂起 |
| 自动挂起 | Voice 空闲 2 分钟 | Voice 自动进入 SUSPENDED |
| 自动恢复 | 语音指令唤醒 Voice | Voice 从 SUSPENDED → ACTIVE，恢复延迟 < 50ms |
| 电源模式切换 | lm.set_power_mode(SUSPENDED) | 可挂起模块全部 SUSPENDED，关键模块保持 ACTIVE |
| 模块重启 | lm.restart("gnss") | GNSS 从 ERROR → IDLE → ACTIVE |
| 依赖排序 | 检查 init 顺序 | i2c_bus 在 temp_humid 和 imu 之前 init |
| 循环依赖检测 | 故意声明 A.depends_on=[B], B.depends_on=[A] | init_all() 抛异常提示循环依赖 |

---

## 8. 风险与约束

### 8.1 MicroPython 线程安全

**风险**：MicroPython 没有 GIL（全局解释器锁），模块状态在后台线程和主循环之间共享。

**影响**：
- GNSS 后台线程在 `_gnss_thread()` 中修改 `_data_queue`，主循环在 `tick()` 中读取队列
- BLE 回调在 modem 线程中执行，写入 `cmd_buffer`
- `get() / put()` 修改 `ref_count` 可能被中断

**对策**：
- `ref_count` 使用 `machine.atomic()` 或关中断保护（如果 MicroPython 支持）
- 所有模块状态变更通过 EventBus 队列（线程安全）传播
- 后台线程不直接调用 `lm.get() / lm.put()`，只发布事件
- `deinit()` 内部不关闭其他模块仍在使用的中断源

### 8.2 挂起/恢复的竞态条件

**风险**：模块 A 正在挂起（SUSPENDING 状态）时，模块 B 调用 `get("A")`。

**场景**：
1. LM 判定 GNSS 空闲超时，发起 `suspend("gnss")`
2. `save_context()` 执行中，`_gnss_thread` 还未停止
3. NavigationService 收到导航指令，`get("gnss")`
4. GNSS 处于半挂起状态，`restore_context()` 与 `deinit()` 冲突

**对策**：
- SUSPENDING 是过渡态，`get()` 在 SUSPENDING 阶段可取消挂起
- 取消流程：终止 deinit → 恢复现场 → 回退到 ACTIVE
- 实现信号量：`_suspend_lock` 防止并发 deinit/init

### 8.3 deinit/init 时的后台线程

**风险**：模块有后台线程时，deinit 后线程还在运行，访问已释放的硬件。

**现状**：
- GNSSDriver 有 `_gnss_thread`
- BLEService 有 `notify_thread`
- CloudService（已废弃）有 `network_thread`

**对策**：
- `deinit()` 必须设置线程退出标志并等待（`time.sleep_ms` + 检查）
- 超时强制返回，不让 deinit 阻塞主循环超过 100ms
- 线程中访问硬件前检查 `is_init` 标志

### 8.4 内存开销

| 项目 | 大小 | 23 模块合计 |
|------|------|-----------|
| `_ModuleEntry` 对象 | ~80 bytes | ~1.8 KB |
| depends_on / needed_by 列表 | ~60 bytes | ~1.4 KB |
| 依赖图排序临时数据 | ~200 bytes | ~200 bytes |
| 空闲超时定时器列表 | ~40 bytes/模块 | ~0.9 KB |
| **总计** | | **~4.6 KB** |

STM32F413ZH 有 1.5 MB Flash + 256 KB SRAM，4.6 KB 可接受。

### 8.5 恢复延迟对关键功能的影响

| 模块 | 恢复延迟 | 影响场景 |
|------|---------|---------|
| GNSS | 3-5 s 搜星 | 停车后快速起步，定位需几秒恢复 |
| Voice | ~50 ms | 用户说"小洛包"到能被识别的延迟 |
| HeartRate | ~2 s | 重新佩戴后心率数据显示延迟 |

**缓解**：
- GNSS 挂起前保持最后的有效定位数据（`force_read()` 返回缓存）
- Voice `restore_context()` 只需打开 UART，不阻塞
- 碰撞检测期间禁止挂起 GNSS（碰撞 30s 内 `ref_count` 保持 > 0）

### 8.6 硬件总线清理

| 总线 | deinit 行为 | 风险 |
|------|------------|------|
| I2C1 | `machine.I2C.deinit()` | 释放前需确保 SCL/SDA 线进入高阻态，否则挂起后功耗高 |
| UART5 (HeartRate) | `machine.UART.deinit()` | 关串口时如果还未收到完整帧，帧数据丢失 |
| UART2 (Voice) | `machine.UART.deinit()` | ASRPRO 不收数据会持续输出，下次开串口时读到脏数据 |
| SPI1 (LCD) | `machine.SPI.deinit()` | LCD 无独立电源，SPI 时钟停止后 LCD 保持最后显示内容 |
| AT 串口 | EC200U AT 通道关闭 | AT 命令队列中的 pending 命令需先完成或丢弃 |

### 8.7 依赖循环检测

可能出现的循环依赖：
- A → B → C → A（显式循环）
- A → B, B → A（双向依赖）

LifecycleManager 在 `register()` 或 `init_all()` 时必须检测循环依赖，抛出明确的异常信息，指示循环路径。

```python
def _detect_cycle(self):
    # 使用 Kahn 算法或 DFS 染色法
    # 输出: [A, B, C, A] 循环路径
```

### 8.8 PowerService 与 LifecycleManager 的职责边界

| 职责 | PowerService | LifecycleManager |
|------|-------------|-----------------|
| 电池电压采样 | ✅ BatteryDriver → EVENT_BATTERY_READY | ❌ |
| 低电量判定 | ✅ 六档映射，判定是否低电 | ❌ |
| 省电模式决策 | ✅ 判定何时自动切换 SUSPENDED | ❌ |
| 模式切换执行 | ❌ 发布 EVENT_POWER_STATE_CHANGE | ✅ 接收事件后统一调度各模块挂起/恢复 |
| 引用计数管理 | ❌ | ✅ |
| 空闲超时管理 | ❌ | ✅ |

**整合方式**：
- PowerService 保留低电量判定和自动省电决策
- 决策结果通过 `EVENT_POWER_STATE_CHANGE` 发布
- LifecycleManager 订阅该事件，调用 `set_power_mode()` 执行协调
- `set_power_mode(SUSPENDED)` 自动遍历可挂起模块，逐一 `suspend()`

---

## 9. 参考

### 9.1 Zephyr Device Runtime Power Management

**URL**：https://docs.zephyrproject.org/latest/kernel/services/device_runtime/index.html

Zephyr RTOS 的设备运行时电源管理框架。每个设备驱动注册到 PM 子系统，支持：
- `pm_device_runtime_get()` / `pm_device_runtime_put()` 引用计数
- 自动挂起：引用归零且经过 `delay_ms` 后执行 `pm_device_action_run(PM_DEVICE_ACTION_SUSPEND)`
- 设备依赖管理：父设备必须在子设备之前就绪
- 状态映射：ACTIVE → SUSPENDING → SUSPENDED → RESUMING → ACTIVE

LifecycleManager 的引用计数和状态机设计受此启发。

### 9.2 Linux Runtime PM

**URL**：https://www.kernel.org/doc/html/latest/power/runtime_pm.html

Linux 内核的运行时电源管理核心机制：
- `pm_runtime_get_sync()` — 唤醒设备，阻塞等待设备进入 ACTIVE
- `pm_runtime_put()` — 释放引用，异步触发自动挂起
- `pm_runtime_put_sync()` — 释放引用，同步执行挂起
- `autosuspend_delay` — 自动挂起延迟，防止频繁唤醒
- 设备必须实现 `runtime_suspend` 和 `runtime_resume` 回调

核心设计模式：get 唤醒 / put 休眠，本设计完全采用。

### 9.3 Hubble Network Power State Machine

嵌入式低功耗网络设备的电源状态管理参考。5 状态模型：OFF → SLEEP → IDLE → ACTIVE → TX。关键设计：
- 状态转换带防抖延迟（debounce delay），避免在低功耗和高功耗之间频繁切换
- 共享外设的电源域管理，所有引用释放后才关闭外设时钟
- 唤醒源优先级：外部中断 > 定时器 > 网络活动

### 9.4 Peter Hinch micropower

**URL**：https://github.com/peterhinch/micropython-micropower

MicroPython 低功耗管理库，提供：
- `Scheduler` — 低功耗调度器，支持 tick-less 休眠
- `Device` — 外设抽象，支持 `__enter__` / `__exit__` 上下文管理器
- `PinWatcher` — GPIO 唤醒检测

适用于借鉴其低功耗调度器和设备上下文管理设计。

### 9.5 MicroPython PR #18424

**URL**：https://github.com/micropython/micropython/pull/18424

MicroPython 社区的多级 init/deinit 提案，标准化：
- `board_init()` / `board_deinit()` 系统级硬件初始化
- `module_init()` / `module_deinit()` 模块级初始化
- 层级化依赖管理，模块按优先级 init

该 PR 尚在讨论阶段，但方向一致。LifecycleManager 可以作为应用层的替代方案，不依赖固件支持。

### 9.6 当前项目参考

- 当前初始化代码：`02_Software/core/main.py`（main 函数，init_order 列表）
- 模块基类：`02_Software/core/Base_Module.py`（四元组规范）
- 配置常量：`02_Software/core/config.py`（电源模式、采样间隔）
- 电源管理服务：`02_Software/Modules/power_service.py`（低电量自动省电逻辑）
- 架构设计：`00_Planning/01_architecture.md`（四层架构、初始化顺序约束）

---

> **文档版本**：v0.1
>
> **状态**：设计参考（非实现计划）
>
> **适用时间**：比赛结束后重构时参考
>
> **维护者**：锦依卫队
