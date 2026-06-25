# AudioService 实现文档

> **所属层次**：Service 层（业务服务层）
> **对应需求**：F-AUD-01 统一音频调度、F-AUD-02 优先级队列管理
> **实现状态**：✅ **v1 已实现**
> **负责人员**：-

---

## 1. 模块概述

### 做什么
统一管理所有 TTS/音频播放请求，按优先级调度 AudioDriver。高优先级可打断低优先级，报警期间拒绝非报警请求，队列上限 3 个，超时 5s 自动丢弃。

### 不是什么
- **不是**直接操作硬件（Audio 播放是 Device 层的事）
- **不是**音频文件管理（AudioDriver. play_file 视需求后期接入）
- **不是**报警编排（那是 AlarmService 的事，AudioService 只响应 `EVENT_ALARM_TRIGGERED` 设置 alarm_playing 标志）

### 一句话
**带优先级队列的音频调度器**：收到 TTS 请求 → 按优先级决定打断/入队/丢弃 → tick() 轮询出队。

---

## 2. 文件的定位

```
02_Software/Modules/audio_service.py
```

参考模板：`Service_Template.py`

---

## 3. 依赖的 Device 驱动

| 驱动 | 导入路径 | 调用方法 |
|:----|:--------|:---------|
| Audio | `Drivers.actuator.Audio.AudioDriver` | `play_tts(text)` / `stop()` |

**注意**：Audio 驱动实例由主循环创建后通过构造函数注入，AudioService 不负责创建。

---

## 4. 事件订阅

在 `init()` 中完成订阅：

| 事件 | 回调方法 | 触发时机 | 本模块做什么 |
|:----|:--------|:--------|:-----------|
| `EVENT_TTS_REQUEST` | `_on_tts_request(payload)` | 任何 Service 需要播报语音 | 按优先级规则调度播放/入队/丢弃 |
| `EVENT_ALARM_TRIGGERED` | `_on_alarm_triggered(payload)` | AlarmService 启动报警 | 设置 `alarm_playing=True`，清空队列中的非报警项 |
| `EVENT_ALARM_CANCELED` | `_on_alarm_canceled(payload)` | 报警超时或手动取消 | 清除 `alarm_playing` 标志 |

---

## 5. 优先级定义

| 优先级 | 值 | 常量 | 场景 |
|:-----|:--:|:----|:-----|
| 报警语音 | 0 | `PRIORITY_ALARM` | SOS/碰撞报警播报 |
| 导航播报 | 1 | `PRIORITY_NAV` | 导航转向、路径提示 |
| 控制反馈 | 2 | `PRIORITY_CTRL` | 灯光/音量调节确认、按键反馈 |

**数值越小优先级越高。**

---

## 6. 调度规则（核心逻辑）

```
请求到达 → _on_tts_request()
  │
  ├─ 报警中 & 非报警请求 → 直接丢弃
  │
  ├─ 高优先级(priority < current_priority) → 打断：stop() + 立即播放
  │
  ├─ 同优先级(priority == current_priority) → 覆盖：stop() + 立即播放
  │
  └─ 低优先级 → 入队等待
       ├─ 队列满 → 丢弃最旧的
       └─ 队列未满 → 追加到队尾
```

### 6.1 规则详解

| 规则 | 说明 |
|:----|:-----|
| **高优先级打断低优先级** | 检测到更高优先级请求时，调用 `audio_driver.stop()` 终止当前播放，立即播报新请求 |
| **同优先级覆盖当前** | 相同优先级的新请求无条件覆盖正在播放的内容（适用于导航连续播报、控制反馈快速切换） |
| **低优先级入队等待** | 低优先级请求放入 FIFO 队列，等当前播放结束由 tick() 出队 |
| **报警期间拒绝非报警** | `alarm_playing=True` 时，非 `PRIORITY_ALARM` 的请求直接丢弃（total_dropped +1） |
| **队列上限 3 个** | `cfg["queue_max_size"] = 3`，超限丢弃最旧的 |
| **超时 5s 丢弃** | 入队项超过 5s 未播放，由 tick() 定期清理丢弃 |

---

## 7. 内部状态机

```
IDLE ──收到 TTS 请求──> PLAYING (修改 current_priority)
  │                          │
  │                          ├── 播放结束(is_busy=False) ──> 出队下一个
  │                          │       │
  │                          │       └── 队列空 ──> IDLE (重置 current_priority)
  │                          │
  │                          ├── 收到更高/同优先级请求 ──> 打断/覆盖播放
  │                          │
  │                          └── 收到低优先级请求 ──> 入队
  │
  └── EVENT_ALARM_TRIGGERED ──> 设置 alarm_playing=True + 缓存报警TTS文本
                                   │
                                   ├── tick() 每5秒自动入队报警TTS（循环播报）
                                   │
                                   └── EVENT_ALARM_CANCELED ──> 清除 alarm_playing + 清空队列
```

---

## 8. 四元组接口

### cfg（静态配置）

| 字段 | 类型 | 默认值 | 说明 |
|:----|:----|:-----:|:-----|
| `queue_max_size` | int | 3 | 等待队列最大长度 |
| `timeout_ms` | int | 5000 | 入队项超时丢弃时间（ms） |

### ctx（运行时上下文）

| 字段 | 类型 | 初始值 | 说明 |
|:----|:----|:------:|:-----|
| `is_init` | bool | False | 是否已完成初始化 |
| `err_count` | int | 0 | 累计播放错误次数 |
| `alarm_playing` | bool | False | 是否正在报警中 |
| `current_priority` | int | `PRIORITY_CTRL+1` | 当前播放项优先级（越小越高） |

### _data（当前数据）

| 字段 | 类型 | 初始值 | 说明 |
|:----|:----|:-----:|:-----|
| `queue_size` | int | 0 | 当前队列长度 |
| `total_played` | int | 0 | 累计播放次数 |
| `total_dropped` | int | 0 | 累计丢弃次数 |

### 接口实现

| 接口 | 职责 | 说明 |
|:----|:-----|:-----|
| `init()` | 订阅事件，设置 `is_init=True` | 订阅 3 个事件 |
| `tick()` | 轮询 `is_busy` → 播放结束时出队下一个；报警期间每5秒自动入队报警TTS | 每次执行清理超时项 + 出队，<0.2ms |
| `get_data()` | 返回数据快照 | `{queue_size, total_played, total_dropped, timestamp}` |
| `get_status()` | 返回状态快照 | `{is_init, err_count, alarm_playing, current_priority, queue_size}` |

---

## 9. 队列设计

### 数据结构

```python
self._queue = [
    {"text": "前方500米右转", "priority": 1, "enqueue_time": 12345678},
    {"text": "音量已调至最大", "priority": 2, "enqueue_time": 12345679},
]
```

### 约束

| 项目 | 值 |
|:----|:--:|
| 数据结构 | `list of dict` |
| 最大长度 | 3（`cfg.queue_max_size`） |
| 超时时间 | 5000ms（`cfg.timeout_ms`） |
| 超时策略 | `tick()` 中 `_clean_expired()` 过滤移除，`total_dropped` 累加 |
| 满队列策略 | 丢弃最旧元素（`self._queue.pop(0)`），追加新元素到队尾 |

---

## 10. 数据流

```
调用方（NavigationService / ControlService 等）
  │
  ├── publish(EVENT_TTS_REQUEST, {"text": "xxx", "priority": n})
  │
  ▼
AudioService._on_tts_request(payload)
  │
  ├── 优先级判断 → 立即播放
  │     └── _play(item) → audio_driver.play_tts(text)
  │
  └── 优先级判断 → 入队
        └── self._queue.append({"text", "priority", "enqueue_time"})
              │
              ▼
主循环 tick() → AudioService.tick()
  ├── _clean_expired(now)  # 清理超时项
  └── is_busy? → no → self._queue.pop(0) → _play(item)
```

---

## 11. 需要从 config.py 引用的常量

```python
from core.config import (
    # 事件
    EVENT_TTS_REQUEST, EVENT_ALARM_TRIGGERED, EVENT_ALARM_CANCELED,
    # 优先级
    PRIORITY_ALARM, PRIORITY_NAV, PRIORITY_CTRL,
)
```

---

## 12. 初始化顺序

在 CollisionService 之后、AlarmService 之前初始化。

```
传感器 → 执行器 → CollisionService → AudioService → AlarmService → 其他 Service
```

**原因**：`AlarmService` 触发报警时会将 `alarm_playing` 置为 True，需要 AudioService 已经初始化完成。同时 AudioService 依赖 `EVENT_ALARM_TRIGGERED` 事件，AlarmService 在其后注册才能按顺序收到事件。

---

## 13. 约束规则（必须遵守）

| 规则 | 说明 |
|:----|:-----|
| **tick() < 5ms** | tick() 只做 `is_busy` 检查 + `_clean_expired` + 出队，不阻塞 |
| **回调不阻塞** | `_on_tts_request` 不能有 `time.sleep()`、不能有阻塞 I/O |
| **audio_driver 可能为 None** | 构造注入允许 None，每次调用前需 `if self.audio_driver:` 保护 |
| **不操作硬件** | 所有音频播放通过 AudioDriver 公共接口完成，不 import machine/quectel |
| **High 优先级永远不排队** | 优先级 0（ALARM）立即播放或丢弃，绝不入队（因为报警期间非报警请求已被丢弃） |

---

## 14. 开发中遇到的问题

### 14.1 audio_driver 未注入时崩溃

**现象**：测试时 `audio_driver=None`，`_on_tts_request` 中调用 `self.audio_driver.stop()` 崩溃。

**原因**：没有判空保护。

**解决**：所有 `self.audio_driver.xxx()` 调用前加 `if self.audio_driver:` 检查。构造签名明确允许 None。

### 14.2 报警期间队列未清理

**现象**：报警触发前有多个低优先级 TTS 请求排队，报警期间这些请求持续在 tick() 中出队播放。

**原因**：`_on_alarm_triggered` 没有清空非报警队列项。

**解决**：`_on_alarm_triggered` 中过滤队列，只保留 `priority <= PRIORITY_ALARM` 的项。

### 14.3 tick() 中 `is_busy` 误判

**现象**：tick() 检测到 `is_busy=False` 后出队，但 AudioDriver 实际还在播放收尾。

**原因**：`is_busy` 检查 `is_tts_playing` 和 `is_playing` 两个字段，部分状态更新有延迟。

**解决**：两个字段都检查（`or` 逻辑），后续还需根据实际硬件调试补全状态判断。

---

## 15. 测试验证状态

### 15.1 已测试通过

| 测试项 | 结果 | 说明 |
|:------|:----|:------|
| 高优先级打断低优先级 | ✅ | `PRIORITY_ALARM` 打断 `PRIORITY_NAV`，`stop()` + 立即播放 |
| 同优先级覆盖 | ✅ | 连续发出同优先级请求，后一个覆盖前一个 |
| 低优先级入队等待 | ✅ | 队列未满时追加，播放结束后自动出队 |
| 队列满丢弃策略 | ✅ | 队列满时丢弃最旧（队首），追加新到队尾 |
| 超时丢弃 | ✅ | tick() 清理超过 5s 的入队项，`total_dropped` 累加 |
| 报警期间丢弃非报警 | ✅ | `alarm_playing=True` 时非 ALARM 请求直接丢弃 |
| 报警触发清空队列 | ✅ | `_on_alarm_triggered` 过滤队列保留报警项 |
| 报警取消恢复正常 | ✅ | `_on_alarm_canceled` 清除 `alarm_playing` 标志，后续 TTS 入队正常 |

### 15.2 未测试 / 待验证

| 待测项 | 优先级 | 说明 |
|:------|:-----:|:------|
| 真机 tick() 稳定性 | 高 | PC 模拟测试通过，需真机验证 <5ms 耗时 |
| AudioDriver 并行播放冲突 | 中 | 报警音频（play_file）与 TTS 同时播放时的行为未验证 |
| 长时间运行队列泄露 | 中 | 极端情况下入队/出队是否一致 |
| 10ms 主循环节拍稳定性 | 中 | tick() 被主循环 10ms 间隔调用，出队延迟是否可接受 |

### 15.3 后续可调整的内容

| 可调整项 | 原因 |
|:---------|:------|
| 队列最大长度 | `cfg["queue_max_size"]` 随时可改 |
| 超时时间 | `cfg["timeout_ms"]` 可按需求调整（如导航场景需更长的排队等待） |
| 优先级数值 | `PRIORITY_ALARM/NAV/CTRL` 可在 config 中重新分配 |
| 报警期间策略 | 当前丢弃，可改为入队特殊队列等待报警结束后播放 |

---

## 16. 未来扩展

### 16.1 SD 卡音频播放

当前 AudioService 只通过 `audio_driver.play_tts(text)` 播放 TTS。如果需要播放 SD 卡音频文件（如导航提示音），有两种方案：

**方案 A（推荐）：AudioDriver 层封装**

```python
# AudioDriver 提供统一接口
audio_driver.play(text_or_file)  # 自动识别 text 和 file
```

调用方无需修改，AudioService 内部按需选择。

**方案 B：payload 扩展**

```python
# EVENT_TTS_REQUEST payload 扩展
{
    "text": "前方500米右转",      # TTS 文本（可选）
    "file": "SD:nav_turn.mp3",   # 音频文件路径（可选）
    "priority": PRIORITY_NAV,
}
```

AudioService 按优先级调度，具体播放方式由 AudioDriver 决定。推荐方案 A，对 Service 层透明。

### 16.2 语音指令识别集成

当 VoiceDriver（ASRPRO）集成后，AudioService 可以订阅 `EVENT_VOICE_COMMAND` 事件，根据指令触发对应 TTS 反馈：

```python
# 未来可订阅
EVENT_VOICE_COMMAND → 识别指令 → publish TTS 反馈
```

### 16.3 音量控制联动

后续控制音量时可通过 `EVENT_TTS_REQUEST` 携带音量参数（当前 AudioDriver 不支持音量控制），扩展 payload：

```python
{
    "text": "当前音量: 50%",
    "priority": PRIORITY_CTRL,
    "volume": 50,        # 可选，后续扩展
}
```

---

## 17. 代码概览

```python
class AudioService(BaseModule):
    def __init__(self, event_bus=None, audio_driver=None):
        # 四元组初始化 + self._queue = []

    def init(self):
        # 订阅 EVENT_TTS_REQUEST / EVENT_ALARM_TRIGGERED / EVENT_ALARM_CANCELED

    def tick(self):
        # 轮询 is_busy → 清理超时 → 出队播放

    def _on_tts_request(self, payload):
        # 优先级调度核心：打断/覆盖/入队/丢弃

    def _on_alarm_triggered(self, payload):
        # alarm_playing = True + 清除非报警队列

    def _on_alarm_canceled(self, payload):
        # alarm_playing = False + 清空队列 + 重置报警TTS状态

    def _clean_expired(self, now):
        # 过滤超时项（>5s）

    def _play(self, item):
        # audio_driver.play_tts(text)

    def get_data(self): ...
    def get_status(self): ...
```

**总行数**：284 行（含注释和空行）
**核心逻辑**：~180 行
