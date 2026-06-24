# 集成测试报告 — Step 6 电池/电源管理

## 基本信息
- **日期**：2026-06-23
- **测试人**：锦依卫队
- **测试文件**：
  - `03_Integration/tests/step6_addition/test_power_battery.py`（BatteryDriver + PowerService 集成测试）
  - `02_Software/Tests/test_battery_e2e.py`（电池 ADC E2E 实测）
- **硬件状态**：NUCLEO-F413ZH + EC200U + 电源扩展板（锂电池 + 分压电路接 ADC1_IN14/PC4）

## 变更概述

本次集成新增 BatteryDriver + PowerService 模块，实现电池电压实时监控、6 档电量显示、低电量自动省电和 TTS 提醒。

### 新增模块
| 模块 | 文件 | 说明 |
|------|------|------|
| BatteryDriver | `Drivers/sensor/Battery.py` | ADC PC4 电压采集，6 档电量 |
| PowerService | `Modules/power_service.py` | 低电量自动省电 + TTS |

### 修改模块
| 模块 | 修改内容 |
|------|----------|
| config.py | 新增 EVENT_BATTERY_READY/LOW/CRITICAL、BATTERY_* 常量、TTS_BATTERY_LOW |
| main.py | 导入 + 初始化 BatteryDriver + PowerService（19→21 模块） |
| AudioDriver | `tick()` 移除 `power_state` 守卫，确保音频回调正常处理 |
| BatteryDriver | 新增 `sample_count` 字段，用于启动宽限期判断 |
| PowerService | 添加启动宽限期（`sample_count < 3` 不做省电决策）+ 未接电池阈值 500→1000 |
| ControlService | 订阅 `EVENT_POWER_STATE_CHANGE`，接收省电事件后回推状态到小程序 |

## 测试结果

### E2E 实测数据（15 秒连续监控）
```
[BAT] raw=55517 adc=2795mV battery=4052mV level=5
[BAT] raw=55533 adc=2796mV battery=4054mV level=5
[BAT] raw=54349 adc=2736mV battery=3967mV level=4
[BAT] raw=52604 adc=2648mV battery=3839mV level=4
[BAT] raw=51404 adc=2588mV battery=3752mV level=3
[BAT] raw=51276 adc=2581mV battery=3742mV level=3
[BAT] raw=49884 adc=2511mV battery=3640mV level=3
[BAT] raw=48411 adc=2437mV battery=3533mV level=2
[audio] power_state: ACTIVE -> SUSPENDED
[audio_service] PLAY: priority=2 text=当前电量不足，请及时充电
  [TTS] 当前电量不足，请及时充电
[BAT] raw=48011 adc=2417mV battery=3504mV level=2
[BAT] raw=46987 adc=2366mV battery=3430mV level=2

最终状态: level=2, battery_mv=3430, is_low=True, power_mode=SUSPENDED, auto_suspended=True
```

### 关键验证点
| # | 验证项 | 结果 |
|---|--------|------|
| 1 | ADC 读数正常（raw/adc_mv/battery_mv） | ✅ |
| 2 | 6 档电量映射正确（level 5→4→3→2） | ✅ |
| 3 | level≤2 时自动切换 SUSPENDED 模式 | ✅ |
| 4 | 低电量 TTS 播报"当前电量不足，请及时充电" | ✅ |
| 5 | AudioService 优先级调度（priority=2, CTRL） | ✅ |
| 6 | auto_suspended 防重复标记生效 | ✅ |
| 7 | BLE 推送含 bat 字段 | ✅ |

### 电压→档位映射实测
| ADC mV | 电池 mV | level | 说明 |
|--------|---------|-------|------|
| 2795 | 4052 | 5 | 满电 |
| 2736 | 3967 | 4 | 良好 |
| 2588 | 3752 | 3 | 中等 |
| 2437 | 3533 | 2 | 低电量 → 触发自动省电 |
| 2366 | 3430 | 2 | 低电量 → TTS 已播报 |

### 自动省电触发链路
```
BatteryDriver.tick() → ADC 读数 → EVENT_BATTERY_READY{level:2}
  → PowerService._on_battery() → level≤2 且 AUTO_SUSPENDED=False
    → EVENT_POWER_STATE_CHANGE{SUSPENDED}  ← 省电模式
    → EVENT_BATTERY_LOW{level:2}           ← 低电量事件
    → EVENT_TTS_REQUEST{text:"当前电量不足"} ← TTS 提醒
      → AudioService → AudioDriver.play_tts()
```

## 待办
- [ ] 上板运行 test_power_battery.py 集成测试（8 个用例）
- [ ] 验证 level=0（电池耗尽）行为
- [ ] 验证 EVENT_BATTERY_CRITICAL 事件（当前未发布）
- [ ] 验证 power_normal 恢复后传感器采样率恢复
- [ ] 验证 AudioDriver.tick() 移除 power_state 后回调处理正常
- [ ] 验证 ControlService 订阅 EVENT_POWER_STATE_CHANGE 后 BLE 回推正确
