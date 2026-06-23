# 集成测试报告

> 每次上板测试后填写，归档到 `03_Integration/reports/`

## 基本信息
- **日期**：2026-06-21
- **测试人**：锦依卫队
- **测试文件**：`03_Integration/tests/wave0_baseline/test_system_base.py`
- **硬件状态**：NUCLEO-F413ZH + EC200U，4G/天线已接，BLE 未测试

## 测试结果
```
结果: 7 通过, 0 失败 / 共 7
ALL PASS
```

## 通过项清单
| 测试 | 验证点 | 结果 |
|------|--------|------|
| test_01_all_modules_init | 11 模块全部初始化成功，EVENT_SYSTEM_READY 已发布 | ✅ |
| test_02_sensor_data_events | 4 个传感器事件（TEMP_HUMID/IMU/GNSS/LIGHT）在 EventBus 正确传播 | ✅ |
| test_03_collision_alarm_chain | 碰撞检测→报警激活，alarm_active=True，EVENT_ALARM_TRIGGERED 已发布 | ✅ |
| test_04_alarm_cancel | 报警取消后 alarm_active=False，EVENT_ALARM_CANCELED 已发布，LCD 恢复正常画面 | ✅ |
| test_05_display_update | 传感器数据正确写入 DisplayService（temp/humid/lat/lon/speed/light） | ✅ |
| test_06_power_state_change | 10/10 模块正确切换到 SUSPENDED 省电状态 | ✅ |
| test_07_main_loop_performance | 100 轮 tick 全部 <5ms，总耗时 1130ms，平均 11.3ms/轮（含 10ms sleep） | ✅ |

## 失败项分析
| 测试 | 失败描述 | 根因 | 修复 |
|------|---------|------|------|
| （无） | — | — | — |

## 关键调试日志
```
GNSS init (首次): AT+QGPS=1 → OK
GNSS init (重入): AT+QGPS=1 → +CME ERROR: 504 (已运行，预期)
GNSS get_location: AT+QGPSLOC=2 → +CME ERROR: 516 (室内无卫星信号)

Audio init: AT+QAUDMOD=2 → OK, AT+CLVL=5 → OK, TTS 参数设置 OK
Audio play alarm: AT+QAUDPLAY="SD:alarm_l2.mp3",0 → +CME ERROR: 903 (SD卡文件缺失)
Audio TTS: AT+QTTS=1,"667A80FD...",0 → OK

LCD: SPI1 @ 20000000Hz, dc=F12, cs=D14 → OK
Display: 开机Logo加载失败: no module named 'images' (降级到文字模式)
Display: TTS播报: 智能骑行头盔已就绪

主循环: 100 轮, 总耗时 1130ms, 平均 11.3ms/轮, 所有 tick() < 5ms
```

## 硬件备注
- BLE 可发现：未测试
- GNSS 信号：无（室内测试）
- 4G 注册：未测试

## 待办
- [ ] 将 alarm_l1.mp3、alarm_l2.mp3 上传到 EC200U SD 卡
- [ ] 将 images/images1 图片资源模块上传到板子（可选，文字降级可用）
- [ ] 室外测试验证 GNSS 定位数据流
