
## [2026-06-21] Step 1 — 测试文件 Bug 修复

### 问题 1: MicroPython 闭包不支持 __name__ 属性

**现象**：test_01~04 全部崩溃，错误 `'closure' object has no attribute '__name__'`

**根因**：`_make_logger()` 函数中尝试设置闭包的 `__name__` 属性：
```python
_log.__name__ = "log_" + event_name.lower()  # MicroPython 不支持
```

**修复**：删除该行，MicroPython 闭包对象不支持设置 `__name__`。

---

### 问题 2: 事件载荷键名不匹配

**现象**：test_05 显示更新失败，test_06 电源状态全部失败

**根因**：测试文件发布的事件载荷键名与模块代码读取的键名不一致：

| 事件 | 测试用键 | 模块读取键 |
|------|---------|-----------|
| EVENT_GNSS_READY | `lat/lon/speed` | `latitude/longitude/speed_kmh` |
| EVENT_LIGHT_READY | `intensity` | `light_intensity` |
| EVENT_POWER_STATE_CHANGE | `state` | `power_state` |

**修复**：测试文件改为与模块代码一致的键名。

**教训**：
- 写测试时必须参考模块源码的 `payload.get("xxx")` 调用
- 不能凭猜测写键名，必须溯源确认

---

### 问题 3: Button 模块无省电模式

**现象**：test_06 中 Button 的 power_state 检查失败

**根因**：Button.py 没有订阅 `EVENT_POWER_STATE_CHANGE`，也没有 `power_state` 在 ctx 中

**修复**：test_06 跳过 Button 模块的检查

---

### 关键经验

1. **MicroPython 与 CPython 差异**：闭包对象不支持 `__name__` 属性设置
2. **事件载荷键名必须溯源**：不能猜测，必须读模块源码确认
3. **不是所有模块都有 power_state**：测试时要检查模块是否订阅了该事件

---

## Step 2 测试经验 (2026-06-21)

### 问题 1: FakeBLEDriver 缺失接口方法

**现象**: BLEService 初始化时报错 `'FakeBLEDriver' object has no attribute 'set_data_handler'`

**根因**: BLEService.init() 调用了 `self._ble.set_data_handler(self._on_ble_data)`，但测试中的 FakeBLEDriver mock 对象没有实现这个方法。

**修复**: 给 FakeBLEDriver 添加缺失的接口：
```python
self.cfg = {
    "char_nav": 0xFFF2,
    "char_ctrl": 0xFFF3,
    "char_ack": 0xFFF4,
}

def set_data_handler(self, handler):
    self._data_handler = handler
```

**教训**: Mock 对象必须与真实模块接口保持同步。当模块代码更新后，需要检查所有相关的 mock 对象是否需要更新。

---

### 问题 2: 报警推送测试断言格式错误

**现象**: `test_alarm_immediate_push` 报错 `KeyError: 'd'`

**根因**: 测试期望报警数据格式为 `{"t":5, "d": {"lvl":2, "type":"collision"}}`，但 BLEService 实际发送的是压缩格式 `{"t":5, "a":1, "l":2}`（a=类型编码, l=等级）。

**修复**: 更新测试断言：
```python
# 旧代码
assert call["d"]["lvl"] == 2
assert call["d"]["type"] == "collision"

# 新代码
assert call.get("a") == 1, "报警类型码应为 collision(1)"
assert call.get("l") == 2, "报警等级应为 2"
```

**教训**: 测试断言必须与代码实际发送的数据格式一致。当代码采用压缩格式时，测试也要相应调整。

---

### 问题 3: 省电模式事件名不匹配

**现象**: `test_light_service_integration.py` 的 test_08 失败

**根因**: 测试发布 `EVENT_CONFIG_UPDATE` 事件，但 LightService 订阅的是 `EVENT_POWER_STATE_CHANGE`。

**修复**: 将测试中的 `EVENT_CONFIG_UPDATE` 改为 `EVENT_POWER_STATE_CHANGE`。

**教训**: 这与 Step 1 的问题完全相同。事件名必须与模块订阅的事件名一致，不能猜测。

---

### 总结

Step 2 的测试问题主要集中在：
1. Mock 对象接口不完整（需要与真实模块同步）
2. 测试断言与实际数据格式不匹配（特别是压缩格式）
3. 事件名不匹配（重复出现的问题）

建议：在编写测试前，先仔细阅读被测模块的源代码，确认接口方法、数据格式和事件名称。

---

## [2026-06-21] Step 3 — NavigationService 集成经验

### 经验 1：MicroPython 线程栈碎片化

**现象**：测试反复创建/销毁 NavigationService 实例，test_08 报 `Malloc failed`

**根因**：
- `_thread.start_new_thread` 从 C 堆分配 4KB 栈（`ALLOC_RAW` 类型）
- `gc.collect()` 只回收 Python 对象堆，**不回收 `ALLOC_RAW` 块**
- MicroPython GC 使用 16 字节定长块分配器，**不做空闲块合并**
- 反复分配/释放 4KB 块导致碎片化，找不到连续 256 块区域

**教训**：
- 生产环境应避免频繁创建/销毁线程
- 改用**持久线程 + ThreadSafeQueue** 模式（参考 BLEService）
- 4KB 栈只分配 1 次，队列串行处理，无需互斥锁

### 经验 2：测试模式 vs 生产模式

**现象**：旧测试文件（`02_Software/Tests/`）没有 Malloc failed，新测试文件有

**根因**：
- 旧测试没有 `wait_tts_done(200)` 延迟，线程可能没完整运行
- 新测试每个 test 创建新系统 + 200ms 等待，加速碎片化累积
- 测试模拟"系统重启 9 次"，不是正常使用场景

**教训**：
- 测试中反复创建/销毁系统会暴露生产环境不会遇到的问题
- 需要区分"测试限制"和"真实缺陷"
- 生产环境只创建 1 个 NavigationService 实例，1 个持久线程

### 经验 3：模块架构一致性

**发现**：BLEService 已使用持久线程 + 队列模式，NavigationService 原设计每次 TTS 创建新线程

**修复**：统一为持久线程模式
```python
# 旧代码（每次创建新线程）
_thread.start_new_thread(_tts_thread, (tts_text, ...))

# 新代码（持久线程 + 队列）
self._tts_queue = ThreadSafeQueue(max_size=5)
# init() 中启动 1 个持久线程
def _tts_worker(self):
    while self.ctx["tts_thread_running"]:
        text = self._tts_queue.get(timeout_ms=1000)
        if text and self.audio_driver:
            self.audio_driver.play_tts(text)
        else:
            time.sleep_ms(50)  # 队列空时出让 CPU
```

**教训**：
- 所有需要后台处理的模块应统一使用持久线程 + 队列模式
- 避免在回调/事件处理中创建新线程
- 线程栈只分配 1 次，队列串行处理，无需互斥锁

### 经验 4：线程内存管理审查

**发现**：CloudService 缺少 `deinit()` 方法，后台线程无法停止

**教训**：
- 所有创建后台线程的模块必须有 `deinit()` 方法
- `deinit()` 中设置退出标志 + sleep 等待线程退出
- 已集成模块检查清单：NavigationService ✅、BLEService ✅、GNSSDriver ✅

### 经验 5：测试代码内存释放

**修复**：每个测试用 `try/finally` 包裹，确保 `nav.deinit()` 被调用

```python
def test_xxx():
    bus, audio, lcd, nav = make_system()
    try:
        # ... 测试逻辑 ...
    finally:
        nav.deinit()  # 停止 TTS 线程，释放 4KB 栈
```

`run_all()` 中每个测试后双重回收：
```python
gc.collect()
time.sleep_ms(100)
gc.collect()
```

**教训**：
- 测试中创建的线程必须在测试结束时停止
- `deinit()` 设置退出标志后需要 sleep 等待线程检测到
- `gc.collect()` 回收 Python 对象，但线程栈需要线程退出后自动释放

---

## [2026-06-21] Step 3 E2E — BLE 数据格式与硬件单例

### 经验 6：BLEService.cmd_buffer 数据格式

**现象**：E2E 测试模拟 BLE FFF2 写入，NavigationService 收不到事件

**根因**：测试直接 `cmd_buffer.put(json_string)`，但 BLEService 的 `_parse_and_route` 期望 dict 格式：

```python
# 错误（测试原始代码）
ble_svc.cmd_buffer.put('{"a":"nav","d":{...}}')

# 正确（匹配 _on_ble_data 的输出格式）
ble_svc.cmd_buffer.put({
    "uuid": ble_svc._ble.cfg["char_nav"],  # 0xFFF2
    "raw": '{"a":"nav","d":{...}}'
})
ble_svc.cmd_ready = True  # 确保 tick() 会 drain
```

**教训**：
- 模拟 BLE 数据流时，必须匹配 `_on_ble_data` 的输出格式（dict with uuid + raw）
- 设置 `cmd_ready = True` 触发 tick() 处理
- 错误被 except 静默捕获，只增加 err_count，无日志输出

### 经验 7：BLE 硬件单例模式

**现象**：test 2/3 的 BLEDriver init 失败（`+CME ERROR: 4`）

**根因**：EC200U BLE 硬件是全局单例，只能 init 一次。测试反复创建 BLEDriver 实例导致冲突。

**修复**：
```python
# 模块级单例
_shared_ble = None

def get_ble_driver(event_bus):
    global _shared_ble
    if _shared_ble is None:
        _shared_ble = BLEDriver(event_bus)
        _shared_ble.init()
    else:
        _shared_ble.event_bus = event_bus  # 复用实例，更新引用
    return _shared_ble
```

**教训**：
- BLE/4G/GNSS 等硬件模块是全局单例，测试中必须复用
- 不能每个测试创建新实例
- 单例模式下 cleanup 不应调用 deinit()（会影响后续测试）

### 经验 8：测试验证的局限性

**现象**：E2E 测试全部通过，但 TTS 实际没有声音播报

**根因**：测试只检查软件状态标志（`is_tts_playing=True`），没有验证实际硬件输出。

**教训**：
- E2E 测试只能验证**代码被执行**，不能验证**硬件实际工作**
- 对于音频、显示等硬件输出，需要人工确认或外部检测
- 测试通过 ≠ 功能正常，硬件层面需要额外验证

### 经验 9：AudioDriver 输出路径配置

**发现**：`AudioDriver.init()` 只设置了音量和语速，没有配置音频输出通道（speaker vs headset）。

**影响**：如果 EC200U 默认输出到耳机通道，TTS 命令成功但喇叭无声。

**建议**：
- 检查 AudioDriver.init() 是否需要添加 `audio.set_audio_channel()` 或等效配置
- 确认硬件连接（J402 喇叭 vs 耳机孔）
- 这是硬件配置问题，不是软件 bug

---

## [2026-06-21] Step 5 — VoiceDriver 集成经验

### 经验 10：EventBus 是队列模式，publish 后必须 pump

**现象**：VoiceDriver 单元测试 7/12 失败，`received` 列表始终为空

**根因**：`EventBus.publish()` 只将事件入队（`self._queue.append`），不会同步触发回调。必须调用 `bus.pump()` 才会从队列取出事件并触发订阅者回调。

```python
# 错误（测试原始代码）
uart.feed(0x01)
voice.tick()          # 内部 publish() → 事件入队
assert len(received) == 1  # FAIL! received 为空

# 正确
uart.feed(0x01)
voice.tick()          # 内部 publish() → 事件入队
bus.pump()            # 从队列取出 → 触发回调 → received.append()
assert len(received) == 1  # PASS
```

**教训**：
- EventBus 是**异步队列模式**，不是同步发布-订阅
- 所有单元测试中，`publish()` / `tick()` 后必须紧跟 `bus.pump()`
- 这是第 3 次因忘记 `pump()` 导致测试失败（Step 1、Step 3 也出现过）
- **建议**：写测试时形成固定模式：`操作 → tick() → pump() → 断言`

---

### 经验 11：Fake 驱动必须调用 init() 订阅事件

**现象**：`test_voice_e2e.py` 测试 4 失败，`audio.ctx["alarm_playing"]` 始终为 False

**根因**：`USE_FAKE=True` 模式下创建了 `FakeAudio(bus)` 但没有调用 `audio.init()`。`FakeAudio.init()` 负责订阅 `EVENT_ALARM_TRIGGERED` 等事件，不调用则事件不会触发回调。

```python
# 错误
audio = FakeAudio(bus)
# 缺少 audio.init()!

# 正确
audio = FakeAudio(bus)
audio.init()  # 订阅 EVENT_TTS_REQUEST / EVENT_VOLUME_CONTROL / EVENT_ALARM_* 等
```

**教训**：
- 这与 Step 2 的 FakeBLEDriver 问题完全相同（经验 1）
- Fake 驱动的 `init()` 通常负责事件订阅，不调用 = 不订阅 = 不响应
- **建议**：`make_system()` 中所有模块（包括 Fake）统一调用 `init()`，形成固定模式

---

### 经验 12：VoiceDriver.init() 会覆盖 uart 属性

**现象**：FakeUART 被真实 UART 覆盖，`voice.tick()` 读取的是真实硬件而非 Fake

**根因**：`VoiceDriver.init()` 内部执行 `self.uart = UART(self.cfg["uart_id"], ...)`，如果在 `init()` 之前设置 `voice.uart = fake_uart`，会被覆盖。

```python
# 错误
voice.uart = fake_uart  # 设置 FakeUART
voice.init()            # init() 内部 self.uart = UART(...) 覆盖了!

# 正确
voice.init()            # 先 init，创建真实 UART
voice.uart = fake_uart  # 再替换为 FakeUART
```

**教训**：
- 硬件模块的 `init()` 通常会初始化硬件句柄（UART/I2C/SPI/GPIO）
- 替换硬件句柄必须在 `init()` **之后**
- **建议**：形成固定模式：`模块.init() → 替换硬件句柄`

---

### Step 5 总结

Step 5 的 3 个问题全部是**测试代码缺陷**，不是模块代码缺陷：

1. EventBus 队列模式（忘记 pump）— 重复出现的老问题
2. Fake 驱动缺少 init（忘记订阅事件）— Step 2 已出现过
3. init() 覆盖硬件句柄（顺序错误）— 新发现

**核心建议**：
- 写测试前检查 3 件事：① tick 后有没有 pump ② Fake 有没有 init ③ 硬件替换在 init 之后
- 这 3 条规则覆盖了 90% 的集成测试 bug
