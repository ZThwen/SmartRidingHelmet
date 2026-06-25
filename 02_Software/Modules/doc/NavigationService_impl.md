# NavigationService 实现路径

> **所属层次**：Service 层（业务服务层）
> **对应需求**：F-NAV-01 导航引导
> **实现状态**：✅ **v1 已实现**（2026-06-09）
> **负责人员**：郑皓文

---

## 1. 模块概述

### 做什么
接收 BLE FFF2 写入的导航指令（方向、距离、路名），解析后调用 Audio TTS 播报中文导航，并在 LCD 底部显示导航摘要行。

### 不是什么
- **不是**BLE 通信层（BLEDriver 负责 GATT 服务，BLEService 负责解析路由）
- **不是**路径规划（那是小程序端腾讯地图 API 的事）
- **不是**GPS 定位（那是 GNSSDriver 的事）

### 一句话
**导航指令播报器**：收 BLE 指令 → 解析 JSON → TTS 播报 + LCD 显示。

---

## 2. 文件位置

```
02_Software/Modules/navigation_service.py                # 本模块
```

---

## 3. 依赖的 Device 驱动

| 驱动 | 导入路径 | 调用方法 | 用途 |
|:----|:--------|:---------|:-----|
| Audio | `Drivers.actuator.Audio.AudioDriver` | `play_tts(text)` | TTS 语音播报（子线程非阻塞） |
| LCD | `Drivers.actuator.LCD.LCDDriver` | `lcd.show_string()` / `lcd.fill_rectangle()` | LCD 导航行显示 |

**注意**：NavigationService 不创建这些驱动实例，由主循环创建后通过构造函数注入。

---

## 4. 事件订阅

| 事件 | 回调方法 | 做什么 |
|:----|:--------|:-------|
| `EVENT_NAV_CMD` | `_on_nav_cmd(payload)` | 收到导航指令，解析 JSON → TTS + LCD |
| `EVENT_POWER_STATE_CHANGE` | `_on_power_state_change(payload)` | 电源状态变化，EMERGENCY 暂停导航 |
| `EVENT_ALARM_TRIGGERED` | `_on_alarm_triggered(payload)` | 报警触发，标记报警状态 |
| `EVENT_ALARM_CANCELED` | `_on_alarm_canceled(payload)` | 报警取消，清除报警状态 |

---

## 5. 事件发布

| 事件 | 携带数据 | 发布时机 |
|:----|:--------|:--------|
| `EVENT_TTS_REQUEST` | `{text, priority: PRIORITY_NAV}` | 收到导航指令时（静默报警期间不发布） |
| `EVENT_NAV_DISPLAY` | `{text: "> 200m 中山路"}` | 收到导航指令时（由 DisplayService 订阅缓存） |

---

## 6. 指令格式

### 6.1 BLE FFF2 写入格式

```json
{"a":"nav", "d":{"dir":"right", "dist":200, "road":"中山路"}}
```

| 字段 | 类型 | 说明 |
|:----|:-----|:-----|
| `a` | string | 固定 `"nav"` |
| `d.dir` | string | 方向：`left`/`right`/`straight`/`slight_left`/`slight_right`/`uturn`/`arrive`/`cancel` |
| `d.dist` | int | 距离（米） |
| `d.road` | string | 路名（可选） |

### 6.2 方向映射表

| 英文 | 中文 | LCD 符号 |
|:-----|:-----|:--------:|
| `left` | 左转 | `<` |
| `right` | 右转 | `>` |
| `straight` | 直行 | `^` |
| `slight_left` | 靠左 | `<` |
| `slight_right` | 靠右 | `>` |
| `uturn` | 掉头 | `U` |
| `arrive` | 到达目的地 | `*` |
| `cancel` | 导航结束 | `x` |

---

## 7. TTS 播报文本

| 场景 | TTS 文本 | 来源 |
|:----|:---------|:-----|
| 有路名 | `"前方200米右转进入中山路"` | `_build_tts_text()` |
| 无路名 | `"前方200米右转"` | `_build_tts_text()` |
| 到达 | `"已到达目的地"` | `TTS_NAV_ARRIVE` |
| 取消 | `"导航已结束"` | `TTS_NAV_CANCEL` |

**TTS 播放方式**：通过 EventBus 发布 `EVENT_TTS_REQUEST`（priority=PRIORITY_NAV），由 AudioService 统一调度优先级，非阻塞。

---

## 8. LCD 显示

导航行显示在 LCD 底部（y=110），格式：

| 场景 | LCD 文本 |
|:----|:---------|
| 有路名 | `> 200m 中山路` |
| 无路名 | `> 200m` |
| 到达 | `已到达` |
| 取消 | `导航结束` |

显示前先用黑色矩形清除旧内容，再写入新文本。同时发布 `EVENT_NAV_DISPLAY`（DisplayService 订阅缓存，渲染时恢复到第5行 y=110）。首次收到指令时直接写入 LCD，后续由 DisplayService 在渲染周期中恢复。

---

## 9. 数据流

```
小程序（腾讯地图 API 规划路线）
  │
  └── BLE FFF2 写入 {"a":"nav","d":{...}}
       │
       └── BLEService._ble_callback() → cmd_buffer.put()
            └── BLEService.tick() drain → _parse_and_route()
                 └── EventBus.publish(EVENT_NAV_CMD, {raw: ...})
                       │
                       └── NavigationService._on_nav_cmd()
                            ├── JSON 解析 → 提取 dir/dist/road
                            ├── EventBus.publish(EVENT_TTS_REQUEST) → AudioService 调度播放
                            └── EventBus.publish(EVENT_NAV_DISPLAY) → DisplayService 缓存渲染
```

---

## 10. 电源模式行为

| 电源模式 | 导航行为 |
|:--------|:--------|
| ACTIVE | 正常 TTS + LCD |
| SUSPENDED | TTS 正常，LCD 关闭（跳过 `_write_nav_line`） |
| EMERGENCY | 导航暂停（`nav_paused = True`，忽略新指令） |

---

## 11. 报警模式行为

| 报警类型 | 导航行为 |
|:--------|:--------|
| 碰撞/SOS | TTS 正常（不阻塞） |
| 静默报警（stealth） | TTS 静默（跳过 `_build_tts_text`） |

---

## 12. 实现步骤

### 阶段 A：定义方向映射
1. `_DIR_MAP`：英文 → 中文
2. `_DIR_SYMBOL`：英文 → LCD 符号
3. `_build_tts_text()`：构造 TTS 文本
4. `_build_lcd_text()`：构造 LCD 文本

### 阶段 B：实现 NavigationService 骨架
1. 继承 `BaseModule`，定义四元组
2. `init()`：订阅事件
3. `tick()`：空实现

### 阶段 C：实现导航指令处理
1. `_on_nav_cmd()`：JSON 解析 → 状态更新 → TTS + LCD
2. TTS 子线程：非阻塞播放
3. LCD 写入：清除旧内容 + 写新文本

### 阶段 D：实现电源/报警响应
1. `_on_power_state_change()`：EMERGENCY 暂停
2. `_on_alarm_triggered/canceled()`：静默报警跳过 TTS

---

## 13. 约束规则

| 规则 | 说明 |
|:----|:-----|
| **tick 为空** | 纯事件驱动，不需要周期调度 |
| **TTS 非阻塞** | 通过 EVENT_TTS_REQUEST 事件发布，AudioService 统一调度 |
| **EMERGENCY 暂停** | 紧急省电模式下忽略导航指令 |
| **静默报警跳过 TTS** | stealth 模式下不播放导航语音 |
| **LCD 行固定位置** | 导航行 y=110，不随其他画面变化 |
