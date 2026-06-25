# 功能集成报告 — 固件冻结：将全部模块烧录进 MicroPython 固件

> **日期**：2026-06-25
> **功能**：将 smartcore 全部 Python 模块（core / Drivers / Modules）冻结到 MicroPython 固件中，消除运行时文件系统依赖
> **涉及模块**：core（3个）、Drivers（16个）、Modules（9个）、manifest.py、固件编译工具链
> **状态**：✅ 完成

---

## 1. 功能概述

将所有自定义 Python 模块通过 MicroPython 冻结机制编译进固件 ROM，使系统上电即可运行，无需手动部署 Python 文件到 flash 文件系统。

---

## 2. 改动清单

| # | 文件 | 改动类型 | 改动内容 | 行数 |
|---|------|---------|---------|------|
| 1 | `lib/micropython-lib/micropython/smartcore/manifest.py` | 新增 | 冻结清单，定义 28 个模块的冻结路径 | +35 |
| 2 | `lib/micropython-lib/micropython/smartcore/core/*.py` | 新增 | Base_Module.py, config.py, Event_Bus.py 复制到冻结目录 | +224 |
| 3 | `lib/micropython-lib/micropython/smartcore/Drivers/**/*.py` | 新增 | 16 个驱动模块复制到冻结目录 | +1500 |
| 4 | `lib/micropython-lib/micropython/smartcore/Modules/*.py` | 新增 | 9 个服务模块复制到冻结目录 | +2000 |
| 5 | `ports/stm32/boards/STM32F413/manifest.py` | 修改 | 添加 `require("smartcore")` | +1 |

---

## 3. 冻结架构

```
固件 ROM（不可变）
├── MicroPython 内核
├── Quectel C 模块（quectel.Network, SMS, GNSS, BLE, Audio...）
├── 冻结库（lis2dh12, ahtx0, st7735, log, urequests...）
└── smartcore 冻结模块（本次新增）
    ├── core/Base_Module.py, config.py, Event_Bus.py
    ├── Drivers/sensor/（7个）
    ├── Drivers/actuator/（4个）
    ├── Drivers/interface/（2个）
    ├── Drivers/network/（3个）
    └── Modules/（9个）

Flash 文件系统（可变）
├── main.py          ← 启动入口
├── images.py        ← 图标数据
└── images1.py       ← 图标数据
```

---

## 4. 关键设计决策

| 决策 | 选项 | 选择理由 |
|------|------|---------|
| 冻结方式 | `freeze()` 保留目录结构 | 代码使用 `from core.Base_Module import` 包导入，必须保留路径 |
| 不冻结 main.py | 放 flash 运行 | main.py 是启动入口，便于独立修改不需重编译 |
| 不冻结 images | 放 flash 运行 | 图片数据较大，冻结会占用固件 flash 空间 |
| 使用最新固件源码 | quectel_bg95_reference_design (1) | 旧版缺少 `ql_sms.c`，新版已包含 SMS 模块 |

---

## 5. 固件容量分析

| 项目 | 大小 | 说明 |
|------|------|------|
| firmware.hex | 1.8 MB | 可烧录固件 |
| firmware.elf | 7.1 MB | 调试用（含符号表） |
| STM32F413ZH Flash | 1.5 MB | 芯片总 flash |
| TEXT 区域 | 658 KB | 实际代码+数据占用 |

固件 658KB 远小于 1.5MB flash 容量，**空间充裕**，后续添加更多模块无压力。

---

## 6. 验收标准

| # | 验证项 | 预期结果 | 验证方法 |
|---|--------|---------|---------|
| 1 | 固件编译 | 编译成功，无报错 | `make BOARD=STM32F413` |
| 2 | 模块冻结 | 28 个模块全部在 frozen_content.c 中 | grep 检查 |
| 3 | SMS 可用 | `from quectel import SMS` 成功 | REPL 测试 |
| 4 | 包导入正常 | `from core.Event_Bus import EventBus` 成功 | REPL 测试 |
| 5 | 启动正常 | 上电自动运行，无需手动部署文件 | 烧录后观察 |

---

## 7. 回滚方案

| 场景 | 操作 | 影响范围 |
|------|------|---------|
| 回退到旧固件 | 烧录 Quectel 原始 UniKnect 固件 | 丢失 smartcore 所有模块 |
| 移除 smartcore | 删除 manifest.py 中 `require("smartcore")` 并重编译 | 回到无自定义模块状态 |
| 部分移除 | 在 manifest.py 中注释掉对应模块 | 仅该模块不可用 |

---

## 8. 备注

- **编译环境**：MSYS2 MINGW64 + ARM GCC 13.3
- **编译命令**：需要设置 `PYTHONUTF8=1` 解决编码问题
- **后续优化**：可将 images.py 也冻结进固件（需评估 flash 剩余空间）
- **main.py 不冻结**：保持灵活性，便于调试时快速修改启动逻辑
