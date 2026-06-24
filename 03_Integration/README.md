# SmartRidingHelmet — 系统集成

> **目的**：这个目录是集成测试的大本营。所有跟"把模块拼一起跑通"相关的东西都放这里。
>
> **谁用**：负责集成的开发人员。测试人员在此写报告，开发人员在此跑测试。

---

## 目录结构

```
03_Integration/
│
├── README.md                  本文件
│
├── plans/                     集成计划文档
│   ├── integration.md         v2 全局集成方案（5 Step 渐进式）
│   └── 集成指南.md            Phase 4 实战指南
│
├── tests/                     集成测试文件（按阶段组织）
│   │
│   ├── step1_base/            Step 1 基础基线（11 模块，无 CloudService）
│   │   └── test_system_base.py
│   │
│   ├── step2_ble_light/       Step 2 BLE + PWM 灯光（15 模块）
│   │   ├── test_pwm_led.py
│   │   ├── test_ble_driver.py
│   │   ├── test_ble_service.py
│   │   ├── test_light_service.py
│   │   └── test_device_integration.py
│   │
│   ├── step3_navigation/      Step 3 导航链路（16 模块）
│   │   ├── test_navigation_service.py
│   │   └── test_navigation_e2e.py
│   │
│   ├── step4_control/         Step 4 远端控制（17 模块）
│   │   ├── test_control_service.py
│   │   ├── test_control_e2e.py
│   │   └── test_light_control.py
│   │
│   ├── step5_voice/           Step 5 语音控制（18 模块）
│   │   ├── test_voice_driver.py
│   │   ├── test_voice_control_integration.py
│   │   ├── test_voice_e2e.py
│   │   └── test_voice_real_debug.py
│   │
│   ├── step6_addition/        Step 6 补充测试（AudioService + 电池/电源 + 全系统 v2）
│   │   ├── test_audio_service.py
│   │   ├── test_power_battery.py
│   │   └── test_full_system_v2.py
│   │
│   └── full_system/           v1 全系统（12 模块，含 CloudService，已过时）
│       └── test_system_v1.py
│
├── reports/                   测试报告
│   ├── REPORT_TEMPLATE.md     复制这个模板写报告
│   ├── learnings.md           测试中发现的教训
│   └── YYYY-MM-DD_xxx.md     各阶段测试报告
│
├── configs/                   参考配置
│   ├── test_config.py         测试参数（超时、重试等）
│   └── hardware_config.py     硬件引脚、设备地址参考
│
└── demo/                      演示相关
    └── demo_checklist.md      演示前逐项确认
```

---

## 测试状态（当前进度）

| 阶段 | 内容 | 模块数 | 测试文件 | 上板验证 |
|------|------|--------|---------|---------|
| ✅ Step 1 | 基线（无 CloudService） | 11 | test_system_base.py | ✅ 通过 (7/7) |
| ✅ Step 2 | BLE + PWM 灯光 | 15 | 5 个文件 | ✅ 通过 |
| ✅ Step 3 | 导航链路 | 16 | 2 个文件 | ✅ 通过 |
| ✅ Step 4 | 远端控制 | 17 | 3 个文件 | ✅ 通过 |
| ✅ Step 5 | 语音控制 | 18 | 4 个文件 | ✅ 通过 (24/24) |
| 🔧 Step 6 | 补充测试 | 21 | 3 个文件 | 🔧 测试中 |
| ⏸️ full_system | v1 基线（含 CloudService） | 12 | test_system_v1.py | ⚠️ 已过时 |

### 2026-06-24 变更说明

今日 Step 6 测试更新涉及 4 个模块：

| 模块 | 变更内容 |
|------|----------|
| AudioDriver | `tick()` 移除 `power_state` 守卫，确保回调缓冲区正常处理 |
| BatteryDriver | 新增 `sample_count` 字段，用于启动宽限期判断 |
| PowerService | 添加启动宽限期（`sample_count < 3` 不做省电决策）+ 未接电池阈值 500→1000 |
| ControlService | 订阅 `EVENT_POWER_STATE_CHANGE`，接收 PowerService 省电事件后回推状态到小程序 |

---

## 怎么用这个目录？

```
测试流程：
  1. 打开 tests/stepX_xxx/ 找到要跑的测试文件
  2. 用 Thonny 上传到板子运行
  3. 把终端输出保存到 reports/YYYY-MM-DD_xxx.md
  4. 有问题？写到 reports/learnings.md
  5. 全部通过？推进下一步
```

---

## 核心原则

1. **自底向上**：传感器 → 执行器 → 服务 → 全系统，底层站稳了再叠上层
2. **每阶段独立测试**：一个 Step 全部通过后再推进下一个
3. **测试必须上板**：MicroPython 只能在 NUCLEO-F413ZH 上运行，PC 不能模拟
4. **main.py 保留回退**：v1 main.py 作为稳定回退，不删
