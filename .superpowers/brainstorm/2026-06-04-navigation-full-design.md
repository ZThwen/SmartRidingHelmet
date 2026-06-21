# 导航功能完整开发设计 Spec

## Context

板子端 NavigationService 已完成（TTS + LCD），但端到端导航从未跑通。小程序用手机 GPS 做路线规划，不符合实际产品设计——应该用板子的定位坐标。室内 GNSS 无信号，需要用 LBS 补偿。同时小程序有 3 个已知 bug 阻塞导航功能。

## 完整数据流

```
板子 GNSS/LBS → BLE merged 上报(含 lat/lon) → 小程序读取坐标
    → 腾讯地图路线规划 → BLE FFF2 推送导航指令 → 板子 NavigationService → TTS + LCD
```

## 坐标来源逻辑

| 状态 | 坐标来源 | 说明 |
|------|---------|------|
| 未骑行 | 手机 GPS (`wx.getLocation()`) | 显示用户位置，不需要板子 |
| 骑行中 + BLE 已连接 | 板子坐标（BLE merged 数据） | 贴近实际产品 |
| 骑行中 + BLE 断开 | 手机 GPS fallback | 兜底 |

## 现有代码关键发现

1. **双 GPS 源已存在**: `index.js` 的 `onData`（`data.t === 0`）已用板子 BLE 坐标更新 `mapLat/mapLon`，同时 `wx.onLocationChange` 用手机 GPS 更新骑行轨迹
2. **导航用手机 GPS**: `navigation-service.js` 的 `startNavigation()` 调用 `wx.getLocation()` 做路线规划
3. **导航路线未绑定地图**: `navRoutePolilines`/`navDestMarker` 在 data 中但 `<map>` 未绑定
4. **polyline 解码器已实现差分编码**: `_decodePolyline` 可能已能处理腾讯地图格式，需实测
5. **`_str2ab` 只支持 ASCII**: 中文路名会被截断

## 子项目分解

### 子项目 A: LBSDriver（板子端新模块）

**目标**: 室内环境下通过基站定位获取板子坐标。

**文件**:
- 新建: `Drivers/sensor/LBS.py`
- 新建: `Tests/test_lbs_unit.py`
- 新建: `Tests/test_lbs_e2e.py`
- 修改: `core/config.py`（添加 LBS 配置常量）

**实现**:
```python
from quectel import LBS as _LBS

class LBSDriver(BaseModule):
    def __init__(self, event_bus=None):
        self.name = "lbs"
        self.cfg = {"timeout_ms": 15000, "sample_ms": 30000}
        self.ctx = {"is_init": False, "is_positioning": False, "err_count": 0}
        self._data = {"latitude": None, "longitude": None, "accuracy": None, "valid": False}
```

**关键设计**:
- `get_location()` 阻塞 15 秒，必须在子线程中调用
- tick() 用 `is_positioning` 标志位避免重复启动
- 发布 `EVENT_LBS_READY`（新建事件，payload: `{latitude, longitude, accuracy, source: "lbs"}`）
- EC200U 不能同时 GNSS + LBS，LBSDriver 和 GNSSDriver 不能同时 init

**风险**: 低——新模块，不影响已有代码。

---

### 子项目 B: 小程序坐标来源改造

**目标**: 骑行中用板子 BLE 坐标做路线规划。

**文件**:
- 修改: `WeChatMiniProgram/services/navigation-service.js`
- 修改: `WeChatMiniProgram/pages/index/index.js`

**改动**:

`navigation-service.js` — `startNavigation(dest)` 增加可选参数 `origin`:
```javascript
// 当前代码:
function startNavigation(dest) {
  // ... wx.getLocation({type: 'gcj02'}) 获取当前位置 ...
  _fetchRoute(lat, lng, dest.lat, dest.lng);
}

// 改为:
function startNavigation(dest, origin) {
  if (origin && origin.lat && origin.lng) {
    // 用板子坐标
    _fetchRoute(origin.lat, origin.lng, dest.lat, dest.lng);
  } else {
    // fallback 手机 GPS
    wx.getLocation({type: 'gcj02', success: function(res) {
      _fetchRoute(res.latitude, res.longitude, dest.lat, dest.lng);
    }});
  }
}
```

`index.js` — `_startRide()` 调用时传入 BLE 坐标:
```javascript
// 当前代码:
NavService.startNavigation(this._navDest);

// 改为:
var origin = null;
if (this.data.bleConnected && this.data.mapLat && this.data.mapLon) {
  origin = {lat: parseFloat(this.data.mapLat), lng: parseFloat(this.data.mapLon)};
}
NavService.startNavigation(this._navDest, origin);
```

**风险**: 中——改坐标来源逻辑。`mapLat/mapLon` 在 onData 回调中已被 BLE 坐标更新，直接复用。

**依赖分析**:
- `startNavigation()` 只被 `_startRide()` 调用
- `wx.getLocation()` 在 `onLoad` 和 `onMapReset` 中还有使用，不受影响

---

### 子项目 C: 小程序导航 bug 修复

**文件**:
- 修改: `WeChatMiniProgram/pages/index/index.wxml`（Bug 1）
- 修改: `WeChatMiniProgram/pages/index/index.js`（Bug 1）
- 修改: `WeChatMiniProgram/services/ble-service.js`（Bug 2）
- 修改: `WeChatMiniProgram/services/navigation-service.js`（Bug 3）

**Bug 1 — 地图不显示导航路线**:
- `<map>` 只绑定了 `trackPolylines`/`trackMarkers`
- 修复: 在 `NavService.onStateChange` 回调中，将 `navRoutePolylines` 合并到 `trackPolylines`，将 `navDestMarker` 合并到 `trackMarkers`
- 注意: 不能在 WXML 中用 `.concat()`（之前踩过坑），必须在 JS 中预合并

**Bug 2 — 中文路名 BLE 传输损坏**:
- `_str2ab()` 用 `charCodeAt()` 转 Uint8Array，中文被截断
- 修复: 改用 `TextEncoder.encode()`
- 风险: 高——`_str2ab` 被 `sendNav`/`sendCtrl`/`sendAck` 共用，需全面回归

**Bug 3 — polyline 解码**:
- 当前 `_decodePolyline` 已实现差分编码处理
- 先 `console.log(route.polyline)` 确认 API 返回格式
- 如果是差分编码数组 → 当前代码已能处理，无需修改
- 如果是编码字符串 → 需实现 Google polyline 解码

---

### 子项目 D: 端到端联调

**前提**: A/B/C 全部完成。

**验证清单**:
- [ ] 板子 LBS 定位返回坐标
- [ ] 小程序收到 BLE 数据中的坐标
- [ ] 骑行中路线规划使用板子坐标
- [ ] 路线规划 API 成功调用
- [ ] 地图显示导航路线 + 目的地
- [ ] 导航指令卡片正常显示
- [ ] 板子 TTS 播报中文导航
- [ ] 板子 LCD 底部导航行显示
- [ ] 中文路名不乱码
- [ ] 报警暂停/恢复正常

## 依赖关系

```
A (LBSDriver) ──┐
                ├──→ D (端到端联调)
B (路线改造) ──┤
C (bug 修复) ──┘
```

A/B/C 互相独立，可并行开发。D 依赖 A/B/C 全部完成。

## 风险缓解

| 改动 | 风险 | 缓解措施 |
|------|------|---------|
| A: LBSDriver | 低 | 新模块，不影响已有代码 |
| B: 坐标来源改造 | 中 | 只改 startNavigation 加 origin 参数，不影响其他 |
| C-Bug1: 地图绑定 | 低 | JS 中预合并数组，不改 WXML 绑定 |
| C-Bug2: UTF-8 编码 | 高 | 改前查所有调用者（sendNav/sendCtrl/sendAck），改后全面回归 |
| C-Bug3: polyline 解码 | 中 | 先 console.log 确认格式，可能不需要改 |
