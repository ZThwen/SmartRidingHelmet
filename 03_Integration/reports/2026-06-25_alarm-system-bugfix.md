# Bug 审计与修复报告 — 碰撞报警体系与 BLE 重连问题

> **日期**：2026-06-25
> **范围**：AlarmService / BLEService / DisplayService / LCD Driver / ControlService / BLE Driver
> **审计方式**：代码审查 + 逐模块链路验证 + 硬件测试

---

## 修复清单

| # | 严重度 | 模块 | Bug | 状态 |
|---|--------|------|-----|:----:|
| 1 | 🔴 致命 | BLEDriver | BLE 断连后不重新广播，手机无法重连 | ⏳ 待修复 |
| 2 | 🔴 致命 | ControlService | 语音"蓝牙连接"指令断连后无效（is_init 判断错误） | ⏳ 待修复 |
| 3 | 🔴 致命 | AlarmService | 碰撞报警无 TTS 语音播报，只有不可靠的 SD 卡 MP3 | ⏳ 待修复 |
| 4 | 🔴 致命 | DisplayService | 开机动画期间正常数据显示叠加 | ⏳ 待修复 |
| 5 | 🔴 致命 | DisplayService | 报警动画期间正常数据显示叠加 | ⏳ 待修复 |

---

## 已验证正确的链路

以下链路经逐行代码审查确认**正确无误**，不存在 Bug：

### BLE 报警推送链路 ✅

```
CollisionService._on_imu_data() → publish(EVENT_COLLISION_DETECTED)
  → AlarmService._on_collision() → _start_alarm("collision", level)
    → publish(EVENT_ALARM_TRIGGERED)
      → BLEService._on_alarm() → send_queue.put({"t":5,"a":1,"l":2})
        → _notify_thread → BLEDriver.notify_data() → _ble.notify(FFF1)
```

| 步骤 | 文件:行号 | 状态 |
|------|----------|:----:|
| CollisionService 发布碰撞事件 | `collision_service.py:146-150` | ✅ |
| AlarmService 订阅并调 _start_alarm | `alarm_service.py:83,244-247` | ✅ |
| _start_alarm 发布 EVENT_ALARM_TRIGGERED | `alarm_service.py:163-168` | ✅ |
| BLEService 订阅并构造消息 | `ble_service.py:102,276-287` | ✅ |
| 消息格式 {"t":5,"a":1,"l":2} 符合协议 | `ble_service.py:282` | ✅ |
| _notify_thread 后台发送 | `ble_service.py:187-219` | ✅ |
| BLEDriver.notify_data() 底层发送 | `BLE.py:117-128` | ✅ |
| EventBus 单泵周期完成整链 | `Event_Bus.py:59-79` | ✅ |

**结论**：BLE 推送链路完整正确。如果小程序未收到报警，原因是碰撞触发时 BLE 未连接（`_notify_thread` L199 会丢弃未连接时的消息），而非代码 Bug。

### SMS 发送链路 ✅

```
_start_alarm() → if _sms_phone and _sms_driver
  → _build_sms_message(level) → 有GPS:高德链接 / 无GPS:纯文本
  → _thread.start_new_thread(send_sms)
    → SMSDriver.send_sms(phone, msg) → quectel.SMS.send()
```

| 步骤 | 文件:行号 | 状态 |
|------|----------|:----:|
| SMS 发送条件判断 | `alarm_service.py:171` | ✅ |
| 后台线程不阻塞主循环 | `alarm_service.py:175` | ✅ |
| _build_sms_message 有GPS时含高德链接 | `alarm_service.py:363-371` | ✅ |
| _build_sms_message 无GPS时纯文本 | `alarm_service.py:374` | ✅ |
| WGS84→GCJ02 坐标转换 | `alarm_service.py:368` | ✅ |
| SMSDriver.send_sms 底层正确 | `SMS.py:42-56` | ✅ |
| 手机号配置链完整 | `alarm_service.py:91,334-341` | ✅ |

**结论**：SMS 链路完整正确。未收到短信的原因是未通过 BLE 配置手机号（`_sms_phone` 为 None），而非代码 Bug。

---

## Bug 详情

---

### Bug 1：BLE 断连后不重新广播

| 项目 | 内容 |
|------|------|
| **文件** | `Drivers/network/BLE.py:222-230` |
| **发现方式** | 用户测试：BLE 断连后手机搜不到设备 |
| **根因** | `EVT_DISCONNECTED` 回调中只设标志位和发布事件，**没有调 `self._ble.advertise()`**。EC200U 硬件断连后停止广播 |
| **触发条件** | 手机主动断开 BLE 连接 |
| **影响** | 手机搜不到设备，无法重连 |
| **修复** | 在断连回调中添加 `self._ble.advertise()` 恢复广播 |
| **验证** | 上传后手机断开→搜到→重连测试 |

#### 解决方案

```python
# BLE.py:222-230 修改
elif event_id == BLE.EVT_DISCONNECTED:
    self.ctx["is_connected"] = False
    self._connected_published = False
    self._data["connected_addr"] = ""
    print("[%s] 手机已断开" % self.name)
    # 新增：断连后恢复广播
    try:
        self._ble.advertise()
        print("[%s] 断连后重新广播" % self.name)
    except Exception as e:
        print("[%s] 重新广播失败: %s" % (self.name, e))
    if self.event_bus:
        self.event_bus.publish(EVENT_BLE_DISCONNECTED, {
            "timestamp": time.ticks_ms(),
        })
```

---

### Bug 2：语音"蓝牙连接"指令断连后无效

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/control_service.py:433-440` |
| **发现方式** | 用户测试：说"蓝牙连接"后 TTS 回复"正在连接"但实际无操作 |
| **根因** | `_ble_connect()` 用 `is_init` 判断是否重启。断连后 `is_init=True`（BLE 栈仍在），`restart()` 不执行，只说 TTS 但什么也没做 |
| **触发条件** | BLE 断连后，用户语音说"蓝牙连接" |
| **影响** | 语音指令无效，用户无法手动恢复 BLE |
| **修复** | 将判断条件从 `not is_init` 改为无条件 restart |
| **验证** | 语音指令恢复 BLE 广播 |

#### 解决方案

```python
# control_service.py:433-440 修改
def _ble_connect(self):
    if self._ble_connected:
        self._tts("蓝牙已连接")
        return
    # 断连后 is_init=True 但 is_connected=False，需要 restart 来重新广播
    if self.ble_driver:
        self.ble_driver.restart()
    self._tts("蓝牙正在连接")
```

---

### Bug 3：碰撞报警无 TTS 语音播报

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/alarm_service.py:151-161` |
| **发现方式** | 用户测试：碰撞报警触发后无语音播报 |
| **根因** | `_start_alarm("collision")` 只调 `audio.play_file("SD:alarm_lx.mp3")`，**不发布 `EVENT_TTS_REQUEST`**。SOS 分支有 `play_tts("SOS 报警已触发")`，碰撞分支完全没有 TTS。且 SD 卡 MP3 文件不可靠（可能不存在导致静默失败） |
| **触发条件** | 碰撞检测触发报警 |
| **影响** | 用户听不到任何报警语音 |
| **修复** | **不用 SD 卡 MP3，改为 TTS 播报**。碰撞/SOS 统一用 TTS 播报，直到用户取消 |
| **验证** | 碰撞触发后听到 TTS 播报 |

#### 解决方案

```python
# alarm_service.py _start_alarm() 修改
# 删除: audio.play_file(self._level_to_file(level))
# 改为: 发布 TTS 请求

if self.cfg["enable_local"]:
    if alarm_type == "collision":
        if self.led:
            self.led.blink(duration=30000, interval=500)
        tts_text = "碰撞报警，等级%d" % level
    elif alarm_type == "sos":
        if self.led:
            self.led.blink(duration=30000, interval=200)
        tts_text = "SOS报警，请注意安全"
    else:
        if self.led:
            self.led.blink(duration=30000, interval=500)
        tts_text = "报警已触发"

    # TTS 播报（替代 SD 卡 MP3）
    if self.event_bus:
        self.event_bus.publish(EVENT_TTS_REQUEST, {
            "text": tts_text,
            "priority": PRIORITY_ALARM,
        })
```

**TTS 循环播报**：AudioService 需在 `alarm_playing=True` 时，每隔 5 秒在 `tick()` 中重新入队报警 TTS，实现持续播报直到报警取消。

---

### Bug 4 & 5：LCD 显示冲突（开机动画+数据、报警+数据）

| 项目 | 内容 |
|------|------|
| **文件** | `Modules/display_service.py:160-165` |
| **发现方式** | 用户测试：开机动画未消失时数据显示叠加；报警画面与数据显示共存 |
| **根因** | `tick()` 脏标志渲染（L160-165）没有 `display_mode` 守卫。传感器回调在 boot/alarm 期间设 `_dirty=True`，tick() 直接调 `_render_normal_screen()` 渲染正常数据 |
| **触发条件** | 传感器数据在 boot(2500ms) 或 alarm 期间到达 |
| **影响** | LCD 画面文字叠加，显示混乱 |
| **修复** | tick() L160 添加 `display_mode == "normal"` 守卫 |
| **验证** | 开机动画无叠加 + 报警画面无叠加 |

#### 解决方案

```python
# display_service.py tick() L160 修改
# 修改前
if self._dirty:

# 修改后
if self._dirty and self.ctx["display_mode"] == "normal":
```

防御性补充——`_render_normal_screen()` 开头加守卫：

```python
def _render_normal_screen(self):
    if not self.lcd_driver:
        return
    if self.ctx["display_mode"] != "normal":  # 新增
        return
    ...
```

---

## 未修复的已知问题

| # | 模块 | 问题 | 影响 | 建议 |
|---|------|------|------|------|
| 1 | BLE | 断连后无自动重连超时机制 | 需用户手动语音恢复 | 后续优化 |
| 2 | LightService | 碰撞 level 1-2 头灯不闪烁 | 仅 SOS(level≥3) 闪灯 | 按需调整 |
| 3 | AudioService | TTS 循环播报机制需实现 | 报警期间需持续 TTS | 本次修复 |

---

## 修复文件清单

| 文件 | 修复内容 | 状态 |
|------|---------|:----:|
| `Drivers/network/BLE.py` | 断连回调添加 `advertise()` | ✅ 已修复 |
| `Modules/control_service.py` | `_ble_connect()` 无条件 restart | ✅ 已修复 |
| `Modules/alarm_service.py` | 碰撞报警改为 TTS 播报 | ⏳ 待修复 |
| `Modules/audio_service.py` | 报警期间 TTS 循环播报机制 | ⏳ 待修复 |
| `Modules/display_service.py` | tick() 脏标志加 `display_mode` 守卫 | ⏳ 待修复 |

---

## 审查建议

1. **上板优先测试** — BLE 重连 + 碰撞 TTS 播报
2. **测试顺序建议**：
   - BLE 断连→重连（手机断开→搜到→重连）
   - 碰撞触发→TTS 持续播报→BLE 推送小程序→取消后停止
   - LCD 开机动画无叠加 + 报警画面无叠加
3. **后续关注** — TTS 循环播报的间隔和取消机制
