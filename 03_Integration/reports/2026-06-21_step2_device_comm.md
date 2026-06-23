# 集成测试报告

> 每次上板测试后填写，归档到 `03_Integration/reports/`

## 基本信息
- **日期**：2026-06-21
- **测试人**：锦依卫队
- **测试文件**：
  - `03_Integration/tests/wave1_device/test_pwm_led_unit.py`
  - `03_Integration/tests/wave1_device/test_ble_driver_unit.py`
  - `03_Integration/tests/wave1_device/test_device_integration.py`
  - `02_Software/Tests/test_light_sensor_integration.py`
  - `03_Integration/tests/wave3_communication/test_ble_service_integration.py`
- **硬件状态**：NUCLEO-F413ZH + EC200U，4G/天线已接，BLE 已连接

## 测试结果
```
结果: 39 通过, 0 失败 / 共 39
ALL PASS
```

## 通过项清单

### PWM_LED 单模块（14/14）
| 测试 | 验证点 | 结果 |
|------|--------|------|
| 步骤1 | PWMLEDDriver init 成功（PE11, TIM1, CH2, 1000Hz） | ✅ |
| 步骤2 | is_init=True | ✅ |
| 步骤3 | set_brightness(50) duty=50 | ✅ |
| 步骤4 | set_brightness(0) duty=0 | ✅ |
| 步骤5 | set_brightness(100) duty=100 | ✅ |
| 步骤6 | 越界限幅：-10→0，200→100 | ✅ |
| 步骤7 | 连续 100 次 tick() 无异常 | ✅ |
| 步骤8 | get_data() 返回 duty_cycle=75, valid=True | ✅ |
| 步骤9 | get_status() 返回 is_init=True, is_busy=False, err_count=0, power=ACTIVE | ✅ |
| 步骤10 | SUSPENDED 状态占空比归零，恢复 ACTIVE 后 set_brightness(60) 正常 | ✅ |
| 步骤11 | deinit 后 is_init=False | ✅ |

### BLEDriver 单模块 MockBLE（8/8）
| 测试 | 验证点 | 结果 |
|------|--------|------|
| 测试1 | init() 成功，API 调用顺序正确（init→set_dataformat→start→add_service） | ✅ |
| 测试2 | 广播名称 SmartHelmet-66ccff | ✅ |
| 测试3 | GATT 服务 UUID=0xFFF0 | ✅ |
| 测试4 | 4 个特征值注册（FFF1/FFF2/FFF3/FFF4） | ✅ |
| 测试5 | notify_data() 发送通道 FFF1，未连接时静默跳过 | ✅ |
| 测试6 | EVENT_BLE_CONNECTED 已发布，is_connected=True | ✅ |
| 测试7 | EVENT_BLE_DISCONNECTED 已发布，is_connected=False | ✅ |
| 测试8 | get_data()/get_status() 返回值正确 | ✅ |

### Device 层集成 PWM+BLE+EventBus（6/6）
| 测试 | 验证点 | 结果 |
|------|--------|------|
| test_01 | PWM+BLE 同时初始化成功，BLE 广播名 SmartHelmet-66ccff，addr=20d59cb6049c | ✅ |
| test_02 | PWM tick 10 轮无异常 | ✅ |
| test_03 | BLE tick 10 轮无异常，power_state=ACTIVE | ✅ |
| test_04 | PWM+BLE 联合 30 轮无事件风暴 | ✅ |
| test_05 | PWM 通过 EVENT_CONFIG_UPDATE 接收亮度设置 | ✅ |
| test_06 | EVENT_POWER_STATE_CHANGE 切换到 SUSPENDED 成功 | ✅ |

### 光敏传感器模块（3/3）
| 测试 | 验证点 | 结果 |
|------|--------|------|
| 事件流转 | LIGHT_READY 事件正常发布，光照强度约 16500-16600 | ✅ |
| 连续采样 | 5 次采样全部成功 | ✅ |
| 配置更新 | POWER_STATE_CHANGE/LIGHT_CONTROL 订阅正常 | ✅ |

### BLEService（6/6）
| 测试 | 验证点 | 结果 |
|------|--------|------|
| 测试1 | 传感器数据合并推送（tmp/hum/lat/lon），t=0 格式 | ✅ |
| 测试2 | 报警触发立即推送（a=1 l=2），报警取消推送 | ✅ |
| 测试3 | BLE 断连时不发送数据 | ✅ |
| 测试3b | 断连后队列已清空 | ✅ |
| 测试4 | 心跳包正常（t=99） | ✅ |
| 测试5 | 队列满不阻塞主线程 | ✅ |

## 失败项分析
| 测试 | 失败描述 | 根因 | 修复 |
|------|---------|------|------|
| （无） | — | — | — |

## 关键调试日志
```
=== PWM_LED ===
init: pin=PE11, timer=1, channel=2, freq=1000Hz
set_brightness(50) → duty_cycle=50
set_brightness(-10) → 限幅为0, set_brightness(200) → 限幅为100
deinit: is_init=False

=== BLEDriver (真机) ===
init: SmartHelmet-66ccff | addr=20d59cb6049c
AT+QBTCFG="dataformat",2 → OK
AT+QBTPWR=1 → OK
AT+QBTNAME=0,"SmartHelmet-66ccff" → OK
AT+QBTGATADV=1,128,160,0,1,7,0 → OK
AT+QBTGATSS/SC/SCV/SCD → GATT 服务+4特征值全部 OK
AT+QBTGATSSC=1,1 → 启动广播
AT+QBTADV=1 → OK

=== BLEService ===
合并数据: tmp=25.3 hum=60.1 lat=31.23 lon=121.47
报警推送: a=1 l=2
心跳包: {'d': {'s': 'ok'}, 't': 99}
```

## 硬件备注
- BLE 可发现：是，广播名 SmartHelmet-66ccff，地址 20d59cb6049c
- GNSS 信号：无（室内测试）
- 4G 注册：未测试

## 待办
- [ ] 推进 Wave 2（LightService + ControlService）上板验证
- [ ] 室外测试验证 GNSS + BLE 数据合并推送
- [ ] 测试 BLE 连接后手机端接收 t=0 数据
