# 集成测试报告

> 每次上板测试后填写，归档到 `03_Integration/reports/`

## 基本信息
- **日期**：2026-06-21
- **测试人**：锦依卫队
- **测试文件**：`03_Integration/tests/wave3_communication/test_navigation_service_ble_e2e.py`
- **硬件状态**：NUCLEO-F413ZH + EC200U，4G/天线已接，BLE 广播中

## 测试结果
```
结果: 3 通过, 0 失败 / 共 3
ALL PASS
```

## 通过项清单
| 测试 | 验证点 | 结果 |
|------|--------|------|
| test_ble_e2e_01_nav_right | BLE FFF2 写入 right 200m 中山路 → TTS "前方200米右转进入中山路" + LCD "> 200m 中山路" | ✅ |
| test_ble_e2e_02_full_ride | 完整骑行流程 4 步（right→straight→left→arrive）→ 每步 TTS + LCD 均正确 | ✅ |
| test_ble_e2e_03_alarm_suppress | stealth 报警期间导航 TTS 被抑制，取消报警后 TTS 恢复正常 | ✅ |

## 失败项分析
| 测试 | 失败描述 | 根因 | 修复 |
|------|---------|------|------|
| （无） | — | — | — |

## 关键调试日志
```
=== E2E 1: BLE FFF2 → 右转导航 ===
BLE init: SmartHelmet-66ccff | addr=65fb74ecf82c
FFF2 写入: right 200m 中山路
  TTS: 前方200米右转进入中山路 ✓
  LCD: > 200m 中山路 ✓
AT+QTTS=1,"524D65B90032003000307C7353F38F6C8FDB51654E2D5C718DEF",0 → OK

=== E2E 2: 完整骑行流程 ===
步骤1: right 500m 中山路 → TTS "前方500米右转进入中山路" + LCD "> 500m 中山路" ✓
步骤2: straight 200m → TTS "前方200米直行" + LCD "^ 200m" ✓
步骤3: left 300m 南京路 → TTS "前方300米左转进入南京路" + LCD "< 300m 南京路" ✓
步骤4: arrive → TTS "已到达目的地" + LCD "已到达" ✓

=== E2E 3: 报警抑制 TTS ===
阶段1: stealth 报警激活 → 导航数据更新但 TTS 被抑制（last_tts 为空）✓
阶段2: 报警取消 → TTS 恢复 "前方200米左转进入恢复路" ✓
```

## 硬件备注
- BLE 可发现：是（SmartHelmet-66ccff）
- GNSS 信号：无（室内测试）
- 4G 注册：未测试

## 待办
- [ ] 推进 ControlService 集成测试（BLE FFF3 控制指令）
- [ ] 推进全系统集成测试（Wave 4）
