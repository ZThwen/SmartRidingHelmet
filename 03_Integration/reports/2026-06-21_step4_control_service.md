# 集成测试报告

> 每次上板测试后填写，归档到 `03_Integration/reports/`

## 基本信息
- **日期**：2026-06-21
- **测试人**：锦依卫队
- **测试文件**：
  - `03_Integration/tests/wave2_service/test_control_service_integration.py`（ControlService 单元测试）
  - `03_Integration/tests/wave2_service/test_light_control_integration.py`（ControlService + LightService 联合）
  - `03_Integration/tests/wave3_communication/test_control_service_ble_e2e.py`（ControlService BLE E2E）
- **硬件状态**：NUCLEO-F413ZH + EC200U，BLE 已连接

## 测试结果
```
结果: 26 通过, 0 失败 / 共 26
ALL PASS
```

## 通过项清单

### ControlService 单元测试（13/13）
| 测试 | 验证点 | 结果 |
|------|--------|------|
| test_01_init_and_subscribe | 初始化成功，订阅 RIDE_CONTROL/VOICE_CMD/CONTROL_STATE_CHANGED | ✅ |
| test_02_light_on | light_on 指令 → EVENT_LIGHT_CONTROL 发布 | ✅ |
| test_03_light_off | light_off 指令 → EVENT_LIGHT_CONTROL 发布 | ✅ |
| test_04_brightness | brightness_up/down 指令正确 | ✅ |
| test_05_volume | volume_up/down 指令正确 | ✅ |
| test_06_alarm_sos | alarm_sos 指令 → EVENT_ALARM_CONTROL 发布 | ✅ |
| test_07_alarm_cancel | alarm_cancel 指令正确 | ✅ |
| test_08_power_save | power_save 指令 → EVENT_POWER_STATE_CHANGE 发布 | ✅ |
| test_09_power_normal | power_normal 指令正确 | ✅ |
| test_10_power_emergency | power_emergency 指令正确 | ✅ |
| test_11_query_status | query_status 指令 → EVENT_TTS_REQUEST 发布 | ✅ |
| test_12_state_snapshot_fields | 控制状态快照包含所有必要字段 | ✅ |
| test_13_continuous_commands | 连续发送 3 条指令无异常 | ✅ |

### ControlService + LightService 联合（9/9）
| 测试 | 验证点 | 结果 |
|------|--------|------|
| test_01_light_on | light_on → PWM duty=50, mode=manual | ✅ |
| test_02_light_off | light_off → PWM duty=0, mode=manual | ✅ |
| test_03_brightness_up | brightness_up: 30→35 (step=5) | ✅ |
| test_04_brightness_down | brightness_down: 30→25 (step=5) | ✅ |
| test_05_light_auto | light_auto → mode=auto, auto_mode=True | ✅ |
| test_06_auto_mode_dark | auto + 暗光(55000lux) → duty=50%, level=night | ✅ |
| test_07_auto_mode_bright | auto + 亮光(10000lux) → duty=0%, level=day | ✅ |
| test_08_state_snapshot_brightness | brightness 跟踪正确（on→down→auto） | ✅ |
| test_09_event_log_state_changed | 5 条指令均触发 STATE_CHANGED 事件 | ✅ |

### ControlService BLE E2E（4/4）
| 测试 | 验证点 | 结果 |
|------|--------|------|
| test_ble_e2e_01_light_on | FFF3 light_on → PWM duty=50, TTS "灯光已开启" | ✅ |
| test_ble_e2e_02_volume_up | FFF3 volume_up → 音量更新, TTS "音量增加" | ✅ |
| test_ble_e2e_03_query_temp | FFF3 query_temp → TTS 播报温度 | ✅ |
| test_ble_e2e_04_alarm_tts_suppress | stealth 报警期间 TTS 被抑制，取消后恢复 | ✅ |

## 失败项分析
| 测试 | 失败描述 | 根因 | 修复 |
|------|---------|------|------|
| （无） | — | — | — |

## 关键调试日志
```
=== ControlService 单元测试 ===
cmd=light_on/light_off/brightness_up/down/volume_up/down
cmd=alarm_sos/alarm_cancel
cmd=power_save/normal/emergency
cmd=query_status
全部 13 条指令验证通过

=== ControlService + LightService 联合 ===
light_on → manual mode, brightness=50, duty=50
light_off → manual mode, brightness=0, duty=0
brightness_up: 30→35 (step=5)
brightness_down: 30→25 (step=5)
light_auto → auto mode enabled
auto_dark: intensity=55000 → duty=50%, level=night
auto_bright: intensity=10000 → duty=0%, level=day

=== ControlService BLE E2E ===
BLE FFF3 → light_on → PWM duty=50 ✓
BLE FFF3 → volume_up → 音量 5→5 (已达上限) ✓
BLE FFF3 → query_temp → TTS 播报温度 ✓
stealth 报警 → TTS 抑制 → 取消后恢复 ✓
AT+QTTS 播报: 灯光已开启/音量增加/温度信息等
```

## 硬件备注
- BLE 可发现：是（SmartHelmet-66ccff）
- GNSS 信号：无（室内测试）
- 4G 注册：未测试

## 待办
- [ ] 推进全系统集成测试（16 模块 main.py）
- [ ] 推进小程序 BLE 联调
