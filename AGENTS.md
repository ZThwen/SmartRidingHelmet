# SmartRidingHelmet — Agent 工作指南

> 本文件为 OpenCode (oh-my-openagent) 在此仓库工作时的行为准则和知识参考。
> 适用于所有 AI Agent。任何 Agent 在本仓库工作前必须阅读。

---

## 1. 项目简介

**智能骑行头盔** — MicroPython 固件（STM32F413ZH + Quectel EC200U 4G/GNSS/BLE）
+ 微信小程序 companion app（BLE 直连） + ConnectLab MQTT 云连接。

**无 PC 构建/检查/测试环境** — 嵌入式 MicroPython 项目。没有 pip/pytest/linter。
`python 02_Software/Tests/test_xxx.py` 仅做语法检查。**测试必须通过 Thonny IDE 上传到 NUCLEO-F413ZH 板子运行。**

---

## 2. 开始工作前必须阅读

1. 知识库：`D:\ObsidianVault\KNOWLEDGE_BASE_GUIDE.md` → `_index.md` → `project-index.md`
   - ⛔ **禁止**读取 `D:\ObsidianVault\raw/`（原始网页剪辑，token 太贵）
2. 关键设计文档：`00_Planning/01_architecture.md`、`00_Planning/00_requestment.md`
3. 硬件手册：`00_Planning/doc/`（EC200U 数据手册、API 手册）
4. SDK 参考：`examples/`（36 个 Quectel MicroPython 参考脚本）
5. 模块实现文档：`02_Software/Modules/doc/`
6. 测试指南：`02_Software/Tests/测试指南.md`

---

## 3. 架构总览

### 3.1 四层架构

```
App (02_Software/core/) → Services (02_Software/Modules/) → Device (02_Software/Drivers/) → Vendor (machine, quectel) — 只读固件
```

- **单向依赖**：上层只能调用下层，下层绝对不能调用上层
- **模块隔离**：Service 层模块间禁止直接调用，必须通过 `EventBus.publish()` / `subscribe()`
- **状态封装**：禁止全局变量，状态封装在模块对象的 `self._data` / `self.ctx` 中
- **Vendor 只读**：移远提供的 MicroPython 固件，禁止修改

### 3.2 核心文件

| 文件 | 职责 |
|------|------|
| `02_Software/core/config.py` | 所有事件常量、阈值、引脚、时序、MQTT/Qth 凭据 |
| `02_Software/core/Event_Bus.py` | 发布/订阅 + 线程安全队列；`pump()` 在主循环中调用 |
| `02_Software/core/Base_Module.py` | 四元组基类：`cfg`/`ctx`/`_data` + `init()`/`tick()`/`get_data()`/`get_status()` |
| `02_Software/core/main.py` | 初始化顺序 + 主循环（`tick` → `pump` → `sleep_ms(10)`） |

### 3.3 模块契约

所有模块必须实现：

| 接口 | 用途 | 调用时机 | 说明 |
|------|------|----------|------|
| `init()` | 初始化硬件 | 系统启动时按顺序调用 | 失败抛异常，main.py 捕获 |
| `tick()` | 周期调度 | 主循环每轮调用 | **必须 <5ms 返回**，不能阻塞 |
| `get_data()` | 获取数据 | 外部读取数据时 | 返回数据快照，外部只读 |
| `get_status()` | 获取状态 | 调试和监控时 | 返回运行状态快照 |

模板：`02_Software/Module_Template.py`（Drivers）、`02_Software/Service_Template.py`（Services）

### 3.4 初始化顺序（必须严格遵守）

```
1. 传感器: Temp_Humid → IMU → GNSS → Light
2. 执行器: Button → LED → Audio → LCD
3. 服务: CollisionService → AlarmService → CloudService → DisplayService
```

v2 新增（已实现但未集成 main.py）：
- PWM_LED: 在 LCD 之后
- LightService: 在 PWM_LED 之后
- ControlService: 在 DisplayService 之后
- NavigationService: 在 ControlService 之后

**注意**：Network/MQTT 不是独立模块，是 CloudService 内部创建的。BLE 未集成 main.py。

---

## 4. 关键设计约束

### 4.1 架构规则

| 规则 | 说明 |
|------|------|
| tick() < 5ms | 必须用 `ticks_diff` 守卫，禁止 `time.sleep()` |
| 禁止跨层调用 | Service → Device → Vendor，单向 |
| 禁止模块间直接调用 | 必须通过 EventBus |
| 禁止硬编码事件字符串 | 所有事件名在 `02_Software/core/config.py` 中定义为 `EVENT_UPPER_SNAKE_CASE` |
| 禁止全局变量 | 状态封装在 `self._data` / `self.ctx` |

### 4.2 BLE 协议约束

| 约束 | 说明 |
|------|------|
| ATT_MTU 限制 | 默认 MTU=23，可用载荷=20 字节。协商后可达 247（payload 244 字节） |
| 载荷压缩 | 所有 BLE payload 必须 ≤244 字节（ATT_MTU - 3） |
| 压缩格式 | 短字段名 + 数字编码：`{"t":7,"m":1,"b":50,"v":5,"p":0}`（控制状态） |
| 回调快速返回 | BLE 回调只写 ring buffer（`cmd_buffer.put` + `cmd_ready=True`），不做 JSON 解析 |
| EventBus 膨胀 | `EventBus.publish()` 自动注入 source/timestamp，BLE 转发时需剥离 |
| 报警压缩 | t=5 报警：`{"t":5,"a":1,"l":2}`（15 字节），`a`=类型编码，`l`=级别 |

**BLE GATT 特征值**：
- FFF0: 主服务 UUID
- FFF1: 头盔数据通道 (NOTIFY) — 传感器合并数据
- FFF2: 导航指令通道 (WRITE) — 手机→头盔导航
- FFF3: 骑行控制通道 (WRITE) — 手机→头盔控制
- FFF4: 报警确认通道 (WRITE) — 手机→头盔报警确认

### 4.3 电源模式

| 模式 | 传感器行为 | 说明 |
|------|-----------|------|
| ACTIVE | 全部正常采样 | 默认模式 |
| SUSPENDED | TempHumid 30s, LightSensor→2s/停止, GNSS 10s | 省电 |
| EMERGENCY | TempHumid 停止, LightSensor→2s/停止, GNSS 10s | 超级省电 |
| CUSTOM | ControlService 管理 | 手动操作覆盖省电模式（如单独开灯/调音量） |

### 4.4 报警系统

- **碰撞报警**：30s 自动取消（Level 1-2），Level 3 升级为 SOS
- **SOS 报警**：手动取消（无自动超时）
- **静默报警**：无 LED 无声音，仅 BLE 通知手机
- **TTS 优先级**：报警音频 > TTS；AudioDriver 在 `alarm_playing=True` 时拒绝 TTS

### 4.5 双线程架构

网络服务（BLEService、CloudService）使用双线程：
- **主线程**：收事件 → 缓存 → `tick()` 拼装 JSON → `send_queue.put()`
- **后台线程**：`send_queue.get()` → 硬件发送
- **绝不阻塞主循环**

---

## 5. 硬件参考

### 5.1 引脚映射

| 组件 | 接口 | 详情 |
|------|------|------|
| AHT20 (温湿度) | I2C1, addr 0x38 | S502 → ARDU |
| LIS2DH12TR (IMU) | I2C1, addr 0x19 | S502 → ARDU |
| GNSS | EC200U 内置 | 被动天线 |
| LBS (基站定位) | EC200U 内置 | 与 GNSS 互斥，室内定位 |
| Light (GL5528) | ADC PC5 | `read_u16()` → 0–65535 |
| Button | GPIO `'SW'` | PULL_DOWN + IRQ_RISING. Hw: ext pull-up + falling — verify. Debounce 50ms |
| LED (`LED_BLUE`) | GPIO D3 active-high | Timer1-driven blink |
| LCD (ST7735) | SPI1, dc=F12, cs=D14 | `display_mode` lock: alarm blocks `show_normal_data()` until `clear()` |
| Audio | EC200U audio | speaker J402, 8Ω/800mW |
| BLE | EC200U 内置 BLE 4.2 | GATT Server, 广播名 `SmartHelmet-66ccff` |
| PWM_LED | PE11, TIM1_CH2 | PWM 调光大功率灯 |
| Voice (ASRPRO) | UART | 语音指令识别，19 hex 映射 |

### 5.2 重要引脚命名规则

- STM32 引脚名：`Pin('PE11')`（不是 Arduino 名 `Pin('D5')`）
- PWM 输出需要 `Pin.OUT`：`Pin('PE11', Pin.OUT, Pin.PULL_NONE)`
- 移植代码前先在 REPL 里验证引脚名 + Timer 组合

---

## 6. 导入规则

| 上下文 | 模式 | 原因 |
|--------|------|------|
| Tests (全部) | `from core.X import Y` | 从 `02_Software/` 目录运行 |
| Temp_Humid.py (仅此驱动) | `from X import Y` (无 `core.`) | 传统 — 上传到设备时工作 |
| 其他 Drivers (除 Temp_Humid) | `from core.X import Y` | 一致 |
| Network/MQTT drivers | `from Drivers.network.X import Y` | 设备层路径 |
| main.py, 集成测试 | `sys.path.append("..")` 然后直接 import | 从 `02_Software/core/` 或 `Tests/` 子目录运行 |
| 导入 drivers | `from Drivers.sensor.X import Y` | 设备层路径 |

外部依赖：`ahtx0` 库（Temp_Humid.py 使用）

---

## 7. 代码风格

- **模块/文档语言**：中文（匹配现有代码库）
- **文档格式**：`brief`/`param`/`return`/`note` 多行格式 — 新模块前先检查 2-3 个现有模块
- **模块模板**：Drivers 用 `02_Software/Module_Template.py`，Services 用 `02_Software/Service_Template.py`
- **模块名**：`name` 字段使用 `UPPER_SNAKE_CASE` 字符串标识
- **事件命名**：`EVENT_UPPER_SNAKE_CASE`，模块前缀（如 `EVENT_TEMP_HUMID_READY`、`EVENT_GPS_LOST`）

---

## 8. 测试规范

### 8.1 命名约定

| 文件名模式 | 说明 |
|-----------|------|
| `test_xxx.py` | 单模块测试 |
| `test_xxx_integration.py` | 带 EventBus + 主循环 |
| `test_xxx_e2e.py` | 全系统端到端（真实硬件 + 网络） |
| `test_xxx_unit.py` | 单元测试（无硬件，假数据） |

### 8.2 关键约束

- **测试只能在设备上运行** — 不要在 PC 上执行 `python Tests/test_xxx.py`
- **禁止 `time.sleep()`** — 所有等待用泵循环：`tick() + event_bus.pump() + sleep_ms(50)`
- **E2E 测试必须交互式** — 每个场景前用 `input()` 暂停，显示要发送的 JSON 指令和预期结果
- **泵循环标准**：`while ticks_diff(end, ticks_ms()) > 0: mod.tick(); bus.pump(); sleep_ms(100)`
- **集成测试连续发送指令** — 必须重置防抖：`ctrl.ctx["last_cmd_tick"] = 0`

详细测试指南：`02_Software/Tests/测试指南.md`

---

## 9. 开发工作流

### 9.1 Git 提交规范

使用 Conventional Commits 格式：

```
type(scope): description

[可选 body]

[可选 footer]
```

**类型**：
| 类型 | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(control): add voice command mapping` |
| `fix` | Bug 修复 | `fix(ble): strip EventBus auto-injected fields` |
| `docs` | 文档更新 | `docs: update test guide inventory` |
| `chore` | 维护任务 | `chore(thonny): sync ble_service` |
| `test` | 测试相关 | `test(control): add BLE E2E v2 test` |
| `refactor` | 重构 | `refactor(alarm): extract _start_alarm method` |

**范围**（可选）：`ble`、`control`、`miniprogram`、`thonny`、`test`、`config`、`main`、`audio`、`light`、`alarm`、`navigation`

### 9.2 Worktree 纪律

- 创建 worktree 前必须检查 main 最新提交：`git log --oneline -5`
- 创建 worktree 后必须检查差异：`git diff main -- <file>`
- 不要污染 main 分支

### 9.3 文档同步流程

修改模块时必须同步更新：
1. 模块实现文档：`02_Software/Modules/doc/`以及`00_Planning/02_Design _scheme.md`
2. 测试指南：`02_Software/Tests/测试指南.md`（新测试文件）
3. 架构文档：`00_Planning/01_architecture.md`（事件表、init 顺序）
4. AGENTS.md（本文件，如涉及架构变更）

### 9.4 Thonny 同步规则

同步 thonny 文件时必须：
1. 从源码派生（不是直接复制）
2. 去掉 docstring、注释
3. f-string 转为 `%` 格式
4. 每次修改源码后重新同步 + 瘦身

---

## 10. Skill 调用规范

### 10.1 何时使用 Skill

| 场景 | 推荐 Skill |
|------|-----------|
| 开始新的创意功能（feature/component） | `/brainstorming` |
| 遇到 Bug 或测试失败 | `/systematic-debugging` 或 `/diagnose` |
| 需要理解代码库结构 | `/Explore Codebase` |
| 重构代码 | `/Refactor Safely` |
| 代码审查 | `/review-changes` 或 `/requesting-code-review` |
| 测试驱动开发 | `/tdd` |
| 安全审查 | `/security-research` |
| 调试复杂问题（2 次失败后） | `/Debug Issue` |

### 10.2 Skill 优先级

**用户安装的 Skill 优先于内置 Skill。** 域匹配时优先使用用户 Skill。

### 10.3 不需要 Skill 的情况

- 简单的单文件修改
- 明确的文件查找/读取
- Git 操作（用 `/git-master`）
- 已知的模式匹配

---

## 11. MCP 工作流

| MCP | 用途 | 主要操作 |
|-----|------|----------|
| code-review-graph | 架构分析、影响评估 | `build_or_update_graph`, `get_architecture_overview`, `query_graph`, `get_impact_radius` |
| codegraph | 快速代码探索 | `codegraph_explore` (主), `codegraph_search`, `codegraph_node`, `codegraph_callers` |
| word-mcp-live | Word 文档操作 | `word_create_document`, `word_add_heading`, `word_add_paragraph`, `word_add_table`, `word_convert_to_pdf` |
| syslab | Julia/MATLAB 交互 | `syslab_evaluate_julia_code`, `syslab_run_julia_file` |
| codebase-memory-mcp | 仓库索引、语义搜索 | `index_repository`, `search_code`, `query_graph`, `trace_path`, `get_architecture` |

---

## 12. Agent Lessons（经验教训）

### 12.1 架构与设计

- **禁止自订阅事件导致状态回推时序错误** — ControlService 订阅自己发布的事件来更新 `_control_state`，但 `_push_state()` 在事件泵处理之前就发送了快照。解决：直接在 `_execute_cmd` 中更新状态，不通过事件
- **重写模块时不要丢失已有方法** — 重写 alarm_service.py 时意外删除了公开的 `cancel_alarm()` 方法。重写前必须 diff 已有代码
- **覆盖状态前必须先清理** — `trigger_stealth_alarm()` 直接覆盖 `alarm_active` 等状态，但没调用 `_cancel_alarm()` 停止已有报警。静默报警前必须先取消已有报警
- **复制粘贴后检查重复代码** — navigation_service.py 出现了两个连续的 `return`
- **lambda 引用的方法必须存在** — `_cmd_handlers` 中的 `lambda: self._pub(...)` 引用了 `_pub` 方法，但该方法从未定义

### 12.2 BLE & 通信

- **密集指令用快照合并避免队列爆炸** — BLEService._on_control_state 更新 `_ctrl_snapshot`（不直接入队），tick 周期统一推送 1 条合并消息
- **BLE 类名是 BLEDriver 不是 BLE** — `Drivers/network/BLE.py` 中的类名是 `BLEDriver`
- **BLEService 构造函数需要 ble_driver 参数** — `BLEService(event_bus)` 不够，必须 `BLEService(event_bus, ble_driver=ble_driver)`
- **BLE 连接后不要立即推送大数据** — 手机需要时间完成 CCCD 订阅
- **ControlService._push_state 合并为 1 条消息** — 原 3 条（t=7 + t=8 + t=9）改为 1 条 `{"t":7,"m":1,"b":50,"v":5,"p":0}`

### 12.3 硬件

- **先读本地 PDF 和文档** — `00_Planning/doc/` 有真实的 API 手册，不要从网页搜索或凭假设推断
- **GNSS `get_location()` 返回 `cog` 字段** — 对地航向，0-360 度，北为 0
- **腾讯地图 polyline 是前向差分编码** — 格式：`[lat1, lng1, delta_lat2, delta_lng2, ...]`
- **腾讯地图骑行 API 不返回 `action` 字段** — 方向信息在 `act_desc` 字段
- **不要猜测 API 返回格式，先查官方文档** — 多次错误修改 `_decodePolyline` 都是因为没查文档
- **音频播放失败不阻塞系统** — `play_file("SD:sos.mp3")` 返回 -3（文件不存在），但 try/except 会捕获并打印错误

### 12.4 Git & 工作流

- **移植外部代码必须逐项审查** — 检查：import 路径、config 常量、方法是否存在、引脚命名、Pin 模式

### 12.5 常见陷阱

- **不能读取图片** — 截图必须替换为终端文本输出
- **类名 typo 会传播到所有测试 import** — 修复源码 + 所有测试文件
- **TTS 常量必须在 AlarmService 导入前定义** — 检查 Service 模块的 import 列表
- **`data-service.js` 和 `ws-client.js` 是历史参考** — 当前未被 index.js 引用
- **微信 WXML 模板中不要做数组操作** — `.concat()` 导致地图组件不渲染 polyline
- **WeChat `onBLECharacteristicValueChange` 监听所有特征值变化** — 必须过滤 `res.characteristicId`
- **catch 块捕获的不一定是 JSON.parse 错误** — `ReferenceError` 也会被 catch 捕获

### 12.6 Phase 3 远端控制经验

- **先读 MTU 限制文档再设计 BLE 协议** — 默认 MTU=23，可用载荷=20 字节，但协商后可达 247。先拆成 3 条（t=7/8/9），后发现 EventBus 自动注入字段导致超长，最终合并为 1 条
- **TTS 防抖需要考虑边界情况** — alarm_cancel 触发 TTS 后，紧接着 light_on 的 TTS 被 1 秒防抖阻塞。解决：在 _on_alarm_canceled 中直接调用 _tts()，绕过 _maybe_tts
- **小程序 UI 先验证再开发** — 12 个 fix 提交只修复 TabBar 适配问题。先在微信开发者工具中验证设计，再开发
- **MicroPython ≠ CPython** — __doc__ 属性在 MicroPython 中不存在，需要用 getattr(t, '__doc__', '') 替代
- **避免自订阅事件** — ControlService 订阅自己发布的事件导致时序混乱。直接在 _execute_cmd 中更新状态
- **状态快照需要考虑并发修改** — _pre_alarm_state 保存/恢复时状态可能已被修改。恢复后需推送 BLE
- **测试文件版本管理** — test_control_service.py 有 4 个版本，旧版本应及时归档
- **gitignore 应在项目初期配置** — thonny 目录之前被 git 跟踪，后来才加入 gitignore，导致删除后需要重新创建

---

## 13. 参考文档

| 文档 | 路径 |
|------|------|
| 架构设计 | `00_Planning/01_architecture.md` |
| PRD | `00_Planning/00_requestment.md` |
| 设计总体方案 | `00_Planning/02_Design _scheme.md`（注意 `_` 前有空格）|
| 模块实现文档 | `02_Software/Modules/doc/` |
| 硬件手册 | `00_Planning/doc/` |
| SDK 参考 | `examples/`（36 个 Quectel MicroPython 参考脚本）|
| 测试指南 | `02_Software/Tests/测试指南.md` |
| 小程序文档 | `02_Software/WeChatMiniProgram/doc/` |

---

## 14. 构建状态

| 层级 | 状态 | 位置 |
|------|------|------|
| Core (main, config, EventBus, BaseModule) | ✅ 完成 | `02_Software/core/` |
| Sensors (Temp_Humid, IMU, GNSS, Light) | ✅ 完成 | `02_Software/Drivers/sensor/` |
| Actuators (LED, Audio, LCD) | ✅ 完成 | `02_Software/Drivers/actuator/` |
| PWM_LED (PE11, TIM1_CH2) | ✅ 完成（未集成 main.py） | `02_Software/Drivers/actuator/PWM_LED.py` |
| Button | ✅ 完成 | `02_Software/Drivers/interface/` |
| Network, MQTT, BLE | ✅ 完成 | `02_Software/Drivers/network/` |
| Qth (Quectel Cloud SDK) | ⚠️ 已废弃 | `02_Software/Drivers/network/Qth.py` |
| Services (Collision, Alarm, Cloud, Display, BLE, Light, Control, Navigation) | ✅ 完成 (v1) | `02_Software/Modules/` |
| LarkCloudService (Quectel Cloud) | ⚠️ 已废弃 | `02_Software/Modules/lark_cloud.py` |
| LightService (自适应灯光) | ✅ 完成（已集成 main.py） | `02_Software/Modules/light_service.py` |
| ControlService (统一控制) | ✅ 完成（纯事件驱动，19 指令） | `02_Software/Modules/control_service.py` |
| NavigationService | ✅ 完成（已集成 main.py） | `02_Software/Modules/navigation_service.py` |
| main.py (21 模块集成) | ✅ v2 完成 | `02_Software/core/main.py` |
| PowerService (电源管理) | ✅ 完成（已集成 main.py） | `02_Software/Modules/power_service.py` |
| BatteryDriver (电池ADC) | ✅ 完成（已集成 main.py） | `02_Software/Drivers/sensor/Battery.py` |
| HeartRate | 📅 v2 计划（等硬件） | `02_Software/Drivers/sensor/HeartRate.py` |
| VoiceDriver (ASRPRO) | ✅ 完成（已集成 main.py） | `02_Software/Drivers/interface/Voice.py` |
| WeChatMiniProgram | Step A + Step B（导航+远端控制）完成 | `02_Software/WeChatMiniProgram/` |

**注意**：Network.py 和 MQTT.py 放在 `02_Software/Drivers/network/`（不是 `02_Software/Drivers/interface/`）。
