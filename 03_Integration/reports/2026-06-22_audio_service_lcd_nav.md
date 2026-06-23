# 集成报告 — AudioService + LCD 导航恢复

## 基本信息
- **日期**：2026-06-22
- **测试人**：AI Agent (Oracle 审查 + 语法验证)
- **测试文件**：main.py（19 模块全集成）
- **硬件状态**：NUCLEO-F413ZH + EC200U，BLE/GNSS

## 变更概述

本次集成新增 AudioService 模块，解决 TTS 播报冲突和 LCD 导航文字被覆盖问题。

### 新增模块
| 模块 | 文件 | 说明 |
|------|------|------|
| AudioService | Modules/audio_service.py | 统一音频调度（优先级队列 + 超时丢弃） |

### 修改模块
| 模块 | 修改内容 |
|------|----------|
| config.py | 新增 EVENT_NAV_DISPLAY、PRIORITY_ALARM/NAV/CTRL |
| navigation_service.py | TTS 改用 EVENT_TTS_REQUEST；LCD 改用 EVENT_NAV_DISPLAY；移除僵尸 TTS 线程 |
| control_service.py | TTS 请求带 priority=PRIORITY_CTRL |
| display_service.py | 订阅 EVENT_NAV_DISPLAY，渲染时恢复导航文字 |
| Audio.py | 移除 EVENT_TTS_REQUEST 订阅（改由 AudioService 管理） |
| main.py | 导入 + 初始化 AudioService，加入 init_order |

## 测试结果

### 语法验证
```
结果: 7/7 通过
ALL PASS
```

| 文件 | 结果 |
|------|------|
| core/config.py | ✅ |
| Modules/audio_service.py | ✅ |
| Modules/navigation_service.py | ✅ |
| Modules/control_service.py | ✅ |
| Modules/display_service.py | ✅ |
| Drivers/actuator/Audio.py | ✅ |
| core/main.py | ✅ |

### 一致性验证
```
结果: 10/10 通过
ALL PASS
```

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | config.py 定义 EVENT_NAV_DISPLAY + PRIORITY_* | ✅ |
| 2 | audio_service.py 正确 import 常量 | ✅ |
| 3 | navigation_service.py import EVENT_TTS_REQUEST/NAV_DISPLAY/PRIORITY_NAV | ✅ |
| 4 | navigation_service.py 移除 _thread 和 ThreadSafeQueue | ✅ |
| 5 | navigation_service.py 移除 _tts_worker 和 deinit | ✅ |
| 6 | navigation_service.py get_status() 不再引用已删除字段 | ✅ |
| 7 | control_service.py TTS 请求带 priority | ✅ |
| 8 | Audio.py 移除 EVENT_TTS_REQUEST 订阅和 _on_tts_request | ✅ |
| 9 | display_service.py 订阅 NAV_DISPLAY + 渲染恢复 | ✅ |
| 10 | main.py AudioService 在 AlarmService 之前初始化 | ✅ |

### Oracle 代码审查
```
结果: 3 个 Bug 发现并修复
```

| Bug | 文件 | 问题 | 修复 |
|-----|------|------|------|
| BUG 1 | audio_service.py | 同优先级检查 is_busy 导致 10ms 延迟 | 改为无条件 stop + play |
| BUG 2 | navigation_service.py | 僵尸 TTS 线程绕过 AudioService | 移除 _tts_queue/_tts_worker/deinit |
| BUG 3 | navigation_service.py | 报警期间 LCD 直接写入覆盖报警画面 | 添加 alarm_active 检查 |

## 初始化顺序变更

```
原：... → CollisionService → AlarmService → ...
新：... → CollisionService → AudioService → AlarmService → ...
```

AudioService 必须在 AlarmService 之前初始化，因为报警触发时需要 AudioService 已就绪。

## 数据流变更

### TTS 数据流（变更前）
```
NavigationService → audio_driver.play_tts()  （直接调用，无优先级）
ControlService → EVENT_TTS_REQUEST → AudioDriver._on_tts_request()  （有 alarm_playing 门控）
```

### TTS 数据流（变更后）
```
NavigationService → EVENT_TTS_REQUEST(priority=NAV) → AudioService → AudioDriver.play_tts()
ControlService → EVENT_TTS_REQUEST(priority=CTRL) → AudioService → AudioDriver.play_tts()
```

### LCD 导航数据流（新增）
```
NavigationService → EVENT_NAV_DISPLAY → DisplayService._on_nav_display()
  → 缓存 _nav_text
  → _render_normal_screen() 末尾恢复导航文字
```

## 冲突场景覆盖

| 场景 | 预期行为 |
|------|----------|
| 导航播报 + 语音控制 | NAV(1) 优先播放，CTRL(2) 入队等待 |
| 导航播报 + 报警触发 | ALARM(0) 打断导航，队列清空 |
| 报警中 + 导航 TTS | 直接丢弃（不排队） |
| 队列满（3个）+ 新低优先级 | 丢弃最旧的，新请求入队 |
| 队列项超时 5s | tick() 自动清理 |
| DisplayService 清屏 | 渲染末尾自动恢复导航文字 |
| 报警期间导航指令 | LCD 直接写入被跳过 |

## 待办
- [ ] 上板实测 TTS 优先级调度
- [ ] 上板实测 LCD 导航文字恢复
- [ ] 上板实测报警期间 LCD 保护
- [ ] SD 卡 play_file 扩展（待硬件验证）

## 文档版本
- **报告版本**：v1.0
- **更新日期**：2026-06-22
- **备注**：AudioService 新建 + LCD 导航恢复 + Oracle 审查 3 Bug 修复
