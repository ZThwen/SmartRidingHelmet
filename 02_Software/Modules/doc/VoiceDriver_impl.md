# VoiceDriver 实现文档

> **所属层次**：Device 层（接口驱动层）
> **实现状态**：✅ **已实现**（2026-06-20），待集成 main.py
> **负责人员**：张文杰

---

## 1. 模块概述

### 做什么
监听 ASRPRO 语音模块的 UART 串口，将接收到的 hex 字节映射为指令字符串，通过 `EVENT_VOICE_CMD` 发送给 ControlService 统一执行。

### 不是什么
- **不是**语音识别算法（ASRPRO 芯片负责）
- **不是**指令执行逻辑（ControlService 负责）
- **不是**TTS 播报（AudioDriver 负责，由 ControlService 统一调度）

### 一句话
**UART 轮询 + 查表映射的语音指令接收器**：轮询 UART → 读 hex → 查表 → 发布事件。

---

## 2. 文件位置

```
02_Software/Drivers/interface/Voice.py
```

---

## 3. 硬件接口

| 项目 | 值 | 说明 |
|------|-----|------|
| 语音芯片 | ASRPRO | 本地语音识别，不依赖云端 |
| 通信接口 | UART2 | EC200U UART2 |
| 波特率 | 9600 | 默认配置 |
| 数据格式 | 单字节 hex | 每条指令 1 字节（0x01-0x18） |
| 通信方向 | 单向 | ASRPRO → EC200U，无握手、无应答 |

---

## 4. 指令映射表（26 条）

映射表定义在 `config.py` 的 `VOICE_CMD_MAP` 字典中：

### 4.1 唤醒指令（1 条，新增）

| hex  | cmd    | 功能     | 中文语音 |
| ---- | ------ | -------- | -------- |
| 0x00 | `wake` | 唤醒指令 | "小洛包" |

### 4.2 控制指令（13 条）

| hex  | cmd               | 功能     | 中文语音                                 |
| ---- | ----------------- | -------- | ---------------------------------------- |
| 0x01 | `light_on`        | 开灯     | "开灯"/"打开灯"/"把灯打开"               |
| 0x02 | `light_off`       | 关灯     | "关灯"/"关掉灯"/"把灯关了"               |
| 0x03 | `brightness_up`   | 亮度+    | "调亮"/"把灯调亮"/"调高亮度"             |
| 0x04 | `brightness_down` | 亮度-    | "调暗"/"把灯调暗"/"调低亮度"             |
| 0x05 | `light_auto`      | 自动模式 | "自适应灯光"/"灯光自适应"/"自动亮暗"     |
| 0x06 | `volume_up`       | 音量+    | "调大音量"/"调高音量"/"音量调大"         |
| 0x07 | `volume_down`     | 音量-    | "调小音量"/"调低音量"/"音量调小"         |
| 0x08 | `alarm_cancel`    | 取消报警 | "取消报警"/"解除报警"/"关闭报警"         |
| 0x09 | `alarm_sos`       | SOS 报警 | **"请求救助"/"请求支援"/"请求救援"**     |
| 0x0A | `alarm_stealth`   | 静默报警 | "悄悄报警"/"后台报警"/"静默报警"         |
| 0x0B | `power_save`      | 省电模式 | "开启省电模式"/"打开省电模式"            |
| 0x0C | `power_normal`    | 正常模式 | "正常模式"/"开启正常模式"/"打开正常模式" |
| 0x0D | `power_emergency` | 紧急省电 | "紧急省电"/"打开紧急省电"/"开启紧急省电" |
| 0x16 | `ble_connect` | 蓝牙连接 | "蓝牙连接"/"连接蓝牙”/“连接" |
| 0x17 | `ble_disconnect` | 蓝牙断开 | "蓝牙断开"/"断开蓝牙“/”断开" |

### 4.3 查询指令（6 条）

| hex  | cmd              | 功能     | 中文语音                           |
| ---- | ---------------- | -------- | ---------------------------------- |
| 0x0E | `query_status`   | 查询状态 | "查询状态"/"状态查询"/"当前状态"   |
| 0x0F | `query_speed`    | 查询速度 | "查询速度"/"速度多少"/"当前速度"   |
| 0x10 | `query_temp`     | 查询温度 | "查询温度"/"温度多少"/"当前温度"   |
| 0x11 | `query_humid`    | 查询湿度 | "查询湿度"/"湿度多少"/"当前湿度"   |
| 0x12 | `query_location` | 查询位置 | "查询位置"/"经纬度多少"/"当前位置" |
| 0x13 | `query_battery` | 查询电量 | "查询电量"/"当前电量"/"电量多少"   |

### 4.4 休眠/闪烁指令（2 条，新增）

| hex  | cmd           | 功能       | 中文语音                         |
| ---- | ------------- | ---------- | -------------------------------- |
| 0x18 | `voice_sleep` | 语音休眠   | "退下"/"退下吧"/"吃小笼包去吧"   |
| 0x19 | `light_blink` | PWM灯光闪烁 | "闪烁"/"灯光闪烁"                |

### 4.5 映射关系说明

- VoiceDriver 只负责 hex → cmd 字符串的映射（查表）
- 映射后的 cmd 字符串通过 `EVENT_VOICE_CMD` 发送给 ControlService
- ControlService 统一执行（与 BLE 指令走同一个 `_execute_cmd` 入口）
- TTS 反馈由 ControlService 统一调度（VoiceDriver 不处理 TTS）

---

## 5. 事件发布

| 事件 | payload | 触发时机 |
|------|---------|----------|
| `EVENT_VOICE_CMD` | `{cmd: "light_on"}` | UART 收到有效 hex，查表成功 |

---

## 6. 四元组

```python
# cfg：静态配置
cfg = {
    "uart_id": 2,                # UART 总线编号
    "baudrate": 9600,            # 波特率
    "cmd_map": VOICE_CMD_MAP,    # 指令映射表（来自 config.py）
}

# ctx：运行时上下文
ctx = {
    "is_init": False,            # 初始化完成标志
    "err_count": 0,              # 错误计数
}

# _data：当前数据
_data = {
    "last_cmd": "",              # 最近一次指令字符串
    "last_hex": 0,               # 最近一次 hex 值
}
```

---

## 7. 实现逻辑

### 7.1 init()

```python
def init(self):
    self.uart = UART(self.cfg["uart_id"], self.cfg["baudrate"])
    self.ctx["is_init"] = True
```

- 创建 UART 实例
- 无事件订阅（VoiceDriver 是纯数据源，不订阅任何事件）

### 7.2 tick()

```python
def tick(self):
    if not self.uart:
        return
    try:
        if self.uart.any():
            data = self.uart.read(1)
            if data and len(data) > 0:
                hex_val = data[0]
                self._handle_hex(hex_val)
    except Exception as e:
        self.ctx["err_count"] += 1
```

### 7.3 _handle_hex(hex_val)

```python
def _handle_hex(self, hex_val):
    cmd = self.cfg["cmd_map"].get(hex_val)
    if cmd:
        self._data["last_cmd"] = cmd
        self._data["last_hex"] = hex_val
        if self.event_bus:
            self.event_bus.publish(EVENT_VOICE_CMD, {"cmd": cmd})
        print("[%s] 0x%02X -> %s" % (self.name, hex_val, cmd))
    else:
        print("[%s] unknown: 0x%02X" % (self.name, hex_val))
```

### 7.4 为什么用轮询而不用中断

| 维度 | 轮询（当前方案） | 中断（可选方案） |
|------|----------------|----------------|
| 实现复杂度 | 低 | 中（需注册回调） |
| 延迟 | < 10ms（tick 间隔） | < 1ms |
| 适用场景 | 语音间隔 1-2 秒 | 需要极低延迟 |
| 资源占用 | 极低（uart.any() 非阻塞） | 需要中断上下文 |

**当前方案足够**：语音指令间隔 1-2 秒（人类说话速度），UART 硬件 FIFO（16 字节）天然缓冲，tick 每 10ms 轮询一次，延迟 < 10ms，用户无感知。

---

## 8. 与 ControlService 的对接

### 8.1 数据流

```
ASRPRO 识别"开灯"
  → UART 发送 0x01
    → VoiceDriver.tick() 轮询到 uart.any() > 0
      → uart.read(1) → hex_val = 0x01
      → VOICE_CMD_MAP[0x01] → "light_on"
      → EventBus.publish(EVENT_VOICE_CMD, {cmd: "light_on"})
        → ControlService._on_voice_cmd()
          → _execute_cmd("light_on", source="voice")
            → handler() → publish(EVENT_LIGHT_CONTROL, {cmd: "on"})
            → _update_control_state()
            → _push_state() → 快照合并 → BLE notify 回推
            → _maybe_tts() → publish(EVENT_TTS_REQUEST, {text: "灯光已开启"})
```

### 8.2 统一执行入口

BLE 指令和语音指令最终汇聚到同一个方法：

```python
ControlService._execute_cmd(cmd, source="ble"/"voice")
```

区别仅在 `source` 参数，用于日志区分来源。执行逻辑、状态回推、TTS 反馈完全一致。

---

## 9. 约束规则

| 规则 | 说明 |
|:----|:-----|
| **tick() < 5ms** | `uart.any()` 和 `uart.read(1)` 都是非阻塞操作，单次 tick < 0.1ms |
| **手动操作永远优先** | 任何电源模式下都读取语音指令（功耗守卫在 tick 中不做限制） |
| **不处理 TTS** | TTS 由 ControlService 统一调度，VoiceDriver 只发事件 |
| **不处理执行逻辑** | VoiceDriver 只做 hex → cmd 映射，不判断指令是否合法 |
| **单向通信** | 不向 ASRPRO 发送任何数据，无握手、无应答 |

---

## 10. 测试状态

### 10.1 已测试通过

| 测试项 | 文件 | 结果 |
|:------|:-----|:----|
| 26 条 hex 映射正确性 | `test_voice_driver.py` | ✅ |
| 未知 hex 处理 | `test_voice_driver.py` | ✅ |
| UART 初始化 | `test_voice_driver.py` | ✅ |

### 10.2 待测试

| 测试项 | 优先级 | 说明 |
|:------|:-----:|:------|
| 集成测试（VoiceDriver + ControlService） | 高 | 验证 EVENT_VOICE_CMD → _execute_cmd 完整链路 |
| E2E 测试（语音 → 灯光/TTS） | 高 | ASRPRO 真机 → UART → 灯光响应 + TTS 播报 |
| 连续语音指令 | 中 | 快速连续说两条指令，验证防抖和执行顺序 |

---

## 11. 后续可调整

| 可调整项 | 原因 |
|:---------|:------|
| UART 波特率 | `cfg["baudrate"]` 随时可改，对齐 ASRPRO 配置 |
| 指令映射表 | `VOICE_CMD_MAP` 在 config.py 中集中管理，可扩展 |
| 改为中断驱动 | 如果语音响应速度不够，可改为 UART 中断 + 环形缓冲区 |
| 多字节协议 | 当前单字节 hex 最多支持 256 条指令，足够使用 |

---

## 12. ASRPRO 烧录参考

ASRPRO 语音识别芯片需要通过专用工具烧录语音指令模型，以下是烧录配置参考。

### 12.1 烧录工具

| 工具 | 说明 |
|:-----|:------|
| ASRPRO 上位机 | 天问 Block / 天问图形化编程软件 |
| 固件包 | 由语音模型训练生成，含识别网络和命令词表 |

### 12.2 UART 配置

ASRPRO 端 UART 参数需与 VoiceDriver 严格一致：

```c
// ASRPRO UART 配置
UART_Config uart = {
    .baudrate = 9600,
    .data_bits = UART_DATA_BITS_8,
    .stop_bits = UART_STOP_BITS_1,
    .parity = UART_PARITY_NONE,
    .tx_pin = UART2_TX,
    .rx_pin = UART2_RX,
};
```

### 12.3 指令编码映射

在 ASRPRO 固件中，每条语音指令必须按照下表分配固定的 hex 编码：

| hex 编号 | 语音指令 | 对应 cmd | 说明 |
|:--------:|:---------|:---------|:-----|
| 0x00     | "小浩包" | `wake` | 唤醒 |
| 0x01     | "开灯"/"打开灯"/"把灯打开" | `light_on` | 控制 |
| 0x02     | "关灯"/"关掉灯"/"把灯关了" | `light_off` | 控制 |
| ...      | ...      | ...      | ... |
| 0x18     | "休眠"/"去睡觉"/"休息吧" | `voice_sleep` | 休眠 |
| 0x19     | "闪烁"/"灯光闪烁" | `light_blink` | 闪烁 |

**重要**：ASRPRO 发送的 hex 值必须与 `config.py` 中 `VOICE_CMD_MAP` 字典的 key 完全一致（0x00–0x19），否则 VoiceDriver 查表失败。

### 12.4 烧录流程

1. 在天问 Block 中打开 ASRPRO 工程
2. 配置 UART2（9600, 8N1）
3. 为每条语音指令绑定对应的 hex 编码（0x00–0x19）
4. 编译生成固件 → 通过串口烧录至 ASRPRO 芯片
5. 烧录后通过串口调试助手验证：说出语音 → ASRPRO 发送对应 hex

### 12.5 注意事项

| 注意 | 说明 |
|:-----|:------|
| hex 一致性 | 烧录前必须与 `02_Software/core/config.py` 中的 `VOICE_CMD_MAP` 确认每个 hex 值一致 |
| 波特率匹配 | ASRPRO 和 EC200U UART2 的波特率必须相同（当前均为 9600） |
| 数据方向 | ASRPRO → EC200U（单向），ASRPRO 不接收数据 |
| 唤醒词检测 | 唤醒后 ASRPRO 才开始发送控制/查询指令，休眠后停止发送 |
