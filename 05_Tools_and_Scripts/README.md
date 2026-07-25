# 工具与脚本

本目录存放固件编译、环境搭建相关工具和文档。

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `操作手册_用户版.md` | MicroPython 固件编译操作手册 |
| `micropython环境搭建.txt` | Linux 下编译环境搭建步骤 |
| `README.md` | 本文件 |

> `msys2-x86_64-20250830.exe` (89MB) 和 `quectel_bg95_reference_design.zip` (462MB)
> 属于编译环境外部依赖，体积过大，已通过 `.gitignore` 排除，不提交到 Git 仓库。
>
> - MSYS2 官方下载：<https://www.msys2.org/>
> - MicroPython 源码路径：`E:\ubuntu\stm32_micropython\quectel_bg95_reference_design (1)\`
> - 固件编译详细步骤见 `操作手册_用户版.md`

## 固件编译工具链

本项目模块已冻结进 MicroPython 固件 ROM（通过 `manifest.py` 编译进固件，非 flash 文件系统）。

| 工具 | 用途 |
|------|------|
| **MSYS2 MINGW64** | Windows 编译环境 |
| **ARM GCC 13.3** | 交叉编译器（`arm-none-eabi-`） |
| **make** | 编译驱动 |
| **Python 3** | 编译脚本依赖 |
| **STM32CubeProgrammer** | 烧录 `firmware.hex` 到开发板 |
| **Thonny IDE** | REPL 调试 + flash 文件管理 |

### 编译步骤概要

1. 打开 MSYS2 MINGW64
2. 切换到 MicroPython 源码 `ports/stm32` 目录
3. 执行编译：

   ```bash
   export PATH=/opt/arm-gnu-toolchain-13.3.../bin:/usr/bin:/mingw64/bin:$PATH
   export PYTHONUTF8=1
   make clean && make BOARD=STM32F413 V=1 -j4
   ```

4. 生成 `build-STM32F413/firmware.hex`
5. 用 STM32CubeProgrammer 烧录

详细步骤和常见问题见 `操作手册_用户版.md`。

### 冻结模块结构

```
micropython/lib/micropython-lib/micropython/smartcore/
├── core/           ← Base_Module, config, Event_Bus
├── Drivers/        ← 传感器/执行器/网络驱动
├── Modules/        ← 报警/导航/灯光/控制等服务
└── manifest.py     ← 冻结文件清单
```

### flash 文件系统（需手动上传）

| 文件 | 来源 |
|------|------|
| `main.py` | `02_Software/core/main.py` |
| `images.py` | `02_Software/images.py` |
| `images1.py` | `02_Software/images1.py` |

## 相关文档

| 文档 | 路径 |
|------|------|
| 固件编译手册 | `操作手册_用户版.md` |
| AI Agent 工作指南 | `../AGENTS.md` |
| 测试指南 | `../02_Software/Tests/测试指南.md` |
| 架构设计 | `../00_Planning/01_architecture.md` |
