# 集成经验记录

> 记录测试中发现的问题、根因、修复方案，供全系统集成参考

---

## [2026-06-19] Wave 1 — PWM_LED 功耗状态切换 BUG

### 问题
SUSPENDED 模式下 PWM 不关灯。`set_brightness(0)` 被静默跳过。

### 根因
`PWM_LED._on_config_update()` 执行顺序错误：先改 `power_state` 再调 `set_brightness(0)`，但 `set_brightness` 第 105 行有 `power_state != ACTIVE → return` 守卫，导致 duty_cycle 永不被设 0。

### 修复
交换顺序——先关灯，再改状态：

```python
if payload["power_state"] != POWER_STATE_ACTIVE:
    self.set_brightness(0)       # ① 先关灯
self.ctx["power_state"] = payload["power_state"]  # ② 再改状态
```

### 教训
- **调用链守卫冲突**：`_on_config_update` → `set_brightness` 时，`set_brightness` 内部检查 `power_state`。如果前者先改了状态再调用，后者会因为守卫而提前 return。
- **测试覆盖的价值**：如无测试覆盖此场景，该 BUG 只会在真机演示时暴露。

---

## [2026-06-19] Wave 1 — BLE 重复 init 失败

### 问题
`test_device_integration.py` 6 个测试，第 2 个开始全部 BLE 初始化失败：
```
AT+QBTPWR=1 → +CME ERROR: 4
```

### 根因
EC200U BLE 硬件是**全局单例**。每个测试新建 `BLEDriver` + `init()` → 第 2 次调 `AT+QBTPWR=1` 时硬件还在上电状态，返回 error。

### 修复
BLE 共享单例，只 init 一次：

```python
_shared_ble = None

def make_system():
    global _shared_ble
    if _shared_ble is None:
        _shared_ble = BLEDriver(event_bus=bus)
        _shared_ble.init()
    else:
        _shared_ble.event_bus = bus
        bus.subscribe(EVENT_CONFIG_UPDATE, _shared_ble._on_config_update)
```

### 教训
- **4G/BLE/GNSS 等模块通常是全局单例**，测试代码不能反复 create/destroy
- 对于共享硬件的测试，用模块级单例而非每次重建
- `BLE.stop()` + `BLE.deinit()` 不能保证硬件完全复位，应避免重建

---

## [2026-06-19] Subagent 成本控制

### 问题
Waves 1-3 全部使用 `unspecified-high`，token 浪费。

### 改进（Wave 4 起）
| 任务类型 | 应用 Category |
|---------|--------------|
| 模板化单文件修改 | `quick` |
| 中等复杂度 | `unspecified-low` |
| 文档 | `writing` |
| 仅在必要时 | `unspecified-high` |

---

## [2026-06-19] 测试故障排查流程

### 两步判断
```
测试失败
  ├─ 测试代码问题？→ 检查硬件生命周期假设、资源竞争
  └─ 模块代码问题？→ 检查执行路径、状态守卫、event handler 顺序
```

### 优先检查
1. **硬件是否是全局单例**（BLE/4G/GNSS）
2. **方法调用链中是否有状态守卫被触发**
3. **event handler 的执行顺序是否导致状态不一致**
