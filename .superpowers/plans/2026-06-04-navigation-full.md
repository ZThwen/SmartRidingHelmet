# Navigation Feature Full Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable end-to-end navigation: board LBS/GNSS coordinates → mini program route planning → BLE FFF2 nav instructions → board TTS + LCD.

**Architecture:** LBSDriver provides indoor positioning on the board. Mini program reads board coordinates from BLE data for route planning during riding. Three mini program bugs are fixed (map binding, UTF-8 encoding, polyline decoding). All subprojects are independent and can be parallelized.

**Tech Stack:** MicroPython (EC200U quectel.LBS), WeChat Mini Program (JS/WXML), BLE GATT (FFF1/FFF2)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `02_Software/Drivers/sensor/LBS.py` | Create | LBS positioning driver |
| `02_Software/Tests/test_lbs_unit.py` | Create | LBS unit tests |
| `02_Software/Tests/test_lbs_e2e.py` | Create | LBS e2e test |
| `02_Software/core/config.py` | Modify | Add LBS config constants |
| `WeChatMiniProgram/services/navigation-service.js` | Modify | Accept origin param + polyline debug |
| `WeChatMiniProgram/pages/index/index.js` | Modify | Pass BLE coords to nav + merge nav polylines |
| `WeChatMiniProgram/pages/index/index.wxml` | Modify | (No change needed - JS merges arrays) |
| `WeChatMiniProgram/services/ble-service.js` | Modify | UTF-8 encoding fix |

---

### Task 1: Add LBS Config Constants to config.py

**Files:**
- Modify: `02_Software/core/config.py`

- [ ] **Step 1: Add LBS constants**

Add after the BLE config section (after line 196, `BLE_KEEPALIVE_MS`):

```python
# ================= LBS 基站定位配置 =================
LBS_TIMEOUT_MS          = 15000    # LBS 定位超时 (ms)
LBS_SAMPLE_MS           = 30000    # LBS 采样间隔 (ms)
```

Add after `EVENT_GPS_LOST` (line 41):

```python
EVENT_LBS_READY             = "LBS_READY"              # LBS定位数据就绪
```

- [ ] **Step 2: Verify syntax**

Run: `python 02_Software/core/config.py`
Expected: no output

- [ ] **Step 3: Commit**

```bash
git add 02_Software/core/config.py
git commit -m "feat(nav): add LBS config constants and EVENT_LBS_READY"
```

---

### Task 2: Create LBSDriver Module

**Files:**
- Create: `02_Software/Drivers/sensor/LBS.py`
- Create: `02_Software/Tests/test_lbs_unit.py`

- [ ] **Step 1: Write the failing test**

Create `02_Software/Tests/test_lbs_unit.py`:

```python
"""
brief LBSDriver 单模块测试（纯 fake 数据）
note 不依赖真实 quectel.LBS 硬件，使用 Fake 对象记录调用
执行: 上传到板子运行 python test_lbs_unit.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_LBS_READY
from Drivers.sensor.LBS import LBSDriver


class FakeLBS:
    """模拟 quectel.LBS"""
    def __init__(self, result=None):
        self.calls = []
        self._result = result
    def get_location(self, timeout_ms):
        self.calls.append(("get_location", timeout_ms))
        return self._result
    def deinit(self):
        self.calls.append(("deinit",))


def make_driver(loc_result=None):
    """创建 LBSDriver + EventBus，注入 FakeLBS"""
    bus = EventBus()
    drv = LBSDriver(bus)
    drv._lbs = FakeLBS(loc_result)
    drv.ctx["is_init"] = True
    return drv, bus


# ==================== 测试用例 ====================

def test_get_location_success():
    """定位成功 → 发布 EVENT_LBS_READY"""
    drv, bus = make_driver({"latitude": 31.84, "longitude": 117.24, "accuracy": 4400.0, "status": 0})
    captured = []
    bus.subscribe(EVENT_LBS_READY, lambda p: captured.append(p))
    drv._do_positioning()
    bus.pump()
    assert len(captured) == 1
    assert captured[0]["latitude"] == 31.84
    assert captured[0]["longitude"] == 117.24
    assert captured[0]["accuracy"] == 4400.0
    assert captured[0]["source"] == "lbs"
    assert drv.ctx["is_positioning"] == False
    assert drv._data["valid"] == True
    print("  OK get_location_success")


def test_get_location_failure():
    """定位失败 → 不发布事件，err_count +1"""
    drv, bus = make_driver(None)
    captured = []
    bus.subscribe(EVENT_LBS_READY, lambda p: captured.append(p))
    drv._do_positioning()
    bus.pump()
    assert len(captured) == 0
    assert drv.ctx["err_count"] == 1
    assert drv._data["valid"] == False
    print("  OK get_location_failure")


def test_get_location_status_error():
    """status != 0 → 定位失败"""
    drv, bus = make_driver({"latitude": 0, "longitude": 0, "accuracy": 0, "status": 1})
    captured = []
    bus.subscribe(EVENT_LBS_READY, lambda p: captured.append(p))
    drv._do_positioning()
    bus.pump()
    assert len(captured) == 0
    assert drv.ctx["err_count"] == 1
    print("  OK get_location_status_error")


def test_no_duplicate_positioning():
    """is_positioning=True 时不重复启动"""
    drv, bus = make_driver({"latitude": 31.84, "longitude": 117.24, "accuracy": 4400.0, "status": 0})
    drv.ctx["is_positioning"] = True
    drv._do_positioning()
    assert len(drv._lbs.calls) == 0  # 没有调用 get_location
    print("  OK no_duplicate_positioning")


def test_get_data():
    """get_data 返回定位数据"""
    drv, _ = make_driver()
    drv._data["latitude"] = 31.84
    drv._data["longitude"] = 117.24
    d = drv.get_data()
    assert d["latitude"] == 31.84
    assert d["longitude"] == 117.24
    assert "accuracy" in d
    assert "valid" in d
    print("  OK get_data")


def test_get_status():
    """get_status 返回模块状态"""
    drv, _ = make_driver()
    s = drv.get_status()
    assert "is_init" in s
    assert "is_positioning" in s
    assert "err_count" in s
    print("  OK get_status")


def test_deinit():
    """deinit 释放 LBS 资源"""
    drv, _ = make_driver()
    drv.deinit()
    assert ("deinit",) in drv._lbs.calls
    assert drv.ctx["is_init"] == False
    print("  OK deinit")


def test_no_event_bus():
    """无 EventBus 时不崩溃"""
    from Drivers.sensor.LBS import LBSDriver
    drv = LBSDriver(None)
    drv._lbs = FakeLBS({"latitude": 31.84, "longitude": 117.24, "accuracy": 4400.0, "status": 0})
    drv.ctx["is_init"] = True
    drv._do_positioning()
    assert drv._data["valid"] == True
    print("  OK no_event_bus")


# ==================== 入口 ====================

def main():
    print("=" * 50)
    print(" LBSDriver 单元测试")
    print("=" * 50)

    tests = [
        test_get_location_success,
        test_get_location_failure,
        test_get_location_status_error,
        test_no_duplicate_positioning,
        test_get_data,
        test_get_status,
        test_deinit,
        test_no_event_bus,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print("  FAIL {}: {}".format(t.__name__, e))
            failed += 1

    print("")
    print("=" * 50)
    print(" 结果: {} 通过, {} 失败".format(passed, failed))
    print("=" * 50)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python 02_Software/Tests/test_lbs_unit.py`
Expected: ImportError (LBSDriver doesn't exist yet)

- [ ] **Step 3: Implement LBSDriver**

Create `02_Software/Drivers/sensor/LBS.py`:

```python
"""
brief LBS基站定位驱动 (EC200U内置)
note 封装 quectel.LBS API，提供室内基站定位能力
     与 GNSSDriver 互斥（EC200U 不能同时运行 GNSS 和 LBS）

功能：
1. get_location() 阻塞定位（必须在子线程中调用）
2. 定位成功发布 EVENT_LBS_READY
3. 定位失败递增 err_count
"""
import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_LBS_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE,
    LBS_TIMEOUT_MS, LBS_SAMPLE_MS, POWER_STATE_ACTIVE,
)

# CPython 兼容
try:
    _ticks_ms = time.ticks_ms
except AttributeError:
    import time as _time
    def _ticks_ms():
        return int(_time.time() * 1000)


class LBSDriver(BaseModule):
    """
    LBS基站定位驱动：室内环境下通过基站获取粗略坐标

    注入依赖：无（quectel.LBS 是内置模块）
    互斥约束：不能与 GNSSDriver 同时 init（EC200U 限制）
    """

    def __init__(self, event_bus=None):
        """
        brief 初始化LBS驱动实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "lbs"

        self.cfg = {
            "timeout_ms": LBS_TIMEOUT_MS,    # 定位超时 15s
            "sample_ms": LBS_SAMPLE_MS,      # 采样间隔 30s
        }

        self.ctx = {
            "is_init": False,
            "is_positioning": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
        }

        self._data = {
            "latitude": None,
            "longitude": None,
            "accuracy": None,
            "valid": False,
        }

        self._lbs = None  # quectel.LBS 实例句柄

    def init(self):
        """初始化：创建 LBS 实例"""
        try:
            from quectel import LBS as _LBS
            self._lbs = _LBS()

            self.ctx["is_init"] = True
            print("[{}] 初始化完成".format(self.name))

        except Exception as e:
            print("[{}] 初始化失败: {}".format(self.name, e))
            raise

    def tick(self):
        """周期调度：触发定位（非阻塞，通过标志位控制）"""
        if not self.ctx["is_init"]:
            return
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        if self.ctx["is_positioning"]:
            return

        now = _ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return

        self.ctx["last_tick"] = now
        self._do_positioning()

    def _do_positioning(self):
        """执行一次定位（同步阻塞，应在子线程中调用或接受阻塞）"""
        if self.ctx["is_positioning"]:
            return
        if not self._lbs:
            return

        self.ctx["is_positioning"] = True
        try:
            loc = self._lbs.get_location(self.cfg["timeout_ms"])

            if loc and loc.get("status", -1) == 0:
                self._data["latitude"] = loc["latitude"]
                self._data["longitude"] = loc["longitude"]
                self._data["accuracy"] = loc.get("accuracy", 0)
                self._data["valid"] = True
                self.ctx["err_count"] = 0

                if self.event_bus:
                    self.event_bus.publish(EVENT_LBS_READY, {
                        "latitude": loc["latitude"],
                        "longitude": loc["longitude"],
                        "accuracy": loc.get("accuracy", 0),
                        "source": "lbs",
                        "timestamp": _ticks_ms(),
                    })

                print("[{}] 定位成功: {:.4f}, {:.4f} (精度: {:.0f}m)".format(
                    self.name, loc["latitude"], loc["longitude"], loc.get("accuracy", 0)))

            else:
                self._data["valid"] = False
                self.ctx["err_count"] += 1
                print("[{}] 定位失败 (err_count={})".format(self.name, self.ctx["err_count"]))

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 定位异常: {}".format(self.name, e))
            if self.event_bus:
                self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_positioning"] = False

    def deinit(self):
        """释放 LBS 资源"""
        try:
            if self._lbs:
                self._lbs.deinit()
                self._lbs = None
            self.ctx["is_init"] = False
            print("[{}] 已释放".format(self.name))
        except Exception as e:
            print("[{}] 释放失败: {}".format(self.name, e))

    def get_data(self):
        """获取定位数据快照"""
        return {
            "latitude": self._data["latitude"],
            "longitude": self._data["longitude"],
            "accuracy": self._data["accuracy"],
            "valid": self._data["valid"],
            "timestamp": _ticks_ms(),
        }

    def get_status(self):
        """获取模块运行状态"""
        return {
            "is_init": self.ctx["is_init"],
            "is_positioning": self.ctx["is_positioning"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python 02_Software/Tests/test_lbs_unit.py`
Expected: All 8 tests pass

- [ ] **Step 5: Commit**

```bash
git add 02_Software/Drivers/sensor/LBS.py 02_Software/Tests/test_lbs_unit.py
git commit -m "feat(nav): add LBSDriver with unit tests"
```

---

### Task 3: Create LBS E2E Test

**Files:**
- Create: `02_Software/Tests/test_lbs_e2e.py`

- [ ] **Step 1: Write e2e test**

Create `02_Software/Tests/test_lbs_e2e.py`:

```python
"""
brief LBS基站定位 端到端测试
note 需要真实硬件（EC200U + SIM卡 + 网络注册）
     1. 初始化 LBSDriver
     2. 执行定位
     3. 验证返回坐标
执行: 上传到板子运行 python test_lbs_e2e.py
"""
import sys
import time
sys.path.append("..")

from core.Event_Bus import EventBus
from core.config import EVENT_LBS_READY
from Drivers.sensor.LBS import LBSDriver


_T0 = 0

def log(msg):
    elapsed = time.ticks_diff(time.ticks_ms(), _T0)
    print("[%7.2fs] %s" % (elapsed / 1000.0, msg))


def main():
    global _T0
    _T0 = time.ticks_ms()

    print("=" * 50)
    print(" LBS 基站定位 端到端测试")
    print("=" * 50)

    bus = EventBus()
    bus.debug = True

    # 1. 初始化
    log("初始化 LBSDriver...")
    try:
        drv = LBSDriver(bus)
        drv.init()
        log("✓ LBSDriver 就绪")
    except Exception as e:
        log("✗ 初始化失败: %s" % e)
        return

    # 2. 监听事件
    results = []
    def on_lbs(data):
        results.append(data)
        log("✓ EVENT_LBS_READY: lat=%.4f lon=%.4f acc=%.0fm" % (
            data["latitude"], data["longitude"], data.get("accuracy", 0)))
    bus.subscribe(EVENT_LBS_READY, on_lbs)

    # 3. 执行定位
    log("开始定位（超时 15 秒）...")
    drv._do_positioning()
    bus.pump()

    # 4. 检查结果
    if results:
        log("✓ 定位成功")
        log("  纬度: %.4f" % results[0]["latitude"])
        log("  经度: %.4f" % results[0]["longitude"])
        log("  精度: %.0f m" % results[0].get("accuracy", 0))
    else:
        log("✗ 定位失败")
        log("  可能原因: 无 SIM 卡 / 未注册网络 / 信号太弱")

    # 5. 多次定位测试
    log("")
    log("=== 多次定位测试（3 次）===")
    for i in range(3):
        log("第 %d 次定位..." % (i + 1))
        drv._do_positioning()
        bus.pump()
        d = drv.get_data()
        if d["valid"]:
            log("  ✓ %.4f, %.4f (精度: %.0fm)" % (d["latitude"], d["longitude"], d.get("accuracy", 0)))
        else:
            log("  ✗ 失败")
        time.sleep(2)

    # 6. 清理
    drv.deinit()
    log("")
    print("=" * 50)
    print(" 测试完成")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n✓ 测试中断")
```

- [ ] **Step 2: Verify syntax**

Run: `python 02_Software/Tests/test_lbs_e2e.py`
Expected: syntax check passes (will fail at runtime without hardware)

- [ ] **Step 3: Commit**

```bash
git add 02_Software/Tests/test_lbs_e2e.py
git commit -m "feat(nav): add LBS e2e test"
```

---

### Task 4: Fix Mini Program Bug 1 — Map Navigation Polyline Binding

**Files:**
- Modify: `WeChatMiniProgram/pages/index/index.js:142-165` (NavService.onStateChange callback)

- [ ] **Step 1: Understand current code**

In `index.js` line 142-165, the `NavService.onStateChange` callback sets `navRoutePolylines` and `navDestMarker` in page data, but the `<map>` component only binds `trackPolylines` and `trackMarkers`. The navigation route is never visible on the map.

- [ ] **Step 2: Fix — merge nav polylines into track polylines in JS**

Change the `onStateChange` callback (lines 142-165) from:

```javascript
    NavService.onStateChange(function(navState) {
      var s = NavService.getState();
      var data = {
        navState: navState,
        showNavCard: navState === 'navigating' || navState === 'paused',
      };
      if (navState === 'navigating' || navState === 'paused') {
        var instr = NavService.getCurrentInstruction();
        if (instr) {
          data.navInstruction = navState === 'paused' ? '报警中，导航暂停' : instr.instruction;
          data.navCurDistance = instr.distance;
        }
        data.navRemainDistance = s.remainDistance;
        data.navRoutePolylines = MapService.buildRoutePolyline(s.routePolyline);
        if (s.dest) {
          data.navDestMarker = MapService.buildDestMarker(s.dest.lat, s.dest.lng, s.dest.name);
        }
      } else {
        data.navRoutePolylines = [];
        data.navDestMarker = [];
        data.navInstruction = '';
      }
      that.setData(data);
    });
```

To:

```javascript
    NavService.onStateChange(function(navState) {
      var s = NavService.getState();
      var data = {
        navState: navState,
        showNavCard: navState === 'navigating' || navState === 'paused',
      };
      if (navState === 'navigating' || navState === 'paused') {
        var instr = NavService.getCurrentInstruction();
        if (instr) {
          data.navInstruction = navState === 'paused' ? '报警中，导航暂停' : instr.instruction;
          data.navCurDistance = instr.distance;
        }
        data.navRemainDistance = s.remainDistance;
        var navPoly = MapService.buildRoutePolyline(s.routePolyline);
        var navMarker = s.dest ? MapService.buildDestMarker(s.dest.lat, s.dest.lng, s.dest.name) : [];
        // 合并导航路线到地图（JS 中预合并，不在 WXML 中 .concat()）
        data.trackPolylines = navPoly.concat(that.data.trackPolylines || []);
        data.trackMarkers = navMarker.concat(that.data.trackMarkers || []);
        data._navPolylines = navPoly;
        data._navMarkers = navMarker;
      } else {
        // 导航结束，恢复原始骑行轨迹
        data.trackPolylines = that.data._savedTrackPolylines || that.data.trackPolylines || [];
        data.trackMarkers = that.data._savedTrackMarkers || that.data.trackMarkers || [];
        data._navPolylines = [];
        data._navMarkers = [];
        data.navInstruction = '';
      }
      that.setData(data);
    });
```

- [ ] **Step 3: Save original track data when navigation starts**

In `_startRide()` (around line 293), after clearing track arrays, save a copy for later restoration. Add after line 305:

```javascript
    // 保存原始轨迹数据（导航结束时恢复）
    this._savedTrackPolylines = [];
    this._savedTrackMarkers = [];
```

Also, in the BLE `onData` callback (where trackPolylines/trackMarkers are updated during riding), if navigating, merge nav polylines:

In the `data.t === 0` handler, after the block that updates `trackPolylines`/`trackMarkers`, add:

```javascript
        // 如果正在导航，合并导航路线到轨迹
        if (NavService.isNavigating()) {
          var navPoly = that.data._navPolylines || [];
          var navMarker = that.data._navMarkers || [];
          u.trackPolylines = navPoly.concat(u.trackPolylines || that.data.trackPolylines || []);
          u.trackMarkers = navMarker.concat(u.trackMarkers || that.data.trackMarkers || []);
        }
```

- [ ] **Step 4: Verify**

Open in WeChat DevTools, start a ride with navigation destination. Verify green route line appears on map.

- [ ] **Step 5: Commit**

```bash
git add WeChatMiniProgram/pages/index/index.js
git commit -m "fix(nav): merge navigation polylines into map display"
```

---

### Task 5: Fix Mini Program Bug 2 — UTF-8 BLE Encoding

**Files:**
- Modify: `WeChatMiniProgram/services/ble-service.js:247-252` (_str2ab function)

- [ ] **Step 1: Understand current code**

`_str2ab()` at line 247-252 uses `charCodeAt(i)` which only handles ASCII. Chinese characters (code point > 255) get truncated when stored in `Uint8Array`.

`_str2ab` is called by `_write()` which is used by `sendNav()`, `sendCtrl()`, and `sendAck()`. All BLE writes go through this function.

- [ ] **Step 2: Fix _str2ab with TextEncoder**

Change `_str2ab` (lines 247-252) from:

```javascript
function _str2ab(str) {
  var buf = new ArrayBuffer(str.length);
  var view = new Uint8Array(buf);
  for (var i = 0; i < str.length; i++) view[i] = str.charCodeAt(i);
  return buf;
}
```

To:

```javascript
function _str2ab(str) {
  var encoder = new TextEncoder();
  return encoder.encode(str).buffer;
}
```

- [ ] **Step 3: Verify TextEncoder availability**

`TextEncoder` is available in WeChat Mini Program base library 2.10.0+. Check `app.json` for `"libVersion"` setting. If using an older version, use a polyfill instead.

- [ ] **Step 4: Test all BLE write paths**

Verify these work with Chinese content:
- `sendNav('right', 200, '中山路')` — nav with Chinese road name
- `sendCtrl('alarm_cancel')` — control command (ASCII only, should still work)
- `sendAck('test123')` — ack (ASCII only, should still work)

- [ ] **Step 5: Commit**

```bash
git add WeChatMiniProgram/services/ble-service.js
git commit -m "fix(ble): support UTF-8 encoding for Chinese road names"
```

---

### Task 6: Investigate and Fix Mini Program Bug 3 — Polyline Decoding

**Files:**
- Modify: `WeChatMiniProgram/services/navigation-service.js:200-235` (_decodePolyline, if needed)

- [ ] **Step 1: Add debug logging to confirm API return format**

In `_parseRoute()` (line 167), add before the polyline decode:

```javascript
  console.log('NAV polyline type:', typeof route.polyline, 'length:', route.polyline ? route.polyline.length : 0);
  if (route.polyline && route.polyline.length > 0) {
    console.log('NAV polyline[0]:', JSON.stringify(route.polyline[0]).substring(0, 100));
  }
```

- [ ] **Step 2: Run in WeChat DevTools and check console**

Start navigation, observe the console output:
- If `type: object, length: N` and `polyline[0]` is `{lat: X, lng: Y}` → current code handles this (object branch)
- If `type: object, length: N` and `polyline[0]` is a number → current code handles this (array branch with differential encoding)
- If `type: string` → current code is broken (parseInt branch), needs fix

- [ ] **Step 3: Fix based on findings**

**If polyline is an array of {lat, lng} objects** — current code already handles this, no fix needed. Remove debug logging.

**If polyline is a string** — replace the string branch in `_decodePolyline`:

```javascript
    if (typeof point === 'string') {
      // Google encoded polyline format - decode
      lat = 0;
      lng = 0;
      // Skip if it's a single encoded string (not array of strings)
      // This case needs full Google polyline decoder
    }
```

For a full Google polyline decoder, add this function:

```javascript
function _decodeGooglePolyline(encoded) {
  var points = [];
  var index = 0, lat = 0, lng = 0;
  while (index < encoded.length) {
    var b, shift = 0, result = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    lat += (result & 1) ? ~(result >> 1) : (result >> 1);

    shift = 0;
    result = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    lng += (result & 1) ? ~(result >> 1) : (result >> 1);

    points.push({ latitude: lat / 1e5, longitude: lng / 1e5 });
  }
  return points;
}
```

Then in `_decodePolyline`, if the input is a single string, call `_decodeGooglePolyline(polyline)`.

- [ ] **Step 4: Remove debug logging**

After confirming the fix works, remove the `console.log` lines added in Step 1.

- [ ] **Step 5: Commit**

```bash
git add WeChatMiniProgram/services/navigation-service.js
git commit -m "fix(nav): handle polyline format from Tencent Maps API"
```

---

### Task 7: Modify Navigation Coordinate Source (Subproject B)

**Files:**
- Modify: `WeChatMiniProgram/services/navigation-service.js:48-70` (startNavigation)
- Modify: `WeChatMiniProgram/pages/index/index.js:309-313` (_startRide)

- [ ] **Step 1: Modify startNavigation to accept origin parameter**

Change `startNavigation` (lines 48-70) from:

```javascript
function startNavigation(dest) {
  if (_state.state !== 'idle' && _state.state !== 'arrived' && _state.state !== 'cancelled') {
    return;
  }

  _state.state = 'planning';
  _state.dest = dest;
  _notifyState();

  logger.log('NAV', '开始规划路线 → ' + dest.name);

  wx.getLocation({
    type: 'gcj02',
    isHighAccuracy: true,
    success: function(res) {
      _fetchRoute(res.latitude, res.longitude, dest.lat, dest.lng);
    },
    fail: function() {
      // 获取当前位置失败，用默认位置
      _fetchRoute(22.5431, 113.9523, dest.lat, dest.lng);
    },
  });
}
```

To:

```javascript
function startNavigation(dest, origin) {
  if (_state.state !== 'idle' && _state.state !== 'arrived' && _state.state !== 'cancelled') {
    return;
  }

  _state.state = 'planning';
  _state.dest = dest;
  _notifyState();

  logger.log('NAV', '开始规划路线 → ' + dest.name);

  if (origin && origin.lat && origin.lng) {
    // 用板子 BLE 坐标做路线规划起点
    logger.log('NAV', '使用板子坐标: ' + origin.lat + ', ' + origin.lng);
    _fetchRoute(origin.lat, origin.lng, dest.lat, dest.lng);
  } else {
    // fallback 手机 GPS
    wx.getLocation({
      type: 'gcj02',
      isHighAccuracy: true,
      success: function(res) {
        _fetchRoute(res.latitude, res.longitude, dest.lat, dest.lng);
      },
      fail: function() {
        _fetchRoute(22.5431, 113.9523, dest.lat, dest.lng);
      },
    });
  }
}
```

- [ ] **Step 2: Modify _startRide to pass BLE coordinates**

Change `_startRide()` (lines 309-313) from:

```javascript
    // 如果选择了目的地，开始导航
    if (this._navDest) {
      NavService.startNavigation(this._navDest);
      this._navDest = null;
    }
```

To:

```javascript
    // 如果选择了目的地，开始导航（骑行中用板子坐标）
    if (this._navDest) {
      var origin = null;
      if (this.data.bleConnected && this.data.mapLat && this.data.mapLon) {
        origin = { lat: parseFloat(this.data.mapLat), lng: parseFloat(this.data.mapLon) };
        logger.log('NAV', '使用板子坐标作为起点: ' + origin.lat + ', ' + origin.lng);
      }
      NavService.startNavigation(this._navDest, origin);
      this._navDest = null;
    }
```

- [ ] **Step 3: Verify**

In WeChat DevTools, start a ride with BLE connected (or simulated). Verify route planning uses the BLE coordinates (check Network panel for the API request `from` parameter).

- [ ] **Step 4: Commit**

```bash
git add WeChatMiniProgram/services/navigation-service.js WeChatMiniProgram/pages/index/index.js
git commit -m "feat(nav): use board BLE coordinates for route planning during riding"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run all board-side tests**

```bash
cd 02_Software/Tests
python test_lbs_unit.py
python test_navigation_service.py
```
Expected: all tests pass

- [ ] **Step 2: Syntax check all modified files**

```bash
python 02_Software/Drivers/sensor/LBS.py
python 02_Software/core/config.py
```

- [ ] **Step 3: Review all changes**

```bash
git diff --stat
```

Verify: only expected files changed, no accidental modifications.

- [ ] **Step 4: Final commit**

```bash
git status
```

Ensure all changes are committed.

---

## Checklist Summary

| Task | Subproject | Files | Tests |
|------|-----------|-------|-------|
| 1. LBS config | A | config.py | syntax check |
| 2. LBSDriver | A | LBS.py, test_lbs_unit.py | 8 unit tests |
| 3. LBS e2e | A | test_lbs_e2e.py | syntax check |
| 4. Map binding | C-Bug1 | index.js | visual verify |
| 5. UTF-8 encoding | C-Bug2 | ble-service.js | BLE write test |
| 6. Polyline decode | C-Bug3 | navigation-service.js | console log verify |
| 7. Coordinate source | B | navigation-service.js, index.js | API request verify |
| 8. Final verification | All | all | all tests |
