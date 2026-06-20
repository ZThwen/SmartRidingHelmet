# 导航功能设计 — Brainstorm Summary

**日期**: 2026-05-28
**状态**: 设计完成，待实施
**范围**: 微信小程序端导航功能（Step B 小程序侧）

---

## 背景

智能骑行头盔项目 v2 需要新增导航引导功能（F-NAV-01）。小程序端负责路线规划和指令下发，头盔端负责 GNSS 比对和 TTS 播报（v2 后续开发）。

当前 Step A 已完成：BLE 直连数据通道、骑行记录、地图轨迹、报警弹窗。导航是 Step B 的核心新增功能。

---

## 关键决策

| 决策 | 选项 | 结论 | 理由 |
|:-----|:-----|:-----|:-----|
| 地图 API | 腾讯地图 vs 高德 | **腾讯地图 WebService API** | 与微信原生 `<map>` 坐标系一致 (GCJ-02)，无需额外 SDK |
| 数据下发 | BLE 直连 vs 云端 writeData vs 双通道 | **BLE 直连 (sendNav → FFF2)** | 延迟 <100ms，骑行时 BLE 必定已连接，无需云端 TSL 配置 |
| 实现方案 | Index 浮层 vs 独立页面 vs 仅服务层 | **Index 页面浮层** | 符合现有双页架构和 thin dispatcher 模式 |
| 导航触发 | 随时可用 vs 仅骑行中 | **出发前选择（可跳过）** | 点击"开始骑行"后弹窗询问是否设置目的地 |
| 骑行中 UI | 仅路线 vs 路线+指令 vs 完整 | **路线 + 指令浮层** | 平衡信息量和屏幕占用 |
| 路线显示 | 双 polyline vs 切换模式 | **双 polyline** | 蓝色骑行轨迹 + 绿色规划路线共存 |
| 报警冲突 | 暂停+恢复 vs 取消 vs 不处理 | **暂停+恢复** | 报警优先，导航暂停后从当前 step 恢复 |
| 开发顺序 | 小程序先 vs STM32 先 | **小程序先** | 可独立验证，STM32 是消费者 |

---

## 功能设计

### 用户流程

```
[点击"开始骑行"]
    ↓
[弹窗: 设置目的地 / 直接出发]
    ↓ (设置目的地)
[wx.chooseLocation() 选目的地]
    ↓
[腾讯地图 API 算路 → 绿色路线显示在地图上]
    ↓
[开始骑行 → 5秒定时器推送指令到头盔 via BLE FFF2]
    ↓
[底部浮层显示当前指令 + 距离]
    ↓ (报警发生)
[暂停导航推送 → 弹出报警浮层]
    ↓ (报警取消)
[恢复导航推送]
    ↓ (到达/取消)
[清除路线 → 状态回到 idle]
```

### 状态机

```
idle ──选目的地──→ planning ──算路完成──→ navigating ──到达──→ arrived
                                                    │
                                                    └──取消──→ cancelled
                                                    │
                                                    └──报警──→ paused ──报警取消──→ navigating
```

### BLE 数据格式

```javascript
// sendNav(direction, distance, road) 写入 FFF2:
{
  "a": "nav",
  "d": {
    "dir": "右转",           // 方向指令
    "dist": 200,             // 距下一拐弯(米)
    "road": "中山路"         // 路名
  }
}
```

---

## 文件改动清单

| 文件 | 操作 | 说明 |
|:-----|:-----|:-----|
| `services/navigation-service.js` | **新建** | 路线规划 + 状态机 + BLE 推送 + pause/resume |
| `services/map-service.js` | 修改 | +`buildRoutePolyline()` +`buildDestMarker()` |
| `pages/index/index.js` | 修改 | +nav 数据字段 + 出发前弹窗逻辑 + 报警暂停/恢复 |
| `pages/index/index.wxml` | 修改 | +目的地选择弹窗 + 导航指令浮层 |
| `pages/index/index.wxss` | 修改 | +弹窗和浮层 Tactical Cyan 样式 |
| `utils/config.js` | 修改 | +`TENCENT_MAP_KEY` 字段 |
| `app.json` | 修改 | +`"chooseLocation"` 到 requiredPrivateInfos |

**不改动:** `ble-service.js`、`ride-service.js`、`alarm-service.js`、`crypto.js`、`logger.js`、`ble-protocol.js`

---

## 前置条件

1. **腾讯地图 API Key** — 在 lbs.qq.com 注册，创建应用，获取 WebService API Key（免费 10000 次/天）
2. `project.private.config.json` 的 `urlCheck: false` — 已配置

---

## 不在本次范围

- 头盔端 `NavigationService.py`（v2，GNSS 比对 + TTS 播报）
- 云端 writeData 通道（后续可加作为 BLE 断连兜底）
- 语音 TTS 播报（Step B 头盔端部分）
- 语音 ASR 控制（Step C）

---

## 验证方式

**WeChat DevTools（无硬件）：**
1. wx.chooseLocation → 选目的地 → 返回坐标
2. 腾讯地图 API → 路线响应 → 坐标解压 → steps 解析
3. 地图绿色 polyline + 目的地 marker
4. 指令浮层显示
5. 取消导航 → 清除路线

**实际硬件（需开发者操作）：**
1. BLE 连接头盔 → 选目的地 → 双 polyline 显示
2. 骑行中指令浮层每 5 秒更新
3. 头盔串口日志确认收到 sendNav 数据
4. 报警触发 → 导航暂停 → 恢复
