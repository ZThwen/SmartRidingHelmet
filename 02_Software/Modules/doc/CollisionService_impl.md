# CollisionService 实现路径

> **所属层次**：Service 层（业务服务层）
> **对应需求**：F-ALM-01 碰撞自动报警
> **实现状态**：✅ **v1 已实现**（2026-05-19 测试通过）
> **负责人员**：张博涵

---

## 1. 模块概述

### 做什么
订阅 IMU 驱动发布的合加速度数据，**通过算法判断是否发生真实碰撞**（排除日常误碰、桌面抖动、拿取操作等误报），区分碰撞等级，发布碰撞事件供 AlarmService 联动报警。

### 不是什么
- **不是**硬件驱动（不操作 I2C、不读取 LIS2DH12TR）
- **不是**报警联动（不调 LED/Audio/LCD，那是 AlarmService 的事）
- **不是**云端推送（不直接发网络，碰撞事件由 AlarmService 转 CloudService）

### 一句话
**数据驱动的碰撞判决器**：收 IMU 加速度 → 滑动窗口 + 特征分析 → 判决碰撞等级 → 发碰撞事件。

---

## 2. 文件位置

参考模板：`Service_Template.py`

---

## 3. 依赖关系

### 3.1 数据依赖（通过事件耦合）

| 上游模块 | 事件 | 数据内容 | 用途 |
|:---------|:-----|:---------|:-----|
| IMUDriver | `EVENT_IMU_READY` | `{acc_x, acc_y, acc_z, acc_total, valid, timestamp}` | 碰撞判决的唯一数据源 |

### 3.2 输出依赖（被下游订阅）

| 下游模块 | 事件 | 数据内容 |
|:---------|:-----|:---------|
| AlarmService | `EVENT_COLLISION_DETECTED` | `{acc_total, level, timestamp}` |

### 3.3 外部依赖

| 依赖 | 路径 | 说明 |
|:-----|:-----|:-----|
| BaseModule | `core/Base_Module.py` | 四元组基类 |
| EventBus | `core/Event_Bus.py` | 事件发布/订阅 |
| config | `core/config.py` | 事件名常量、算法阈值参数 |

---

## 4. 事件接口

### 4.1 订阅事件

| 事件 | 回调方法 | 触发时机 | 回调做什么 |
|:----|:---------|:--------|:-----------|
| `EVENT_IMU_READY` | `_on_imu_data(payload)` | IMU 每 100ms 采集完成 | 将 acc_total 推入滑动窗口，执行实时判决 |
| `EVENT_CONFIG_UPDATE` | `_on_config_update(payload)` | 云端远程配置下发 | 更新碰撞阈值、窗口大小等算法参数 |

### 4.2 发布事件

| 事件 | 携带数据 | 发布时机 |
|:----|:---------|:--------|
| `EVENT_COLLISION_DETECTED` | `{acc_total, level, timestamp}` | 检测到真实碰撞，且通过防误报校验 |

---

## 5. 算法设计（核心）

### 5.1 核心挑战

项目最终无头盔外壳，实物为裸板。碰撞检测仅通过以下 6 种可复现的实测场景来验证：

| 场景分类 | 场景 | 实测方法 | 典型峰值(g) | 应检/应排 |
|:---------|:-----|:---------|:-----------|:----------|
| **真实碰撞** | ① 摔落地面 | 手持 1m 高处松手自由落体 | 20~100+ | 应检出 → Level 3 |
| | ② 敲击/拍打 | 用小工具用力敲击板边或背面 | 3~15 | 应检出 → Level 1~3 |
| **非碰撞(误报)** | ③ 桌面抖动 | 手持快速来回晃动 10cm 幅度持续 2~3 秒 | 2~4 | 应排除(振荡判别) |
| | ④ 拿起板子 | 从桌面拿起放至另一位置 | 1.5~3 | 应排除(幅度低+脉冲缓) |
| | ⑤ 桌面平移 | 在桌面上从 A 推到 B | 2~3 短促 | 应排除(脉冲窄) |
| | ⑥ 静止放置 | 板子放在桌面不动 | ~1 | 应排除(低于最低阈值) |

由此导出碰撞检测面临的 3 个核心矛盾：

| 挑战 | 表现 | 应对思路 |
|:-----|:-----|:---------|
| **敲击 vs 摔落** | 重敲(5~8g) 与摔落(>8g) 幅度重叠在中端 | 设置 >8g 确认阈值快速通道 |
| **抖动 vs 碰撞** | 抖动(2~4g 振荡) 与敲击(3~8g 单脉冲) 特征相似 | 用窗口内方差/波峰数量区分 |
| **拿取/平移 vs 碰撞** | 拿取(1.5~3g 缓变) 与敲击(尖锐脉冲) 波形不同 | 用脉冲宽度 + 变化率区分 |

### 5.2 三级判决流程

### 5.3 第一级：物理量纲归一化

IMU 驱动发布的 `acc_total` 单位为 **m/s²**。

算法内部需要统一使用 **g 值**（1g = 9.8 m/s²），因为碰撞阈值的工程经验值惯用 g 为单位。

```python
# 归一化：m/s² → g
acc_g = payload["acc_total"] / 9.8
```

### 5.4 第二级：滑动窗口 + 多级阈值

#### 滑动窗口结构

```python
self.ctx["window"] = [
    # 每个元素: {"acc_g": float, "timestamp": ms}
    # 窗口大小: self.cfg["window_size"] (默认 15 个样本)
    # 窗口时长: 约 15 × 100ms = 1500ms
]
```

#### 多级阈值设计

结合裸板 6 种实测场景的峰值分布：

| 等级 | 阈值范围(g) | 对应的裸板场景 | 判定策略 |
|:-----|:-----------|:--------------|:---------|
| 无碰撞 | < 1.5 | 静止放置、轻拿轻放 | 直接丢弃，不进入后续流程 |
| 潜在碰撞(可疑) | 1.5 ~ 3.0 | 桌面平移(误报)、桌面抖动(误报) | 必须通过第三级防误报鉴别 |
| 疑似碰撞 | 3.0 ~ 5.0 | 轻敲击(真)、剧烈抖动(误报) | 需要通过第三级防误报鉴别 |
| 高度疑似碰撞 | 5.0 ~ 8.0 | 重敲击(真) | 快速通道，脉冲宽度通过即判 |
| 确定碰撞 | > 8.0 | 摔落地面(真) | 直接判定 Level 3，免鉴别 |

```python
# 多级阈值配置（裸板适配）
COLLISION_THRESHOLD_SUSPECT    = 1.5   # 最低怀疑阈值(g) — 超过此值进入三级判决
COLLISION_THRESHOLD_LIKELY     = 3.0   # 疑似碰撞下限(g)
COLLISION_THRESHOLD_HIGH       = 5.0   # 高度疑似下限(g)
COLLISION_THRESHOLD_CONFIRMED  = 8.0   # 确定碰撞阈值(g) — 超过直判 Level 3

# 针对场景的专属阈值（裸板适配）
COLLISION_WINDOW_DURATION_MS   = 1500  # 滑动窗口总时长(ms)
COLLISION_PULSE_MIN_WIDTH_MS   = 60    # 最小脉冲宽度(ms) — 排除桌面平移
COLLISION_PRE_WINDOW_MS        = 300   # 碰撞前上下文窗口(ms)
COLLISION_FREE_FALL_THRESHOLD  = 0.8   # 失重阈值(g)
COLLISION_VARIANCE_THRESHOLD   = 0.5   # 振荡方差阈值(g²) — 排除桌面抖动
COLLISION_PEAK_COUNT_THRESHOLD = 3     # 振荡波峰计数阈值
COLLISION_COOLDOWN_MS          = 3000  # 防重复触发间隔(ms) — 裸板碰撞后稳定较快
```

### 5.5 第三级：防误报鉴别器

#### 鉴别器 A：脉冲宽度鉴别（排除桌面平移/拿取）

**原理**：真实碰撞（敲击/摔落）的加速度脉冲宽度通常 > 60ms（撞击后惯性延续），而桌面平移或拿起放下的脉冲是对称的窄尖峰（< 60ms），变化突然且快速回落。

**实现细节**：从峰值位置向左右两侧扫描，统计 acc_g ≥ `COLLISION_THRESHOLD_SUSPECT(1.5g)` 的连续样本数，换算为脉冲宽度。

**关键改动（适用于裸板环境）**：
- 扫描阈值从 `peak_val / 2` 改为 `threshold_suspect(1.5g)`：确保 5g 敲击的邻居 2.5g 被计入宽度，而 3g 平移的邻居 1.0g 不被计入
- 当峰值位于窗口最右边缘(`peak_idx == len-1`)时跳过判决：等待后续样本到来后再次判决，避免因右邻居数据尚未到达而被误判为窄脉冲

#### 鉴别器 B：失重前兆检测（裸板场景 —— 增强摔落识别）

**原理**：摔落地面场景中，裸板在自由落体阶段会短暂处于"失重"状态（acc_total ≈ 0g），随后才是撞击脉冲。此鉴别器在裸板环境下**不用于排除碰撞，而是用于增强摔落识别**——检测到失重后紧跟大脉冲，更确信为碰撞。

**实现**：

#### 鉴别器 C：振荡判别（排除桌面抖动）

**原理**：桌面抖动产生持续振荡（2~5g 连续波动），能量在时间上均匀分布。而敲击碰撞是瞬时能量集中。通过窗口内的**方差(Variance)** + **波峰计数**区分。

**实现**：

### 5.6 碰撞等级判定

通过第三级鉴别后，根据 acc_g 的**峰值** + **持续时间** 综合评定等级：

| 等级 | level 值 | 判定条件 | 对应的裸板场景 |
|:-----|:---------|:---------|:--------------|
| 轻微 | 1 | 峰值在 1.5~5.0g 且窗口内 > 阈值持续时间 < 200ms | 轻敲板子 |
| 中等 | 2 | 峰值在 5.0~8.0g 或峰值 > 4.0g 且持续 > 200ms | 中等力度敲击 |
| 严重 | 3 | 峰值 > 8.0g 或峰值 > 6.0g 且持续 > 300ms | 重敲击、摔落地面(>8.0g 直判) |

**注意**：等级 3 的碰撞将使 AlarmService 按 SOS 级别处理（即 level=3 时，AlarmService 将 `EVENT_ALARM_TRIGGERED` 的 `alarm_type` 标记为 `sos`）。

---

## 6. 内部状态机

CollisionService 不维护复杂的报警状态机（报警联动由 AlarmService 负责），仅维护滑动窗口数据队列和碰撞计数状态。

### 四元组关键字段

```
ctx:
  "is_init":           False       # 初始化完成标志
  "last_tick":         0          # 上次 tick 执行时间戳
  "power_state":       "ACTIVE"    # 功耗状态
  "window":            []          # 滑动窗口: [{acc_g, timestamp}, ...]
  "collision_count":   0          # 累计碰撞次数
  "last_collision_ts": 0          # 上次碰撞时间戳(用于 3000ms cooldown)

_data:
  "status":            "normal"    # 当前状态: normal / collision
  "last_peak":         0.0        # 最近峰值(g)
  "last_level":        0          # 最近碰撞等级
```

---

## 7. 实现步骤（按顺序）

### 步骤 1：搭骨架
1. 复制 `Service_Template.py`，重命名为 `CollisionService.py`
2. 改类名为 `CollisionService`，改 `self.name = "collision"`
3. 导入 config 事件常量、BaseModule
4. 定义 cfg/ctx/_data 四元组

### 步骤 2：实现 init()
1. 初始化滑动窗口 `self.ctx["window"] = []`
2. 订阅 `EVENT_IMU_READY` → `_on_imu_data()`
3. 订阅 `EVENT_CONFIG_UPDATE` → `_on_config_update()`
4. 设置 `is_init = True`
5. 打印 `[collision] ✓ 初始化完成`

### 步骤 3：实现 tick()
1. 功耗守卫：非 ACTIVE 状态不执行
2. 时间片校验：`check_interval_ms` 控制（与 IMU 采样间隔同步，设为 100ms）
3. **职责**：tick() 在本服务中只做超时守卫，不做实时推算。实时推算全部在 `_on_imu_data()` 回调中完成（因为碰撞检测需要实时响应，不能等到 tick 轮询）

### 步骤 4：实现 `_on_imu_data(payload)`
这是核心方法，实现"接收数据 → 更新窗口 → 实时判决"流水线：

### 步骤 5：实现 `_detect_collision()`
这是算法核心，实现第 5 节描述的完整判决流程。注意以下时序规则：

**边缘跳过逻辑**：如果峰值位于窗口最右边缘(`peak_idx == len(acc_values) - 1`)，直接返回 `None` 跳过本次判决。因为此时峰值的右侧邻居数据可能尚未通过 EventBus 队列处理完毕，如果立即进行脉冲宽度计算会错误地得到宽度为 0，导致真实碰撞被拦截。等待下一轮数据到来后峰值进入窗口内部再重新判决。

```
_detect_collision():
  1. 窗口数据不足 3 个 → return None
  2. 提取峰值 peak_val、位置 peak_idx
  3. peak_val < SUSPECT(1.5g) → return None
  4. peak_val > CONFIRMED(8.0g) → return 3 (快速通道)
  5. peak_idx 在窗口最右边缘 → return None (等待后续数据)
  6. _check_pulse_width 失败 → return None (桌面平移排除)
  7. _check_freefall 通过(检测到失重) → return None
  8. _check_oscillation 通过(检测到振荡) → return None
  9. _determine_level(peak_val) → 返回 1/2/3
```

### 步骤 6：防重复触发
1. `self.ctx["last_collision_ts"]` 记录上次碰撞发布时间
2. 如果 `time.ticks_diff(now, last_collision_ts) < 5000ms`，忽略本次碰撞
3. 这样设计避免：一次碰撞事故中可能产生多个超过阈值的脉冲（例如倒地后身体弹跳），防止重复报警

### 步骤 7：实现 `_on_config_update(payload)`
```python
_on_config_update(payload):
  if payload.get("target") == self.name:
    if "threshold_suspect" in payload:
      self.cfg["threshold_suspect"] = float(...)
    if "threshold_likely" in payload:
      self.cfg["threshold_likely"] = float(...)
    if "window_size" in payload:
      self.cfg["window_size"] = int(...)
    # ... 其他参数同理
  
  if "power_state" in payload:
    self.ctx["power_state"] = payload["power_state"]
```

### 步骤 8：实现辅助方法（窗口工具函数）

```python
# 裁剪窗口，只保留最近 window_duration_ms 内的数据
_trim_window(self, now_ms):
    cutoff = now_ms - self.cfg["window_duration_ms"]
    self.ctx["window"] = [
        x for x in self.ctx["window"]
        if x["timestamp"] >= cutoff
    ]

# 计算脉冲宽度（从峰值往两侧扫描到半幅值）
_calc_pulse_width(self, window_data, peak_idx, peak_val):
    从 peak_idx 向左扫描，找到 acc_g < peak_val/2 的位置 → left_idx
    从 peak_idx 向右扫描，找到 acc_g < peak_val/2 的位置 → right_idx
    返回 window[right_idx]["timestamp"] - window[left_idx]["timestamp"]

# 检查碰撞前窗口内是否有失重样本
_has_freefall_before(self, window_data, peak_idx):
    取 peak_idx 之前、最近 300ms 内的数据段
    检查是否有 acc_g < PRE_FREE_FALL_THRESHOLD(0.8g) 的样本
    返回 True/False

# 计算数据段的方差
_calc_variance(self, data_segment):
    计算均值 avg = sum / len
    方差 = sum((x - avg)²) / len
    返回方差值

# 统计波峰数量
_count_peaks(self, data_segment):
    遍历数据，统计 acc_g 值 >= 局部极大值的点
    返回波峰数量
```

### 步骤 9：实现 get_data()、get_status()

```python
get_data():
    return {
        "status": self._data["status"],
        "last_peak": self._data["last_peak"],
        "last_level": self._data["last_level"],
        "window_size": len(self.ctx.get("window", [])),
        "timestamp": time.ticks_ms()
    }

get_status():
    return {
        "is_init": self.ctx["is_init"],
        "power_state": self.ctx["power_state"],
        "collision_count": self.ctx["collision_count"],
        "last_collision_ts": self.ctx.get("last_collision_ts", 0)
    }
```

### 步骤 10：单元测试准备

测试文件位置：`02_Software/Tests/test_modules/test_collision_service.py`

测试用例建议覆盖以下场景（对应裸板 6 种实测情形）：

| 测试 ID | 场景 | 输入数据 | 期望结果 |
|:--------|:-----|:---------|:---------|
| TC-01 | **静止放置** | acc_g 在 0.9~1.1g 稳定 2 秒 | 不触发碰撞 |
| TC-02 | **桌面抖动** | acc_g 在 2.5~3.5g 持续振荡 1.5 秒，多波峰 | 被振荡判别器排除 |
| TC-03 | **桌面平移** | 单个对称短脉冲，峰值 3.5g，宽度约 60ms | 被脉冲宽度鉴别器排除 |
| TC-04 | **敲击测试** | 脉冲峰值 6g，宽度约 100ms，两侧邻居 ≥ 2.0g | 判定为碰撞，等级 2 |
| TC-05 | **摔落测试** | 脉冲峰值 18g，无失重前兆 | 直接过确认阈值，等级 3 |
| TC-06 | **防重复触发** | 间隔 3 秒的两个碰撞脉冲 | 第一次触发，第二次被防重复忽略 |

---

## 8. 约束规则（必须遵守）

| 规则 | 说明 |
|:-----|:-----|
| **不操作硬件** | 所有数据通过事件接收，不 import machine、不访问 I2C |
| **回调不阻塞** | `_on_imu_data()` 必须 < 1ms 完成（MicroPython 回调限制），所有重计算在回调内完成 |
| **tick() < 5ms** | tick() 只做超时守卫和状态维护 |
| **浮点精度** | 使用 MicroPython 原生 float，不做高精度小数运算，保留 2 位有效数字即可 |
| **防重复触发** | 两次碰撞事件最短间隔 3000ms，防止单次事故的多次脉冲重复报警（裸板碰撞后稳定较快，3000ms 已足够） |
| **无 sleep** | 任何方法中都不能调用 `time.sleep()` |
| **内存控制** | 滑动窗口最多保留 `window_size + 2` 个元素，防止内存泄漏 |
| **异常隔离** | 任何内部计算异常不能吞没事件泵，用 try/except 包裹算法逻辑 |

---

## 9. 需要在 config.py 中新增的常量

当前 `config.py` 已有基础配置，但不足以支撑三级判决算法。建议新增以下常量：

### 9.1 算法阈值（替换和扩充现有 `COLLISION_THRESHOLD_*` 系列）

```python
# ================= 碰撞检测配置（裸板适配）=================
# 多级阈值（单位：g，1g=9.8m/s²）
COLLISION_THRESHOLD_SUSPECT    = 1.5    # 最低怀疑阈值 — 超过此值进入三级判决
COLLISION_THRESHOLD_LIKELY     = 3.0    # 疑似碰撞下限
COLLISION_THRESHOLD_HIGH       = 5.0    # 高度疑似下限
COLLISION_THRESHOLD_CONFIRMED  = 8.0    # 确定碰撞阈值 — 免鉴别直接报警
GRAVITY                        = 9.8    # 重力加速度

# 滑动窗口
COLLISION_WINDOW_SIZE          = 15     # 滑动窗口最大容量(样本数)
COLLISION_WINDOW_DURATION_MS   = 1500   # 窗口覆盖时间范围(ms)

# 防误报鉴别参数（裸板脉冲更短，但平移/抖动特征不变）
COLLISION_PULSE_MIN_WIDTH_MS   = 60     # 最小有效脉冲宽度(ms) — 排除桌面平移
COLLISION_PRE_WINDOW_MS        = 300    # 碰撞前上下文窗口(ms)
COLLISION_FREE_FALL_THRESHOLD  = 0.8    # 失重判定阈值(g)
COLLISION_VARIANCE_THRESHOLD   = 0.5    # 振荡方差阈值(g²)
COLLISION_PEAK_COUNT_THRESHOLD = 3      # 振荡波峰计数阈值

# 防重复触发（裸板碰撞后稳定较快）
COLLISION_COOLDOWN_MS          = 3000   # 碰撞事件最短间隔(ms)

# 碰撞等级划分阈值（裸板适用）
COLLISION_LEVEL1_MAX_G         = 5.0    # 轻微碰撞最大峰值(g) — 轻敲板子
COLLISION_LEVEL1_MAX_DURATION_MS = 200  # 轻微碰撞最长持续时间(ms)
COLLISION_LEVEL2_MAX_G         = 8.0    # 中等碰撞最大峰值(g) — 用力敲击
COLLISION_LEVEL2_MAX_DURATION_MS = 300  # 中等碰撞最长持续时间(ms)
# 超过上述值即为等级 3（严重碰撞 — 重敲/摔落）
```

### 9.2 说明

上述常量分为 4 组，命名统一使用 `COLLISION_` 前缀：

| 组 | 常量范围 | 用途 |
|:---|:---------|:-----|
| 多级阈值 | `COLLISION_THRESHOLD_*` | 四个阶梯阈值，覆盖 1.5g ~ 8.0g |
| 窗口参数 | `COLLISION_WINDOW_*` | 滑动窗口的大小和时长 |
| 鉴别参数 | `COLLISION_PULSE_*`, `COLLISION_PRE_*`, `COLLISION_FREE_*`, `COLLISION_VARIANCE_*`, `COLLISION_PEAK_*` | 三个鉴别器的判定参数 |
| 碰撞等级 | `COLLISION_LEVEL1_*`, `COLLISION_LEVEL2_*` | 轻微/中等/严重的划分边界 |

### 9.3 兼容性说明

原有的 `COLLISION_THRESHOLD_SUSPECT`(2.0→1.5)、`COLLISION_THRESHOLD_CONFIRMED`(15.0→8.0) 等常量已全部替换为裸板适配值，无需保留旧值。

---

## 10. 算法调试辅助

### 10.1 裸板实况测试

新增文件：`Tests/test_modules/test_collision_live.py`

连接真实 IMU 硬件后运行此脚本，可以实时看到以下输出：
- 当前加速度（底行动态刷新）
- 实时碰撞状态：`正常` / `可疑` / `🌟轻微(1)` / `⚠️中等(2)` / `🚨严重(3)`
- 碰撞事件发布记录（测试结束汇总）

```
加速度:    9.3 m/s² ( 0.95 g) | 状态: 正常
加速度:   29.4 m/s² ( 3.00 g) | 状态: 可疑

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ⚡ 碰撞事件已发布!
  EVENT: EVENT_COLLISION_DETECTED
  等级: 3 (🚨严重(3))
  加速度: 156.8 m/s² (16.0 g)
  接收方: → AlarmService (报警联动)
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

### 10.2 调试模式

在 `cfg` 中增加 `debug` 开关：

```python
"debug": False  # 开启后打印窗口数据和判决过程
```

发布 `EVENT_COLLISION_DETECTED` 时打印一行摘要日志：

---

## 11. 与 AlarmService 的对接约定

CollisionService 发布 `EVENT_COLLISION_DETECTED` 后，AlarmService 的 `_on_collision(payload)` 将接收并处理：

| payload 字段 | 类型 | 说明 |
|:-------------|:-----|:-----|
| `acc_total` | float | 碰撞峰值加速度（单位: m/s²，与 IMU 发布格式一致） |
| `level` | int | 碰撞等级: 1=轻微, 2=中等, 3=严重 |
| `timestamp` | int | 碰撞发生时刻(ms) |

AlarmService 根据 `level` 决定报警行为：
- **level=1**：LED 慢闪(1000ms间隔) + 播放等级1报警音
- **level=2**：LED 中速闪(500ms间隔) + 播放等级2报警音
- **level=3**：LED 快闪(200ms间隔) + 播放等级3报警音 + `EVENT_ALARM_TRIGGERED` 的 `alarm_type` 标记为 `sos`

---

## 附录：算法参数调优指南

### 参数敏感度分析

| 参数 | 调大后果 | 调小后果 | 建议初始值 |
|:-----|:---------|:---------|:-----------|
| `THRESHOLD_SUSPECT`(1.5g) | 漏报轻敲碰撞 | 增加桌面平移误报 | 1.5g |
| `PULSE_MIN_WIDTH_MS`(60ms) | 漏报短促敲击(真碰撞) | 增加桌面平移误报 | 60ms |
| `COOLDOWN_MS`(3000ms) | 漏报摔落后二次撞击 | 一次摔落多次报警 | 3000ms |
| `VARIANCE_THRESHOLD`(0.5g²) | 漏报抖动中敲击 | 增加持续抖动误报 | 0.5g² |
| `CONFIRMED`(8.0g) | 漏报低高度摔落(5~8g) | 敲击被误判为摔落 | 8.0g |

### 调优策略（裸板）

1. **先用实况测试脚本摸底**：运行 `test_collision_live.py`，实际敲击/摔落/抖动裸板，观察实时加速度和状态变化
2. **从阈值下限开始**用 `THRESHOLD_SUSPECT=1.2g`测试，逐步提高到稳定抑制误报
3. **再调脉冲宽度**：用敲击 vs 平移反复对比，找到最稳定的 `PULSE_MIN_WIDTH_MS` 值
4. **最终验证**必须通过裸板 6 种场景（摔落/敲击/抖动/拿取/平移/静止）的完整测试