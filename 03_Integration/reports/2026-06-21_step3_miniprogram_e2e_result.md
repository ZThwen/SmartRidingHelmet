# Step 3 联动小程序 E2E 测试报告

> 日期：2026-06-21
> 测试环境：真实硬件 + 微信小程序
> 测试人员：用户

---

## 1. 测试环境

### 硬件配置
- 主控：NUCLEO-F413ZH + EC200U
- 传感器：AHT20 温湿度、LIS2DH12 IMU、GL5528 光照
- 执行器：ST7735 LCD、EC200U Audio (TTS)
- 通信：EC200U BLE 4.2

### 软件版本
- main.py：v2 Step 3（16 模块集成）
- 微信小程序：导航功能已完成

### 模块清单（16个）
- 传感器 (4)：TempHumid, IMU, GNSS, Light
- 执行器 (6)：Button, LED, Audio, LCD, PWM_LED, BLE
- 服务 (6)：Collision, Alarm, Display, LightService, BLEService, NavigationService

---

## 2. 测试结果汇总

| 场景 | 结果 | 备注 |
|------|------|------|
| 1. BLE 扫描与连接 | ✅ 通过 | 小程序成功连接 SmartHelmet-66ccff |
| 2. 传感器数据推送 | ✅ 通过 | FFF1 Notify 正常，小程序显示温湿度/光照 |
| 3. 导航指令下发 | ✅ 通过 | FFF2 Write 正常，TTS 播报 + LCD 显示 |
| 4. 导航中报警 | ✅ 通过 | 碰撞触发报警，导航暂停 |
| 5. 报警解除 | ✅ 通过 | 报警解除后导航恢复 |
| 6. 导航结束 | ✅ 通过 | cancel 指令正常，TTS "导航已结束" |

**总体结果**：✅ 全部通过

---

## 3. 关键验证点

### 3.1 BLE 连接
- ✅ 设备名：`SmartHelmet-66ccff`
- ✅ MTU 协商：247 bytes
- ✅ 连接地址：`65fb74ecf82c`
- ✅ FFF1 Notify：传感器数据正常推送
- ✅ FFF2 Write：导航指令正常接收

### 3.2 传感器数据推送 (FFF1)
- ✅ 数据格式：`{"t":0,"d":{"tmp":27.1,"hum":65.3,"lux":20100}}`
- ✅ 推送间隔：2 秒
- ✅ 心跳包：`{"t":99,"d":{"s":"ok"}}` 每 5 秒

### 3.3 导航指令 (FFF2)
- ✅ 指令格式：`{"a":"nav","d":{"dir":"right","dist":26,"road":""}}`
- ✅ TTS 播报：`前方26米右转`
- ✅ LCD 显示：`> 26m`
- ✅ 状态更新：`is_navigating: True, current_dir: right`

### 3.4 报警冲突处理
- ✅ 报警触发时导航暂停
- ✅ 报警解除后导航恢复
- ✅ LCD 显示切换正常

### 3.5 导航取消
- ✅ cancel 指令：`{"a":"nav","d":{"dir":"cancel","dist":0,"road":""}}`
- ✅ TTS 播报：`导航已结束`
- ✅ LCD 显示：`导航结束`
- ✅ 状态恢复：`is_navigating: False`

---

## 4. 发现的问题

### 4.1 性能问题（非功能性，后续优化）

**现象**：
```
⚠️ 真阻塞: [temp_humid] tick 耗时 82ms
⚠️ 真阻塞: [EventBus.pump] 耗时 84ms
🔴 警告: 主循环 CPU 忙碌时间 178ms
```

**影响**：
- 主循环 178ms，远超 10ms sleep 间隔
- 可能导致传感器数据丢失
- 实时性能差

**根因分析**：
1. `temp_humid` 阻塞 82ms：I2C 通信超时或传感器响应慢
2. `EventBus.pump` 阻塞 84ms：DisplayService 渲染或 BLEService 发送慢

**优化方向**：
- 检查 I2C 通信超时配置
- 优化 DisplayService 渲染逻辑
- 考虑将耗时操作移到后台线程

**优先级**：P2（功能性验证通过，性能后续优化）

---

## 5. 经验总结

### 5.1 BLE 协议验证
- ✅ 小程序与头盔的 BLE 通信协议完全匹配
- ✅ FFF1/FFF2 特征值工作正常
- ✅ JSON 数据格式一致

### 5.2 导航功能验证
- ✅ 小程序发送导航指令 → 头盔接收 → TTS 播报 → LCD 显示
- ✅ 完整链路验证通过
- ✅ 报警冲突处理正确

### 5.3 集成测试价值
- ✅ 单元测试无法验证的跨模块交互，在联动测试中发现
- ✅ 真实环境下的 BLE 通信稳定性得到验证
- ✅ 小程序与头盔的协同工作正常

### 5.4 性能监控价值
- ✅ 详细的性能监控帮助定位阻塞点
- ✅ 为后续性能优化提供数据支撑

---

## 6. 下一步

### Step 4：远端控制集成
- 集成 ControlService
- 实现 FFF3 控制指令（灯光、音量、电源模式等）
- 联动小程序控制页面测试

### 性能优化（P2）
- 分析 temp_humid 阻塞原因
- 优化 EventBus.pump 性能
- 考虑后台线程处理耗时操作

---

## 7. 附录

### 7.1 测试日志片段
```
[nav] 收到事件: {'source': 'unknown', 'raw': '{"a":"nav","d":{"dir":"right","dist":26,"road":""}'}
[nav] ▶ TTS: 前方26米右转
[nav] LCD: > 26m

[nav] 收到事件: {'source': 'unknown', 'raw': '{"a":"nav","d":{"dir":"cancel","dist":0,"road":""}'}
[nav] ▶ TTS: 导航已结束
[nav] LCD: 导航结束
```

### 7.2 模块状态快照
```json
{
  "ble": {"is_connected": true, "mtu": 247},
  "navigation": {"is_navigating": true, "current_dir": "right", "current_dist": 26},
  "ble_service": {"ble_connected": true, "queue_size": 0}
}
```

---

**报告完成时间**：2026-06-21
**Step 3 状态**：✅ 完成
