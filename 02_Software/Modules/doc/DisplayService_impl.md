# DisplayService 实现路径

> **所属层次**：Service 层（业务服务层）
> **对应需求**：F-DISP-01 开机画面显示、F-DISP-02 正常骑行数据显示、F-DISP-03 光照自适应背光、F-DISP-04 报警画面联动
> **实现状态**：✅ **v1 已实现**（真实硬件测试通过）
> **负责人员**：张文杰

---

## 1. 模块概述

### 做什么
管理LCD显示、背光调节、画面切换。协调 LCD、Audio 两个 Device 驱动完成画面显示，根据光照强度自动调节背光，响应报警事件切换画面。

### 不是什么
- **不是**直接操作硬件（LCD/Audio 是 Device 层的事）
- **不是**传感器数据采集（那是各个传感器 Driver 的事）
- **不是**碰撞检测（那是 CollisionService 的事）

### 一句话
**事件驱动的显示编排器**：收到事件 → 更新数据 → 调 Device 接口 → 画面刷新。

---

## 2. 文件位置

```
02_Software/Service/DisplayService.py
```

测试文件：`02_Software/Tests/test_display.py`

---

## 3. 依赖的 Device 驱动

| 驱动 | 导入路径 | 调用方法 |
|:----|:--------|:---------|
| LCD | `Drivers.actuator.LCD.LCDDriver` | `lcd.clear()` / `lcd.show_image()` / `lcd.show_alarm()` / `lcd.set_backlight()` / `lcd.lcd.show_string()` |
| Audio | `Drivers.actuator.Audio.AudioDriver` | `audio.play_tts(text)` |

**注意**：DisplayService 不创建这些驱动实例，由主循环创建后通过构造函数注入。

---

## 4. 事件订阅

在 `init()` 中完成订阅：

| 事件 | 回调方法 | 触发时机 | 本模块做什么 |
|:----|:--------|:--------|:-----------|
| `EVENT_TEMP_HUMID_READY` | `_on_temp_humid_ready(payload)` | TempHumidDriver 采集到温湿度 | 更新温度湿度数据 → 刷新正常画面 |
| `EVENT_GNSS_READY` | `_on_gnss_ready(payload)` | GNSSDriver 获取到定位 | 更新经纬度速度数据 → 刷新正常画面 |
| `EVENT_LIGHT_READY` | `_on_light_ready(payload)` | LightSensorDriver 读取到光照 | 根据光照强度自动调节背光 |
| `EVENT_ALARM_TRIGGERED` | `_on_alarm_triggered(payload)` | AlarmService 启动报警 | 显示报警画面（碰撞文字/SOS图标） |
| `EVENT_ALARM_CANCELED` | `_on_alarm_canceled(payload)` | AlarmService 取消报警 | 恢复正常画面 |
| `EVENT_POWER_STATE_CHANGE` | `_on_power_state_change(payload)` | PowerService 切换功耗状态 | 休眠关闭背光/唤醒恢复背光 |
| `EVENT_CONFIG_UPDATE` | `_on_config_update(payload)` | 云端配置下发 | 更新开机时长、背光等参数 |

---

## 5. 事件发布

DisplayService **不发布**事件，仅订阅和处理事件。画面状态变化通过 `get_data()` / `get_status()` 供外部查询。

---

## 6. 内部状态机

```
[blank] ──init()──> [boot] ──2500ms超时──> [normal]
                         │                          │
                         │                          │
                         v                          v
                    [alarm] <───────报警触发─────────
                         │
                         │
                         v
                    [normal] <───────报警取消────────
```

### 四元组关键字段

```
cfg:
  "boot_display_ms":     2500        # 开机画面显示时长(ms)
  "backlight_boot":      80          # 开机背光(%)
  "backlight_normal":    60          # 正常背光(%)
  "backlight_alarm":     100         # 报警背光(%)
  "light_level_1/2/3":   100/500/1000 # 光照阈值(lux)
  "backlight_level_1/2/3/4": 20/50/80/100 # 背光档位(%)
  "sample_ms":           1000        # tick采样周期(ms)

ctx:
  "is_init":             False       # 初始化完成标志
  "is_busy":             False       # 操作中标志（防重入）
  "last_tick":           0           # 上次tick时间戳
  "display_mode":        "blank"     # 显示模式: blank/boot/normal/alarm
  "is_alarm_active":     False       # 报警是否激活
  "boot_displayed":      False       # 开机画面是否已显示
  "boot_start_time":     0           # 开机画面开始时间戳
  "power_state":         "ACTIVE"    # 功耗状态
  "current_backlight":   60          # 当前背光亮度
  "err_count":           0           # 错误计数

_data:
  "temp":                None        # 温度(°C)
  "humid":               None        # 湿度(%)
  "lat":                 None        # 纬度
  "lon":                 None        # 经度
  "speed":               None        # 速度(km/h)
  "light_intensity":     None        # 光照强度(lux)
  "logo_loaded":         False       # Logo是否加载成功
  "sos_icon_loaded":     False       # SOS图标是否加载成功
```

---

## 7. 实现步骤（按顺序）

### 步骤 1：搭骨架
1. 创建 `DisplayService` 类，继承 `BaseModule`
2. 改 `self.name = "display"`
3. 导入 config 事件常量、BaseModule
4. 定义 cfg/ctx/_data 四元组
5. 注入 lcd_driver、audio_driver 依赖

### 步骤 2：实现 init()
1. 调用 `_load_images()` 加载开机Logo和SOS图标
2. 订阅 7 个事件（见第 4 节）
3. 调用 `_show_boot_screen()` 显示开机画面
4. 设置 `is_init = True`
5. 打印 `[display] 初始化完成`

### 步骤 3：实现 tick()
1. 功耗守卫：非 ACTIVE 状态不执行
2. 时间片校验：用 `sample_ms` 防止高频空转
3. **开机画面超时检查**：如果 `display_mode == "boot"` 且超过 2500ms，调用 `_switch_to_normal()`
4. 更新 `last_tick` 时间戳

### 步骤 4：实现图片加载 `_load_images()`
1. 尝试导入 `images.QQ_ICON_40x40`（开机Logo）
2. 尝试导入 `images1.Quectel_Icon_160x20`（SOS图标）
3. 捕获 ImportError 异常，标记加载失败但不阻塞初始化
4. 更新 `_data["logo_loaded"]` 和 `_data["sos_icon_loaded"]`

### 步骤 5：实现开机画面 `_show_boot_screen()`
1. 清屏 `lcd_driver.clear()`
2. 验证并显示 Logo `lcd_driver.show_image()`
3. 设置开机背光 `lcd_driver.set_backlight(80)`
4. 播放 TTS `audio_driver.play_tts("智能骑行头盔已就绪")`
5. 设置 `display_mode = "boot"`
6. 记录 `boot_start_time = time.ticks_ms()`

### 步骤 6：实现正常画面渲染 `_render_normal_screen()`
1. 格式化温湿度：`"T:25.5C"`、`"H:65%"`
2. 格式化定位：`"Lat:31.23 Lon:121.47"`
3. 格式化速度：`"V:18.5km/h"`
4. 显示在第1-4行 (y=20/60/100/140)

### 步骤 7：实现光照背光回调 `_on_light_ready(payload)`
1. 提取光照强度值
2. 调用 `_get_backlight_by_light()` 计算背光档位
3. 设置 LCD 背光

### 步骤 8：实现报警回调 `_on_alarm_triggered(payload)`
1. 设置 `is_alarm_active = True`
2. 判断 `alarm_type`：
   - `"collision"` → 调用 `lcd_driver.show_alarm("collision")`
   - `"sos"` → 显示移远图标 + `"SOS!"` 文字
3. 设置报警背光 `lcd_driver.set_backlight(100)`
4. 设置 `display_mode = "alarm"`

### 步骤 9：实现报警取消回调 `_on_alarm_canceled(payload)`
1. 设置 `is_alarm_active = False`
2. 清屏
3. 恢复正常背光
4. 调用 `_render_normal_screen()` 恢复正常画面
5. 设置 `display_mode = "normal"`

### 步骤 10：实现功耗状态回调 `_on_power_state_change(payload)`
1. 如果进入非 ACTIVE 状态：关闭背光
2. 如果从非 ACTIVE 恢复：恢复背光

### 步骤 11：实现辅助方法
- `_get_backlight_by_light(light_intensity)`：光照→背光映射
- `_validate_image_data(data, width, height)`：验证图片数据
- `_format_temperature/humidity/location/speed()`：数据格式化
- `get_data()`、`get_status()`：返回数据快照

---

## 8. 约束规则（必须遵守）

| 规则 | 说明 |
|:----|:-----|
| **不操作硬件** | 所有硬件交互必须通过调用 Device 驱动公共接口，不 import machine、st7735 |
| **tick() < 5ms** | tick() 只做超时检查和时间戳更新，不做重操作 |
| **回调不阻塞** | 所有 _on_xxx 回调不能有 sleep、不能有阻塞 I/O |
| **防重入** | 使用 `ctx["is_busy"]` 防止画面切换操作重入 |
| **图片验证** | 显示图片前必须调用 `_validate_image_data()` 验证数据有效性 |
| **背光限幅** | 背光值限制在 0-100 范围 |
| **功耗联动** | 非 ACTIVE 状态时强制关闭背光 |

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
    # 功耗
    POWER_STATE_ACTIVE,
)
```

---

## 10. 开发中遇到的问题

### 10.1 LCD驱动未注入导致崩溃

**现象**：测试时传入 `lcd_driver=None` 后 `_show_boot_screen()` 崩溃。

**原因**：`self.lcd_driver.clear()` 没有判空保护。

**解决**：所有 Device 调用前加 `if self.lcd_driver:` 保护。构造签名 `DisplayService(event_bus, lcd_driver=None, audio_driver=None)` 明确允许 None。

### 10.2 图片数据验证缺失

**现象**：加载损坏或长度不足的图片数据时，`lcd_driver.show_image()` 崩溃或显示乱码。

**原因**：未验证图片数据长度是否符合 RGB565 格式要求（width × height × 2 字节）。

**解决**：实现 `_validate_image_data()` 方法，验证数据非空、类型正确、长度足够。

### 10.3 开机画面计时错误

**现象**：开机画面显示时长不准确，或未自动切换到正常画面。

**原因**：`boot_start_time` 未正确记录，或 tick() 中的时间差计算错误。

**解决**：在 `_show_boot_screen()` 中记录 `boot_start_time = time.ticks_ms()`，tick() 中用 `time.ticks_diff()` 正确计算经过时间。

### 10.4 光照调节背光报警时仍生效

**现象**：报警画面显示时，光照变化导致背光被自动调节，影响报警效果。

**原因**：`_on_light_ready()` 未检查 `is_alarm_active` 状态。

**解决**：在 `_on_light_ready()` 中增加 `if self.ctx["is_alarm_active"]: return`，报警时不调节背光。

---

## 11. 测试验证状态

### 11.1 已测试通过（真实硬件）

| 测试项 | 结果 | 说明 |
|:------|:----|:------|
| 初始化和开机画面 | ✅ | Logo显示、TTS播报、2.5秒后自动切换 |
| 正常画面数据显示 | ✅ | 温湿度、定位、速度正确显示 |
| 光照自动调节背光 | ✅ | 不同光照强度自动调节背光（20%/50%/80%/100%） |
| 碰撞报警画面 | ✅ | 显示碰撞文字，背光100% |
| SOS报警画面 | ✅ | 显示移远图标和"SOS!"文字，背光100% |
| 报警取消恢复 | ✅ | 取消报警后恢复正常画面和背光 |
| 功耗状态切换 | ✅ | 休眠关闭背光，唤醒恢复背光 |

### 11.2 测试要点

**test_display.py 关键设计**：
1. `wait_with_pump()` 函数：等待期间持续调用 `pump()` 和 `tick()`
2. 真实硬件测试：读取真实传感器数据
3. 每个步骤保持5秒：让用户观察屏幕变化
4. 不测试GNSS定位：室内无GPS信号

### 11.3 画面布局验证

**正常骑行画面**：
```
第1行 (y=20):  T:25.5°C              (温度)
第2行 (y=60):  H:65%                 (湿度)
第3行 (y=100): Lat:31.23 Lon:121.47  (定位)
第4行 (y=140): V:18.5km/h            (速度)
```

### 11.4 光照-背光映射验证

| 光照强度 (lux) | 背光亮度 (%) | 环境 |
|----------------|--------------|------|
| < 100 | 20 | 暗环境 |
| 100-500 | 50 | 室内环境 |
| 500-1000 | 80 | 明亮环境 |
| > 1000 | 100 | 户外强光 |

### 11.5 后续可调整的内容

| 可调整项 | 原因 |
|:---------|:------|
| 开机画面时长 | `cfg["boot_display_ms"]` 随时可改，云端可通过 `EVENT_CONFIG_UPDATE` 下发 |
| 背光档位 | `backlight_level_1/2/3/4` 可调整 |
| 光照阈值 | `light_level_1/2/3` 可调整 |
| 开机TTS文本 | `cfg["tts_welcome"]` 可修改 |
| 报警背光 | `cfg["backlight_alarm"]` 可调整 |
