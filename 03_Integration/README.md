# SmartRidingHelmet — 系统集成

> **目的**：这个目录是集成测试的大本营。所有跟"把模块拼一起跑通"相关的东西都放这里。
>
> **谁用**：负责集成的开发人员。测试人员在此写报告，开发人员在此跑测试。

---

## 目录结构（每个文件夹干什么用？）

```
03_Integration/
│
├── README.md
│       本文件。每次进这个目录先看这里，了解当前进度和目录结构。
│
├── plans/
│       集成计划文档。想了解"我们分几步走"看这里。
│   └── integration-plan.md     ← 当前集成计划（5阶段）
│
├── tests/
│       集成测试文件。每个测试文件都是独立的，可以上传到板子直接运行。
│       按集成阶段（Wave）组织，从底层到顶层。
│   │
│   ├── wave0_baseline/   ← 已有文件
│   │   └── test_system_v1.py     （v1 12模块基线，确认现有功能正常）
│   │
│   ├── wave1_device/     ← 已有文件
│   │   ├── test_pwm_led_unit.py           （PWM_LED 单模块）
│   │   ├── test_ble_driver_unit.py        （BLEDriver 单模块）
│   │   └── test_device_integration.py     （Device 层联合）
│   │
│   ├── wave2_service/    ← 已有文件
│   │   ├── test_light_service_integration.py    （LightService + PWM）
│   │   ├── test_control_service_integration.py  （ControlService 纯事件）
│   │   └── test_light_control_integration.py    （Service 层联合）
│   │
│   ├── wave3_communication/  ← 已有文件
│   │   ├── test_ble_service_integration.py      （BLEService 双线程）
│   │   ├── test_navigation_service_integration.py（NavigationService）
│   │   └── test_communication_integration.py    （通信层联合）
│   │
│   ├── wave4_full_system/   ← 空（等前面跑通后创建）
│   │       全系统集成测试：main_v2.py 初始化 + 完整 E2E 场景。
│   │
│   └── wave6_voice/         ← 空（等队友发送VoiceDriver后创建）
│           语音驱动集成测试。VoiceDriver 代码在队友手中，阻塞中。
│
├── reports/
│       测试报告。每次上板跑完测试后写一份，记录结果、问题、日志。
│   ├── REPORT_TEMPLATE.md    ← 复制这个模板写报告
│   └── learnings.md          ← 从测试中发现的教训，避免重复踩坑
│
├── scripts/
│       批量脚本。← 目前空的
│       将来可放：批量上传测试文件的脚本、一键跑全部测试的脚本等。
│       不一定要有，需要时再创建。
│
├── configs/
│       参考配置。测试过程中需要查的引脚、接口参数放这里。
│   ├── test_config.py        ← 测试参数（超时、重试等） 
│   └── hardware_config.py    ← 硬件引脚、设备地址参考
│
└── demo/
        演示相关。最终演示用的脚本和检查清单。
    └── demo_checklist.md     ← 演示前逐项确认

```

---

## 测试状态（当前进度）

| 阶段 | 内容 | 测试文件 | 上板验证 |
|------|------|---------|---------|
| ✅ Wave 0 | v1 基线（12 模块） | test_system_v1.py | ✅ 通过 |
| 🔧 Wave 1 | Device 层（PWM_LED, BLE） | 3 个文件 | ⚠️ 修复中 |
| ⏳ Wave 2 | Service 层（Light, Control） | 3 个文件 | ⏸ 待测 |
| ⏳ Wave 3 | 通信层（BLEService, Nav） | 3 个文件 | ⏸ 待测 |
| ⏳ Wave 4 | 全系统（main_v2.py） | 待创建 | 📅 等 Wave 1-3 通过 |
| ⏸️ Wave 6 | 语音集成（VoiceDriver） | 待创建 | 阻塞（等队友） |

---

## 怎么用这个目录？

```
测试流程：
  1. 打开 tests/waveX_xxx/ 找到要跑的测试文件
  2. 用 Thonny 上传到板子运行
  3. 把终端输出保存到 reports/YYYY-MM-DD_xxx.md
  4. 有问题？写到 reports/learnings.md
  5. 全部通过？推进下一 Wave
```

---

## 核心原则

1. **自底向上**：Device → Service → 通信 → 全系统，底层站稳了再叠上层
2. **每阶段独立测试**：一个 Wave 全部通过后再推进下一个
3. **main_v2.py 保留 v1**：`main.py` 作为稳定回退，不删
4. **测试必须上板**：MicroPython 只能在 NUCLEO-F413ZH 上运行，PC 不能模拟
