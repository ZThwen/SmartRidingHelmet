# DisplayService 实现路径

> **所属层次**：Service 层（业务服务层）
> **对应需求**：F-DISP-01 开机画面显示、F-DISP-02 正常骑行数据显示、F-DISP-03 光照自适应背光、F-DISP-04 报警画面联动
> **实现状态**：✅ **v2 已实现**（洛天依主题 + ⚠️报警图标 + 报警差异化 + 报警优先覆盖电源模式）
> **负责人员**：张文杰

---

## 1. 模块概述

### 做什么
管理LCD显示、背光调节、画面切换。协调 LCD、Audio 两个 Device 驱动完成画面显示，根据光照强度自动调节背光，响应报警事件切换画面。开机画面采用洛天依主题（头像 + 预渲染文字条 + 跑马灯），报警画面采用 ⚠️ 图标居中 + 差异化文字。

### 不是什么
- **不是**直接操作硬件（LCD/Audio 是 Device 层的事）
- **不是**传感器数据采集（那是各个传感器 Driver 的事）
- **不是**碰撞检测（那是 CollisionService 的事）

### 一句话
**事件驱动的显示编排器**：收到事件 → 更新数据 → 调 Device 接口 → 画面刷新。

---

## 2. 文件位置

```
02_Software/Modules/display_service.py
02_Software/images2.py                   # 洛天依头像 + ⚠️报警预警图标
```

测试文件：`02_Software/Tests/test_display.py`

---

## 3. 依赖的 Device 驷动

| 驷动 | 导入路径 | 调用方法 |
|:----|:--------|:---------|
| LCD | `Drivers.actuator.LCD.LCDDriver` | `lcd.clear()` / `lcd.show_image()` / `lcd.set_backlight()` / `lcd.lcd.show_string()` / `lcd.lcd.fill_rectangle()` / `lcd.show_nav_line()` |
| Audio | `Drivers.actuator.Audio.AudioDriver` | 通过 EventBus `EVENT_TTS_REQUEST` 间接调用 |

**注意**：DisplayService 不创建这些驱实例，由主循环创建后通过构造函数注入。

---

## 4. 事件订阅

在 `init()` 中完成订阅：

| 事件 | 回调方法 | 触发时机 | 本模块做什么 |
|:----|:--------|:--------|:-----------|
| `EVENT_TEMP_HUMID_READY` | `_on_temp_humid_ready(payload)` | TempHumidDriver 采集到温湿度 | 更新温度湿度数据 → 设脏标志 → tick() 中渲染 |
| `EVENT_GNSS_READY` | `_on_gnss_ready(payload)` | GNSSDriver 获取到定位 | 更新经纬度速度数据 → 设脏标志 |
| `EVENT_LIGHT_READY` | `_on_light_ready(payload)` | LightSensorDriver 读取到光照 | 根据光照强度自动调节背光（报警期间跳过） |
| `EVENT_ALARM_TRIGGERED` | `_on_alarm_triggered(payload)` | AlarmService 启动报警 | 设置延迟渲染标志 → tick() 中渲染报警画面 |
| `EVENT_ALARM_CANCELED` | `_on_alarm_canceled(payload)` | AlarmService 取消报警 | 恢复正常画面（延迟清屏） |
| `EVENT_POWER_STATE_CHANGE` | `_on_power_state_change(payload)` | PowerService 切换功耗状态 | 休眠关背光/唤醒恢复背光（报警优先覆盖） |
| `EVENT_CONFIG_UPDATE` | `_on_config_update(payload)` | 云端配置下发 | 更新开机时长、背光等参数 |
| `EVENT_NAV_DISPLAY` | `_on_nav_display(payload)` | NavigationService 导航内容变更 | 缓存导航文字，渲染时显示在第5行 |
| `EVENT_SYSTEM_READY` | `_on_system_ready(payload)` | 系统启动完成 | 释放图片数据，切换至 normal 画面 |

---

## 5. 事件发布

DisplayService 仅发布 TTS 事件（开机欢迎语）：
- `EVENT_TTS_REQUEST`：开机时发布，文本为"依路护航，锦依卫队为您保驾护航"

---

## 6. 内部状态机

```
[blank] ──init()──> [boot] ──EVENT_SYSTEM_READY──> [normal]
```

### 四元组关键字段

```
cfg:
  "backlight_boot":      80          # 开机背光(%)
  "backlight_normal":    60          # 正常背光(%)
  "backlight_alarm":     100         # 报警背光(%)
  "light_level_1/2/3":   100/500/1000 # 光照阈值(lux)
  "backlight_level_1/2/3/4": 20/50/80/100 # 背光档位(%)
  "luotianyi_width/height": 100/100 # 洛天依头像尺寸
  "luotianyi_x/y":       30/0       # 洛天依头像位置
  "alarm_icon_width/height": 48/48   # ⚠️报警图标尺寸
  "alarm_icon_x/y":      56/0       # ⚠️报警图标位置（居中 x=(160-48)/2=56）
  "scroll_text":         "锦依卫队"   # 开机跑马灯文字
  "scroll_y":            118         # 跑马灯行Y坐标
  "scroll_speed_ms":     200         # 滚动刷新间隔(ms)
  "scroll_step_px":      8           # 滚动步长(px)
  "tts_welcome":         "依路护航，锦依卫队为您保驾护航"
  "sos_flash_interval_ms": 500       # SOS背光闪烁间隔(ms)
  "sos_flash_low/high":  30/100      # SOS背光闪烁亮度
  "sample_ms":           1000        # tick采样周期(ms)

ctx:
  "is_init":             False       # 初始化完成标志
  "is_busy":             False       # 操作中标志（防重入）
  "last_tick":           0           # 上次tick时间戳
  "display_mode":        "blank"     # 显示模式: blank/boot/normal/alarm
  "is_alarm_active":     False       # 报警是否激活
  "boot_displayed":      False       # 开机画面是否已显示
  "power_state":         "ACTIVE"    # 功耗状态
  "current_backlight":   60          # 当前背光亮度
  "err_count":           0           # 错误计数
  "alarm_type":          ""          # 报警类型: collision/sos/stealth
  "alarm_level":         0           # 报警等级
  "alarm_start":         0           # 报警触发时间戳

_data:
  "temp":                None        # 温度(°C)
  "humid":               None        # 湿度(%)
  "lat":                 None        # 纬度
  "lon":                 None        # 经度
  "speed":               None        # 速度(km/h)
  "light_intensity":     None        # 光照强度(lux)
  "luotianyi_loaded":    False       # 洛天依头像是否加载成功
  "boot_text_loaded":    False       # 开机文字条是否加载成功
  "alarm_icon_loaded":   False       # ⚠️报警图标是否加载成功

内部标志:
  "_dirty":              False       # 脏标志：回调中只设标志，tick() 中统一渲染
  "_last_render_time":   0           # 上次渲染时间戳
  "_min_render_interval": 100        # 最小渲染间隔 100ms（防频繁刷新）
  "_nav_text":           ""          # 导航文字缓存（由 EVENT_NAV_DISPLAY 更新）
  "_boot_scroll_offset": 160         # 跑马灯当前偏移(px)
  "_boot_scroll_last_tick": 0        # 上次滚动更新时间
  "_sos_flash_state":    False       # SOS背光闪烁状态
  "_last_flash_tick":    0           # 上次闪烁切换时间
  "_alarm_needs_render": False       # 报警画面延迟渲染标志（零阻塞架构）
  "_collision_flash_state": True     # 碰撞文字闪烁状态
  "_collision_flash_last_tick": 0    # 上次碰撞闪烁切换时间
  "_needs_clear":        False       # 报警取消后延迟清屏标志
```

---

## 7. 实现步骤（按顺序）

### 步骤 1：搭骨架
1. 创建 `DisplayService` 类，继承 `BaseModule`
2. 改 `self.name = "display"`
3. 导入 config 事件常量、BaseModule
4. 定义 cfg/ctx/_data 四元组
5. 注入 lcd_driver、audio_driver 依赖
6. 初始化 `luotianyi_icon_data`、`boot_text_data`、`alarm_warning_icon_data`

### 步骤 2：实现 init()
1. 调用 `_load_images()` 加载洛天依头像、开机文字条和 ⚠️ 报警预警图标
2. 订阅 9 个事件（见第 4 节）
3. 调用 `_show_boot_screen()` 显示开机画面
4. 设置 `is_init = True`

### 步骤 3：实现 tick()
1. 状态守卫：未初始化则返回
2. 时间片校验：用 `sample_ms` 防止高频空转
3. **boot 模式等待 EVENT_SYSTEM_READY**：收到事件后调用 `_switch_to_normal()`
4. **boot 模式滚动动画**：`_tick_boot_scroll(now)` 更新跑马灯位置
5. **SOS 背光闪烁**：`_tick_sos_flash(now)` 切换背光亮度
6. **碰撞文字闪烁**：`_flash_collision_text()` 翻转图标+文字
7. **报警画面延迟渲染**：消费 `_alarm_needs_render` 标志
8. **报警取消延迟清屏**：消费 `_needs_clear` 标志
9. **正常画面脏渲染**：检查 `_dirty` 标志

### 步骤 4：实现图片加载 `_load_images()`
1. 尝试导入 `images2.LUOTIANYI_ICON_100x100`（洛天依头像）
2. 尝试导入 `images2.BOOT_TEXT_160x20`（开机文字条，来自 `boot_text.py`）
3. 尝试导入 `images2.ALARM_WARNING_ICON_48x48`（⚠️ 报警预警图标）
4. 捕获 ImportError 异常，标记加载失败但不阻塞初始化
5. 更新 `_data["luotianyi_loaded"]`、`_data["boot_text_loaded"]` 和 `_data["alarm_icon_loaded"]`

### 步骤 5：实现开机画面 `_show_boot_screen()`

### 开机画面（两阶段事件驱动）

**不再使用 2500ms 定时器**。改为事件驱动 boot→normal 切换。

1. `init()` 末尾：显示洛天依头像(100x100 RGB565) + 预渲染中文文字条"队伍：锦依卫队"(160x20, 来自 `boot_text.py`)。
2. 状态机置为 `boot`，等待 `EVENT_SYSTEM_READY` 事件。
3. 收到 `EVENT_SYSTEM_READY` 后：释放 `luotianyi_icon_data` + `boot_text_data`（回收 ~26KB RAM），切换 `normal`。

**新增订阅**：`EVENT_SYSTEM_READY` → `_on_system_ready()`

### 步骤 6：实现切换正常画面 `_switch_to_normal()`
1. 清屏
2. 设置 `display_mode = "normal"`
3. **释放图片数据**：`self.luotianyi_icon_data = None` + `self.boot_text_data = None` + `gc.collect()`（回收 ~26KB RAM）
4. 恢复背光（根据光照强度或默认值）
5. 调用 `_render_normal_screen()`

### 步骤 7：实现正常画面渲染 `_render_normal_screen()`
1. 格式化温湿度：`"T:25.5C"`、`"H:65%"`
2. 格式化定位：`"Lat:31.23 Lon:121.47"`
3. 格式化速度：`"V:18.5km/h"`
4. 显示在第1-4行 (y=10/35/60/85)
5. 恢复导航文字在第5行 (y=110)

### 步骤 7.5：实现报警画面渲染 `_render_alarm_screen()`
1. 根据 `alarm_type` 选择渲染策略：
   - `"collision"` → `_render_collision_screen(level)`
   - `"sos"` → `_render_sos_screen()`
   - `"stealth"` → 不调用（LCD 保持不变）
2. 设置 `alarm_override = True` 防止电源模式关闭背光
3. 显示经纬度（绿色小字，第0-11行）
4. 显示报警图标 ⚠️（48x48, x=56, y=0）
5. 显示报警文字（红色大字，偏移1px模拟加粗）
6. 显示等级/标识（黄色/红色）
7. 显示提示语（白色/黄色）
8. 显示倒计时/手动取消提示（灰色）

### 步骤 8：实现报警回调 `_on_alarm_triggered(payload)`
1. 设置 `is_alarm_active = True`
2. **零阻塞架构**：回调只设状态和标志，LCD操作延迟到 tick()
3. 判断 `alarm_type`：
   - `"stealth"` → LCD保持不变
   - `"collision"` → 延迟渲染碰撞画面 + 背光100% + 后续闪烁
   - `"sos"` → 延迟渲染SOS画面 + 背光100% + 后续背光闪烁
4. 设置 `lcd_driver.ctx["alarm_override"] = True`（报警优先覆盖电源模式）
5. 设置 `_alarm_needs_render = True`

### 步骤 9：碰撞报警画面 `_show_collision_screen(level)`
画面布局（160x128）：
- 第0-11行：经纬度（绿色小字）
- 第0-47行：⚠️ 报警预警图标居中（48x48, x=56）
- 第60-75行：**CRASH!**（红色大字，偏移1px模拟加粗）
- 第76-91行：**Lv:X**（黄色）
- 第92-107行：**Check Safety**（白色）
- 第108-123行：**Cancel in 30s**（灰色）

### 步骤 10：SOS报警画面 `_show_sos_screen()`
画面布局（160x128）：
- 第0-11行：经纬度（绿色小字）
- 第0-47行：⚠️ 报警预警图标居中（48x48, x=56）
- 第60-75行：**EMERGENCY!**（红色大字，偏移1px模拟加粗）
- 第76-91行：**SOS**（红色）
- 第92-107行：**Help Sent**（黄色）
- 第108-123行：**Press to Cancel**（灰色）

**SOS 画面只绘制一次**，后续 tick 仅切换背光亮度（30%/100% 500ms交替），不重绘文字（<1ms）。

### 步骤 11：碰撞文字闪烁 `_flash_collision_text()`
- 显示状态：重绘⚠️图标 + 红色碰撞预警文字
- 隐藏状态：用黑色填充覆盖图标和文字区域（fill_rectangle）
- 闪烁周期：500ms，仅翻转颜色，不重绘经纬度/等级/提示区域

### 步骤 12：报警取消 `_on_alarm_canceled(payload)`
1. 设置 `is_alarm_active = False`
2. 清除 `alarm_override` 标志
3. 恢复背光（根据光照强度或默认值）
4. 设置 `display_mode = "normal"`
5. 设置 `_needs_clear = True`（延迟清屏，避免阻塞回调）

### 步骤 13：功耗状态回调 `_on_power_state_change(payload)`
1. 报警优先覆盖：报警期间进入休眠不清屏不关背光
2. 报警期间唤醒：延迟渲染报警画面
3. 非报警期间：正常省电逻辑（清屏+关背光）

### 步骤 14：辅助方法
- `_tick_boot_scroll(now)`：跑马灯滚动动画（每200ms移动8px）
- `_tick_sos_flash(now)`：SOS背光闪烁
- `_get_backlight_by_light(light_intensity)`：光照→背光映射
- `_validate_image_data(data, width, height)`：验证图片数据
- `_format_temperature/humidity/location/speed()`：数据格式化
- `_on_nav_display(payload)`：缓存导航文字
- `get_data()`、`get_status()`：返回数据快照

---

## 8. 约束规则（必须遵守）

| 规则 | 说明 |
|:----|:-----|
| **不操作硬件** | 所有硬件交互必须通过调用 Device 驷动公共接口，不 import machine、st7735 |
| **tick() < 5ms** | tick() 只做超时检查、闪烁切换和脏标志渲染，不做阻塞操作 |
| **回调零阻塞** | 所有 _on_xxx 回调只设状态和标志，LCD绘制延迟到 tick() |
| **防重入** | 使用 `ctx["is_busy"]` 防止画面切换操作重入 |
| **图片验证** | 显示图片前必须调用 `_validate_image_data()` 验证数据有效性 |
| **背光限幅** | 背光值限制在 0-100 范围 |
| **报警优先** | 报警期间 `alarm_override=True`，电源模式不关闭背光和画面 |
| **开机图片释放** | `_switch_to_normal()` 释放洛天依头像 + 开机文字条数据 + gc.collect() |

---

## 9. 需要从 config.py 引用的常量

```python
from config import (
    # 事件
    EVENT_TEMP_HUMID_READY,
    EVENT_GNSS_READY,
    EVENT_LIGHT_READY,
    EVENT_ALARM_TRIGGERED,
    EVENT_ALARM_CANCELED,
    EVENT_POWER_STATE_CHANGE,
    EVENT_CONFIG_UPDATE,
    EVENT_NAV_DISPLAY,
    EVENT_TTS_REQUEST,
    # TTS 优先级
    PRIORITY_NAV,
    # 功耗
    POWER_STATE_ACTIVE,
    # TTS 文案
    TTS_BOOT_WELCOME,
)
```

---

## 10. 图片数据说明

**共 3 个图片资源**（luotianyi_icon + boot_text + alarm_warning_icon）。

| 图片 | 变量名 | 尺寸 | 位置 | 用途 | 释放时机 |
|:----|:-------|:----|:----|:----|:---------|
| 洛天依头像 | `LUOTIANYI_ICON_100x100` | 100×100 | x=30, y=0 | 开机画面 | `_switch_to_normal()` 后释放 + gc |
| 开机文字条 | `BOOT_TEXT_160x20` | 160×20 | x=0, y=103 | 开机画面中文文字 | `_switch_to_normal()` 后释放 + gc |
| ⚠️ 报警预警图标 | `ALARM_WARNING_ICON_48x48` | 48×48 | x=56, y=0 | 碰撞/SOS报警居中 | **不释放**（报警期间持续使用） |

图片存储位置：`02_Software/images2.py`（RGB565 格式 bytearray）

---

## 11. 开发中遇到的问题

### 11.1 LCD驱未注入导致崩溃

**现象**：测试时传入 `lcd_driver=None` 后 `_show_boot_screen()` 崩溃。

**原因**：`self.lcd_driver.clear()` 没有判空保护。

**解决**：所有 Device 调用前加 `if self.lcd_driver:` 保护。

### 11.2 图片数据验证缺失

**现象**：加载损坏或长度不足的图片数据时，`lcd_driver.show_image()` 崩溃或显示乱码。

**解决**：实现 `_validate_image_data()` 方法，验证数据非空、类型正确、长度足够。

### 11.3 回调阻塞 EventBus

**现象**：报警回调直接操作 LCD SPI，阻塞 EventBus.pump()，导致其他模块事件延迟。

**解决**：零阻塞架构 — 回调只设 `_alarm_needs_render = True`，LCD绘制延迟到 tick() 中执行。

### 11.4 报警期间电源模式关闭背光

**现象**：报警触发后，如果设备进入休眠，背光被关闭，报警画面不可见。

**解决**：引入 `alarm_override` 标志，报警期间 LCDDriver 在非 ACTIVE 模式也允许保持背光。

### 11.5 碰撞闪烁重绘覆盖经纬度

**现象**：碰撞闪烁时 `_flash_collision_text()` 用 `fill_rectangle` 覆盖了经纬度区域。

**解决**：闪烁隐藏状态时覆盖 y=0~78 区域（经纬度+图标+文字），显示状态时重绘图标和文字（经纬度不变，因为只显示一次不再变化）。

### 11.6 报警取消清屏时机

**现象**：报警取消回调中直接清屏，可能与新的报警触发冲突。

**解决**：引入 `_needs_clear` 延迟清屏标志，仅在 `display_mode == normal` 时消费。

---

## 12. 测试验证状态

### 12.1 已测试通过（真实硬件）

| 测试项 | 结果 | 说明 |
|:------|:----|:------|
| 初始化和开机画面 | ✅ | 洛天依头像显示、跑马灯滚动、"依路护航"居中、TTS播报 |
| 正常画面数据显示 | ✅ | 温湿度、定位、速度正确显示 |
| 光照自动调节背光 | ✅ | 不同光照强度自动调节背光 |
| 碰撞报警画面 | ✅ | ⚠️图标居中 + 碰撞预警文字 + 等级 + 提示 |
| SOS报警画面 | ✅ | ⚠️图标居中 + 紧急求救文字 + SOS标识 + 背光闪烁 |
| 静默报警 | ✅ | LCD保持不变 |
| 报警取消恢复 | ✅ | 取消报警后恢复正常画面和背光 |
| 功耗状态切换 | ✅ | 休眠关背光/唤醒恢复（报警期间不受影响） |
| 开机图片释放 | ✅ | `_switch_to_normal()` 后 gc.collect() 回收 RAM |

### 12.2 画面布局验证

**正常骑行画面**：
```
第1行 (y=10):  T:25.5C               (温度)
第2行 (y=35):  H:65%                 (湿度)
第3行 (y=60):  Lat:31.23 Lon:121.47  (定位)
第4行 (y=85):  V:18.5km/h            (速度)
第5行 (y=110): [导航行]              (由 NavigationService 通过 EVENT_NAV_DISPLAY 写入)
```

**碰撞报警画面**：
```
第0-11行:  Lat:31.23 / Lon:121.47    (经纬度，绿色)
第0-47行:  ⚠️ 图标居中 (48x48, x=56)  (报警预警图标)
第60-75行: CRASH!                    (红色大字，偏移1px加粗)
第76-91行: Lv:2                      (黄色)
第92-107行: Check Safety              (白色)
第108-123行: Cancel in 30s            (灰色)
```

**SOS报警画面**：
```
第0-11行:  Lat:31.23 / Lon:121.47    (经纬度，绿色)
第0-47行:  ⚠️ 图标居中 (48x48, x=56)  (报警预警图标)
第60-75行: EMERGENCY!                (红色大字，偏移1px加粗)
第76-91行: SOS                       (红色)
第92-107行: Help Sent                 (黄色)
第108-123行: Press to Cancel           (灰色)
```

---

## 13. 后续可调整的内容

| 可调整项 | 原因 |
|:---------|:------|
| 开机图片释放时机 | `EVENT_SYSTEM_READY` 触发条件 |
| 背光档位 | `backlight_level_1/2/3/4` 可调整 |
| 光照阈值 | `light_level_1/2/3` 可调整 |
| 开机TTS文本 | `cfg["tts_welcome"]` / `TTS_BOOT_WELCOME` 可修改 |
| 报警背光 | `cfg["backlight_alarm"]` 可调整 |
| SOS闪烁参数 | `sos_flash_interval_ms` / `sos_flash_low/high` 可调整 |
| 跑马灯速度 | `scroll_speed_ms` / `scroll_step_px` 可调整 |
| ⚠️ 图标尺寸 | `alarm_icon_width/height/x/y` 可调整 |
