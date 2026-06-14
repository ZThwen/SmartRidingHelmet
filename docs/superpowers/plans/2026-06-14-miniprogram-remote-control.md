# 小程序远程控制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增独立控制页面 + eventBus 事件机制 + 自定义底部导航栏，实现小程序远程控制功能。

**Architecture:** App.js 中心化全局状态（globalData）+ EventBus 跨页面事件通知。control 页面通过 CtrlService 发送 BLE FFF3 控制指令，固件 t=7 状态回推驱动 UI 更新。自定义 TabBar 用 redirectTo 切换页面。

**Tech Stack:** 微信小程序（WXML + WXSS + JavaScript CommonJS），零 npm 依赖。

---

## File Structure

```
02_Software/WeChatMiniProgram/
├── app.js                          [修改] globalData + eventBus 初始化
├── app.json                        [修改] 注册 control 页面
├── utils/
│   └── event-bus.js                [新建] 简易事件发射器
├── custom-tab-bar/
│   ├── index.js                    [新建] TabBar 逻辑
│   ├── index.wxml                  [新建] TabBar 模板
│   └── index.wxss                  [新建] TabBar 样式
├── pages/
│   ├── index/
│   │   ├── index.js                [修改] eventBus 监听、t=7 处理
│   │   └── index.wxml              [修改] 内嵌报警弹窗模板
│   └── control/
│       ├── control.js              [新建] 控制页逻辑
│       ├── control.json            [新建] 页面配置
│       ├── control.wxml            [新建] 控制页模板
│       └── control.wxss            [新建] 控制页样式
└── services/
    └── ctrl-service.js             [已有] 直接使用
```

---

## Task 1: EventBus 工具模块

**Files:**
- Create: `02_Software/WeChatMiniProgram/utils/event-bus.js`
- Test: `02_Software/WeChatMiniProgram/Tests/test_event_bus.js`

- [ ] **Step 1: Write the failing test**

```javascript
// Tests/test_event_bus.js
var EventBus = require('../utils/event-bus');

var bus = new EventBus();
var received = null;

bus.on('test', function(data) { received = data; });
bus.emit('test', { value: 42 });

if (received === null || received.value !== 42) {
  console.log('FAIL: emit/on not working');
  process.exit(1);
}

// off 测试
var count = 0;
var fn = function() { count++; };
bus.on('count', fn);
bus.emit('count');
bus.off('count', fn);
bus.emit('count');

if (count !== 1) {
  console.log('FAIL: off not working, count=' + count);
  process.exit(1);
}

console.log('PASS: all event-bus tests');
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node 02_Software/WeChatMiniProgram/Tests/test_event_bus.js`
Expected: Error: Cannot find module '../utils/event-bus'

- [ ] **Step 3: Write implementation**

```javascript
/**
 * EventBus — 简易事件发射器
 * 用于跨页面状态通知（报警、控制状态、BLE 连接）
 */
function EventBus() {
  this._listeners = {};
}

EventBus.prototype.on = function(event, fn) {
  if (!this._listeners[event]) this._listeners[event] = [];
  this._listeners[event].push(fn);
};

EventBus.prototype.off = function(event, fn) {
  var list = this._listeners[event];
  if (!list) return;
  for (var i = list.length - 1; i >= 0; i--) {
    if (list[i] === fn) list.splice(i, 1);
  }
};

EventBus.prototype.emit = function(event, data) {
  var list = this._listeners[event];
  if (!list) return;
  for (var i = 0; i < list.length; i++) {
    list[i](data);
  }
};

module.exports = EventBus;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node 02_Software/WeChatMiniProgram/Tests/test_event_bus.js`
Expected: PASS: all event-bus tests

- [ ] **Step 5: Commit**

```bash
git add 02_Software/WeChatMiniProgram/utils/event-bus.js 02_Software/WeChatMiniProgram/Tests/test_event_bus.js
git commit -m "feat(miniprogram): add EventBus utility for cross-page events"
```

---

## Task 2: App.js 改造 — globalData + eventBus

**Files:**
- Modify: `02_Software/WeChatMiniProgram/app.js`

- [ ] **Step 1: Read current app.js to confirm baseline**

当前内容：
```javascript
App({
  globalData: {
    token: '',
    refreshToken: '',
    isRiding: false,
    rideCache: [],
    rideStartTime: 0,
  },
});
```

- [ ] **Step 2: Write updated app.js**

```javascript
/**
 * 智能骑行头盔 — 全局入口
 */
var EventBus = require('./utils/event-bus');

App({
  onLaunch: function() {
    this.eventBus = new EventBus();
  },
  globalData: {
    // 认证
    token: '',
    refreshToken: '',
    // 骑行
    isRiding: false,
    rideCache: [],
    rideStartTime: 0,
    // BLE
    bleConnected: false,
    bleStatus: '未连接',
    // 控制状态（从 t=7 回推更新）
    ctrlState: {
      lightMode: 'auto',
      lightBrightness: 0,
      volume: 5,
      powerMode: 'active',
    },
    // 报警
    alarmActive: false,
  },
});
```

- [ ] **Step 3: Verify syntax**

Run: `node -c 02_Software/WeChatMiniProgram/app.js`
Expected: no output (syntax OK)

- [ ] **Step 4: Commit**

```bash
git add 02_Software/WeChatMiniProgram/app.js
git commit -m "feat(miniprogram): add globalData fields + eventBus init"
```

---

## Task 3: app.json 注册 control 页面

**Files:**
- Modify: `02_Software/WeChatMiniProgram/app.json`

- [ ] **Step 1: Add control page to pages array**

```json
{
  "pages": [
    "pages/login/login",
    "pages/index/index",
    "pages/control/control"
  ],
  "window": {
    "navigationBarTitleText": "智能骑行头盔",
    "navigationBarBackgroundColor": "#080d17",
    "navigationBarTextStyle": "white",
    "backgroundColor": "#080d17"
  },
  "permission": {
    "scope.userLocation": {
      "desc": "获取您的位置用于地图显示"
    }
  },
  "requiredPrivateInfos": [
    "getLocation",
    "chooseLocation",
    "startLocationUpdate",
    "onLocationChange"
  ]
}
```

- [ ] **Step 2: Verify JSON syntax**

Run: `node -e "JSON.parse(require('fs').readFileSync('02_Software/WeChatMiniProgram/app.json','utf8')); console.log('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add 02_Software/WeChatMiniProgram/app.json
git commit -m "feat(miniprogram): register control page in app.json"
```

---

## Task 4: Custom TabBar 组件

**Files:**
- Create: `02_Software/WeChatMiniProgram/custom-tab-bar/index.js`
- Create: `02_Software/WeChatMiniProgram/custom-tab-bar/index.json`
- Create: `02_Software/WeChatMiniProgram/custom-tab-bar/index.wxml`
- Create: `02_Software/WeChatMiniProgram/custom-tab-bar/index.wxss`

- [ ] **Step 1: Create index.json**

```json
{
  "component": true
}
```

- [ ] **Step 2: Create index.js**

```javascript
/**
 * 自定义底部导航栏 — 骑行/控制切换 + 浮动骑行按钮
 */
var app = getApp();

Component({
  data: {
    selected: 0,  // 0=骑行, 1=控制
    riding: false,
    bleConnected: false,
    tabs: [
      { pagePath: '/pages/index/index', text: '骑行', icon: '🚴' },
      { pagePath: '/pages/control/control', text: '控制', icon: '⚙' },
    ],
  },

  methods: {
    switchTab: function(e) {
      var index = e.currentTarget.dataset.index;
      var tab = this.data.tabs[index];
      if (this.data.selected === index) return;
      wx.redirectTo({ url: tab.pagePath });
    },

    onRideBtn: function() {
      // 控制页点击骑行按钮 → 跳回骑行页
      if (this.data.selected === 1) {
        wx.redirectTo({ url: '/pages/index/index' });
        return;
      }
      // 骑行页 → 触发页面的 onToggleRide
      var pages = getCurrentPages();
      var current = pages[pages.length - 1];
      if (current && current.onToggleRide) {
        current.onToggleRide();
      }
    },
  },

  pageLifetimes: {
    show: function() {
      var globalData = app.globalData;
      this.setData({
        riding: globalData.isRiding,
        bleConnected: globalData.bleConnected,
      });
    },
  },
});
```

- [ ] **Step 3: Create index.wxml**

```xml
<view class="tabbar-container">
  <!-- 浮动骑行按钮 -->
  <view class="ride-btn-wrap">
    <button class="ride-btn {{riding ? 'end' : 'start'}}" bindtap="onRideBtn">
      <text>{{riding ? '结束骑行' : '开始骑行'}}</text>
    </button>
  </view>
  <!-- Tab 栏 -->
  <view class="tab-bar">
    <view class="tab-item {{selected === index ? 'active' : ''}}"
          wx:for="{{tabs}}" wx:key="pagePath"
          data-index="{{index}}" bindtap="switchTab">
      <text class="tab-icon">{{item.icon}}</text>
      <text class="tab-label">{{item.text}}</text>
    </view>
  </view>
</view>
```

- [ ] **Step 4: Create index.wxss**

```css
.tabbar-container {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
}

.ride-btn-wrap {
  display: flex;
  justify-content: center;
  padding: 0 24rpx;
  margin-bottom: 8rpx;
}

.ride-btn {
  width: 100%;
  height: 96rpx;
  border-radius: 48rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  line-height: 1;
}

.ride-btn text {
  font-size: 30rpx;
  font-weight: 700;
  letter-spacing: 4rpx;
}

.ride-btn.start {
  background: transparent;
  border: 2rpx solid #66ccff;
}

.ride-btn.start text {
  color: #66ccff;
}

.ride-btn.end {
  background: linear-gradient(90deg, #ff4444, #cc0000);
}

.ride-btn.end text {
  color: #fff;
}

.tab-bar {
  height: 112rpx;
  background: rgba(8, 13, 23, 0.96);
  border-top: 1rpx solid rgba(102, 204, 255, 0.12);
  display: flex;
  align-items: center;
  padding-bottom: env(safe-area-inset-bottom, 0);
}

.tab-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4rpx;
  padding: 8rpx 0;
}

.tab-icon {
  font-size: 40rpx;
}

.tab-label {
  font-size: 20rpx;
  font-weight: 600;
  letter-spacing: 1rpx;
  color: #3a5068;
}

.tab-item.active .tab-label {
  color: #66ccff;
}
```

- [ ] **Step 5: Verify files exist**

Run: `ls 02_Software/WeChatMiniProgram/custom-tab-bar/`
Expected: index.js index.json index.wxml index.wxss

- [ ] **Step 6: Commit**

```bash
git add 02_Software/WeChatMiniProgram/custom-tab-bar/
git commit -m "feat(miniprogram): add custom tab bar component"
```

---

## Task 5: Control 页面 — JS 逻辑

**Files:**
- Create: `02_Software/WeChatMiniProgram/pages/control/control.js`
- Create: `02_Software/WeChatMiniProgram/pages/control/control.json`

- [ ] **Step 1: Create control.json**

```json
{
  "usingComponents": {},
  "navigationStyle": "custom"
}
```

- [ ] **Step 2: Create control.js**

```javascript
/**
 * 远端控制页 — 灯光/音量/电源控制
 */
var CtrlService = require('../../services/ctrl-service');
var NavService = require('../../services/navigation-service');
var logger = require('../../utils/logger');
var app = getApp();

Page({
  data: {
    // 安全区域
    statusBarHeight: 44,
    // 控制状态
    lightMode: 'auto',
    lightBrightness: 0,
    volume: 5,
    powerMode: 'active',
    // BLE
    bleConnected: false,
    bleStatus: '未连接',
    deviceName: '',
    // 导航
    showNavIndicator: false,
    navInstruction: '',
    navRemainDistance: 0,
    // 骑行
    riding: false,
    // 报警
    showAlarmPopup: false,
    alarmPopupData: {},
  },

  onLoad: function() {
    var sysInfo = wx.getSystemInfoSync();
    this.setData({ statusBarHeight: sysInfo.statusBarHeight || 44 });
    this._syncFromGlobal();
    this._bindEvents();
  },

  onShow: function() {
    // 更新 TabBar 选中态
    var tabbar = this.getTabBar();
    if (tabbar) tabbar.setData({ selected: 1 });
    this._syncFromGlobal();
  },

  onUnload: function() {
    this._unbindEvents();
  },

  _syncFromGlobal: function() {
    var gd = app.globalData;
    var cs = gd.ctrlState;
    this.setData({
      bleConnected: gd.bleConnected,
      bleStatus: gd.bleStatus,
      deviceName: gd.bleConnected ? 'SmartHelmet-66ccff' : '',
      lightMode: cs.lightMode,
      lightBrightness: cs.lightBrightness,
      volume: cs.volume,
      powerMode: cs.powerMode,
      riding: gd.isRiding,
      showAlarmPopup: gd.alarmActive,
    });
    // 同步导航状态
    if (NavService.isNavigating()) {
      var s = NavService.getState();
      var instr = NavService.getCurrentInstruction();
      this.setData({
        showNavIndicator: true,
        navInstruction: instr ? instr.instruction : '',
        navRemainDistance: s.remainDistance,
      });
    } else {
      this.setData({ showNavIndicator: false });
    }
  },

  _bindEvents: function() {
    var that = this;
    var bus = app.eventBus;
    if (!bus) return;

    this._onCtrlState = function(state) {
      that.setData({
        lightMode: state.lightMode,
        lightBrightness: state.brightness,
        volume: state.volume,
        powerMode: state.powerMode,
      });
    };

    this._onAlarmTriggered = function() {
      that.setData({ showAlarmPopup: true });
    };

    this._onAlarmCancelled = function() {
      that.setData({ showAlarmPopup: false });
    };

    this._onBleDisconnected = function() {
      that.setData({
        bleConnected: false,
        bleStatus: '已断开',
        deviceName: '',
      });
      CtrlService.reset();
      that._syncFromGlobal();
    };

    this._onBleConnected = function() {
      that.setData({
        bleConnected: true,
        bleStatus: '已连接',
        deviceName: 'SmartHelmet-66ccff',
      });
    };

    bus.on('ctrl:stateChanged', this._onCtrlState);
    bus.on('alarm:triggered', this._onAlarmTriggered);
    bus.on('alarm:cancelled', this._onAlarmCancelled);
    bus.on('ble:disconnected', this._onBleDisconnected);
    bus.on('ble:connected', this._onBleConnected);
  },

  _unbindEvents: function() {
    var bus = app.eventBus;
    if (!bus) return;
    bus.off('ctrl:stateChanged', this._onCtrlState);
    bus.off('alarm:triggered', this._onAlarmTriggered);
    bus.off('alarm:cancelled', this._onAlarmCancelled);
    bus.off('ble:disconnected', this._onBleDisconnected);
    bus.off('ble:connected', this._onBleConnected);
  },

  // ==================== 灯光控制 ====================

  onLightMode: function(e) {
    var mode = e.currentTarget.dataset.mode;
    if (mode === 'auto') {
      CtrlService.lightAuto();
    }
  },

  onLightOn: function() {
    if (this.data.lightMode === 'auto') return;
    CtrlService.lightOn();
  },

  onLightOff: function() {
    if (this.data.lightMode === 'auto') return;
    CtrlService.lightOff();
  },

  onBrightnessUp: function() {
    if (this.data.lightMode === 'auto') return;
    CtrlService.brightnessUp();
  },

  onBrightnessDown: function() {
    if (this.data.lightMode === 'auto') return;
    CtrlService.brightnessDown();
  },

  // ==================== 音量控制 ====================

  onVolumeUp: function() {
    CtrlService.volumeUp();
  },

  onVolumeDown: function() {
    CtrlService.volumeDown();
  },

  // ==================== 电源控制 ====================

  onPowerMode: function(e) {
    var mode = e.currentTarget.dataset.mode;
    if (mode === 'save') {
      CtrlService.powerSave();
    } else {
      CtrlService.powerNormal();
    }
  },

  // ==================== 导航 ====================

  onNavIndicatorTap: function() {
    wx.redirectTo({ url: '/pages/index/index' });
  },

  // ==================== 报警 ====================

  onCancelAlarm: function() {
    this.setData({ showAlarmPopup: false });
    var BleService = require('../../services/ble-service');
    if (BleService.isConnected()) {
      BleService.sendCtrl('alarm_cancel');
    }
  },

  // ==================== 导航栏 ====================

  onBackPress: function() {
    wx.redirectTo({ url: '/pages/index/index' });
  },
});
```

- [ ] **Step 3: Verify syntax**

Run: `node -c 02_Software/WeChatMiniProgram/pages/control/control.js`
Expected: no output (syntax OK)

- [ ] **Step 4: Commit**

```bash
git add 02_Software/WeChatMiniProgram/pages/control/control.js 02_Software/WeChatMiniProgram/pages/control/control.json
git commit -m "feat(miniprogram): add control page JS logic"
```

---

## Task 6: Control 页面 — WXML 模板

**Files:**
- Create: `02_Software/WeChatMiniProgram/pages/control/control.wxml`

- [ ] **Step 1: Create control.wxml**

```xml
<!-- 远端控制页 (Tactical Cyan) -->
<view class="page" style="padding-top: {{statusBarHeight}}px;">

  <!-- 自定义导航栏 -->
  <view class="nav-bar" style="top: {{statusBarHeight}}px;">
    <view class="nav-back" bindtap="onBackPress" hover-class="nav-back-hover">‹ 返回</view>
    <view class="nav-title">
      <text class="deco">≋</text>
      <text>远端控制</text>
      <text class="deco">≋</text>
    </view>
    <view class="nav-spacer"></view>
  </view>

  <!-- 导航状态条（仅导航中显示） -->
  <view class="ctrl-nav-indicator" wx:if="{{showNavIndicator}}" bindtap="onNavIndicatorTap">
    <text class="ctrl-nav-icon">→</text>
    <view class="ctrl-nav-text">
      <text class="ctrl-nav-instruction">{{navInstruction}}</text>
      <text class="ctrl-nav-remain">剩余 {{navRemainDistance}}m</text>
    </view>
    <text class="ctrl-nav-goto">查看地图 ›</text>
  </view>

  <!-- 内容区 -->
  <scroll-view class="ctrl-scroll" scroll-y="{{true}}" enhanced="{{true}}" show-scrollbar="{{false}}">

    <!-- 灯光控制 -->
    <view class="ctrl-section">
      <view class="ctrl-section-title">
        <text>灯光控制</text>
        <view class="deco-line"></view>
      </view>

      <!-- 模式切换 -->
      <view class="toggle-group">
        <view class="toggle-btn {{lightMode === 'auto' ? 'active' : ''}}"
              data-mode="auto" bindtap="onLightMode">
          <text>自动</text>
        </view>
        <view class="toggle-btn {{lightMode === 'manual' ? 'active' : ''}}"
              data-mode="manual" bindtap="onLightMode">
          <text>手动</text>
        </view>
      </view>

      <!-- 开关灯 -->
      <view class="toggle-group">
        <view class="toggle-btn {{lightMode === 'auto' ? 'disabled' : ''}}"
              bindtap="onLightOn">
          <text>开灯</text>
        </view>
        <view class="toggle-btn {{lightMode === 'auto' ? 'disabled' : ''}}"
              bindtap="onLightOff">
          <text>关灯</text>
        </view>
      </view>

      <!-- 亮度滑条 -->
      <view class="slider-row {{lightMode === 'auto' ? 'disabled' : ''}}">
        <view class="slider-btn" bindtap="onBrightnessDown"><text>◀</text></view>
        <view class="slider-track">
          <view class="slider-fill" style="width: {{lightBrightness}}%;"></view>
        </view>
        <text class="slider-value">{{lightBrightness}}%</text>
        <view class="slider-btn" bindtap="onBrightnessUp"><text>▶</text></view>
      </view>
    </view>

    <!-- 音量控制 -->
    <view class="ctrl-section">
      <view class="ctrl-section-title">
        <text>音量控制</text>
        <view class="deco-line"></view>
      </view>
      <view class="volume-display">
        <view class="vol-btn {{volume <= 0 ? 'disabled' : ''}}" bindtap="onVolumeDown"><text>▼</text></view>
        <view class="vol-level">
          <view class="vol-bar {{volume >= 1 ? 'active' : ''}}" style="height: 16rpx;"></view>
          <view class="vol-bar {{volume >= 2 ? 'active' : ''}}" style="height: 28rpx;"></view>
          <view class="vol-bar {{volume >= 3 ? 'active' : ''}}" style="height: 40rpx;"></view>
          <view class="vol-bar {{volume >= 4 ? 'active' : ''}}" style="height: 52rpx;"></view>
          <view class="vol-bar {{volume >= 5 ? 'active' : ''}}" style="height: 64rpx;"></view>
          <view class="vol-bar {{volume >= 6 ? 'active' : ''}}" style="height: 76rpx;"></view>
          <view class="vol-bar {{volume >= 7 ? 'active' : ''}}" style="height: 88rpx;"></view>
        </view>
        <text class="vol-value">{{volume}}/7</text>
        <view class="vol-btn {{volume >= 7 ? 'disabled' : ''}}" bindtap="onVolumeUp"><text>▲</text></view>
      </view>
    </view>

    <!-- 电源模式 -->
    <view class="ctrl-section">
      <view class="ctrl-section-title">
        <text>电源模式</text>
        <view class="deco-line"></view>
      </view>
      <view class="toggle-group">
        <view class="toggle-btn {{powerMode === 'active' ? 'active' : ''}}"
              data-mode="active" bindtap="onPowerMode">
          <text>正常</text>
        </view>
        <view class="toggle-btn {{powerMode === 'suspended' ? 'active' : ''}}"
              data-mode="save" bindtap="onPowerMode">
          <text>省电</text>
        </view>
      </view>
    </view>

    <!-- 连接状态 -->
    <view class="ctrl-section">
      <view class="ctrl-section-title">
        <text>连接状态</text>
        <view class="deco-line"></view>
      </view>
      <view class="conn-status">
        <view class="conn-dot {{bleConnected ? 'on' : 'off'}}"></view>
        <view class="conn-info">
          <text class="conn-name">{{bleConnected ? deviceName : '未连接'}}</text>
          <text class="conn-detail">{{bleConnected ? 'BLE 已连接' : '请检查蓝牙'}}</text>
        </view>
      </view>
    </view>

    <view style="height: 320rpx;"></view>
  </scroll-view>

  <!-- BLE 未连接遮罩（全局） -->
  <view class="ble-overlay" wx:if="{{!bleConnected}}">
    <text class="ble-overlay-text">BLE 未连接，请先连接设备</text>
  </view>

  <!-- 报警弹窗 -->
  <view class="alarm-popup" wx:if="{{showAlarmPopup}}">
    <view class="alarm-pulse-border"></view>
    <view class="alarm-popup-body">
      <view class="alarm-icon-wrap">
        <view class="alarm-icon-ring"></view>
        <text class="alarm-icon">⚡</text>
      </view>
      <text class="alarm-type">报警触发</text>
      <view class="alarm-cancel-btn" bindtap="onCancelAlarm">
        <text>取消报警</text>
      </view>
    </view>
  </view>

  <!-- 自定义 TabBar -->
  <custom-tab-bar></custom-tab-bar>
</view>
```

- [ ] **Step 2: Verify WXML well-formedness**

Visual check in WeChat Developer Tools.

- [ ] **Step 3: Commit**

```bash
git add 02_Software/WeChatMiniProgram/pages/control/control.wxml
git commit -m "feat(miniprogram): add control page WXML template"
```

---

## Task 7: Control 页面 — WXSS 样式

**Files:**
- Create: `02_Software/WeChatMiniProgram/pages/control/control.wxss`

- [ ] **Step 1: Create control.wxss**

```css
/* control.wxss — 远端控制页 (Tactical Cyan) */
page {
  background: #080d17;
  color: #e0f0ff;
}

.page {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

/* ===== 导航栏 ===== */
.nav-bar {
  display: flex;
  align-items: center;
  height: 88rpx;
  padding: 0 16rpx;
  position: fixed;
  left: 0; right: 0;
  z-index: 99;
  background: rgba(8, 13, 23, 0.92);
}

.nav-back {
  font-size: 32rpx;
  color: #5a7a98;
  padding: 12rpx 20rpx;
  min-width: 100rpx;
}

.nav-title {
  flex: 1;
  text-align: center;
  font-size: 28rpx;
  font-weight: 600;
  color: #e0f0ff;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12rpx;
  margin-right: 140rpx;
}

.nav-title .deco {
  font-size: 22rpx;
  color: rgba(102, 204, 255, 0.4);
}

.nav-spacer { min-width: 100rpx; }

/* ===== 导航状态条 ===== */
.ctrl-nav-indicator {
  margin: 16rpx 20rpx 8rpx;
  padding: 16rpx 20rpx;
  background: rgba(102, 204, 255, 0.06);
  border: 1rpx solid rgba(102, 204, 255, 0.15);
  border-radius: 12rpx;
  display: flex;
  align-items: center;
  gap: 16rpx;
}

.ctrl-nav-icon {
  font-size: 36rpx;
  color: #66ccff;
}

.ctrl-nav-text { flex: 1; }
.ctrl-nav-instruction {
  display: block;
  font-size: 26rpx;
  color: #e0f0ff;
  font-weight: 600;
}
.ctrl-nav-remain {
  display: block;
  font-size: 22rpx;
  color: #5a7a98;
  margin-top: 4rpx;
}

.ctrl-nav-goto {
  font-size: 22rpx;
  color: #66ccff;
  letter-spacing: 1rpx;
}

/* ===== 滚动内容 ===== */
.ctrl-scroll {
  flex: 1;
  padding: 0 20rpx;
}

/* ===== 控制区块 ===== */
.ctrl-section {
  position: relative;
  background: rgba(12, 20, 36, 0.85);
  border: 1rpx solid rgba(102, 204, 255, 0.12);
  border-radius: 16rpx;
  padding: 24rpx 28rpx;
  margin-bottom: 16rpx;
}

.ctrl-section-title {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-bottom: 20rpx;
  font-size: 24rpx;
  font-weight: 600;
  color: #7a9a98;
  letter-spacing: 2rpx;
}

.deco-line {
  flex: 1;
  height: 1rpx;
  background: linear-gradient(90deg, rgba(102, 204, 255, 0.25), transparent);
}

/* ===== 切换按钮组 ===== */
.toggle-group {
  display: flex;
  gap: 12rpx;
  margin-bottom: 16rpx;
}

.toggle-btn {
  flex: 1;
  padding: 16rpx 20rpx;
  border: 1rpx solid rgba(102, 204, 255, 0.12);
  border-radius: 12rpx;
  text-align: center;
  background: transparent;
}

.toggle-btn text {
  font-size: 26rpx;
  font-weight: 600;
  color: #5a7a98;
  letter-spacing: 1rpx;
}

.toggle-btn.active {
  background: rgba(102, 204, 255, 0.12);
  border-color: #66ccff;
}

.toggle-btn.active text {
  color: #66ccff;
}

.toggle-btn.disabled {
  opacity: 0.35;
}

/* ===== 亮度滑条 ===== */
.slider-row {
  display: flex;
  align-items: center;
  gap: 16rpx;
  margin-top: 8rpx;
}

.slider-row.disabled {
  opacity: 0.35;
  pointer-events: none;
}

.slider-btn {
  width: 60rpx;
  height: 60rpx;
  border: 1rpx solid rgba(102, 204, 255, 0.2);
  border-radius: 12rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.slider-btn text {
  font-size: 28rpx;
  color: #66ccff;
}

.slider-track {
  flex: 1;
  height: 16rpx;
  background: rgba(102, 204, 255, 0.08);
  border-radius: 8rpx;
  overflow: hidden;
}

.slider-fill {
  height: 100%;
  background: linear-gradient(90deg, #66ccff, #00ffff);
  border-radius: 8rpx;
  transition: width 0.3s ease;
}

.slider-value {
  font-size: 26rpx;
  color: #e0f0ff;
  min-width: 70rpx;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* ===== 音量控制 ===== */
.volume-display {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24rpx;
  padding: 12rpx 0;
}

.vol-btn {
  width: 72rpx;
  height: 72rpx;
  border: 1rpx solid rgba(102, 204, 255, 0.2);
  border-radius: 16rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.vol-btn text {
  font-size: 32rpx;
  color: #66ccff;
}

.vol-btn.disabled {
  opacity: 0.3;
}

.vol-level {
  display: flex;
  gap: 6rpx;
  align-items: flex-end;
}

.vol-bar {
  width: 24rpx;
  border-radius: 4rpx;
  background: rgba(102, 204, 255, 0.1);
  transition: background 0.3s ease;
}

.vol-bar.active {
  background: #66ccff;
  box-shadow: 0 0 8rpx rgba(102, 204, 255, 0.4);
}

.vol-value {
  font-size: 28rpx;
  color: #e0f0ff;
  min-width: 60rpx;
  text-align: center;
}

/* ===== 连接状态 ===== */
.conn-status {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 8rpx 0;
}

.conn-dot {
  width: 16rpx;
  height: 16rpx;
  border-radius: 50%;
  flex-shrink: 0;
}

.conn-dot.on {
  background: #00d4aa;
  box-shadow: 0 0 10rpx rgba(0, 212, 170, 0.5);
}

.conn-dot.off {
  background: #ff2a4d;
  box-shadow: 0 0 10rpx rgba(255, 42, 77, 0.5);
}

.conn-info { flex: 1; }
.conn-name {
  display: block;
  font-size: 28rpx;
  color: #e0f0ff;
  font-weight: 600;
}
.conn-detail {
  display: block;
  font-size: 22rpx;
  color: #5a7a98;
  margin-top: 4rpx;
}

/* ===== BLE 未连接遮罩 ===== */
.ble-overlay {
  position: fixed;
  bottom: 320rpx;
  left: 20rpx;
  right: 20rpx;
  background: rgba(8, 13, 23, 0.85);
  border: 1rpx solid rgba(255, 42, 77, 0.3);
  border-radius: 16rpx;
  padding: 24rpx;
  text-align: center;
  z-index: 50;
}

.ble-overlay-text {
  font-size: 26rpx;
  color: #ff2a4d;
  letter-spacing: 1rpx;
}

/* ===== 报警弹窗（复用 index 样式） ===== */
.alarm-popup {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  z-index: 998;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, rgba(180, 0, 0, 0.95), rgba(120, 0, 0, 0.98));
}

.alarm-pulse-border {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  border: 4rpx solid rgba(255, 61, 0, 0.6);
  animation: pulseBorder 1.2s ease-in-out infinite;
  pointer-events: none;
}

@keyframes pulseBorder {
  0%, 100% { border-color: rgba(255, 61, 0, 0.6); }
  50% { border-color: rgba(255, 61, 0, 1); }
}

.alarm-popup-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 48rpx;
  z-index: 10;
}

.alarm-icon-wrap {
  width: 160rpx; height: 160rpx;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 32rpx;
}

.alarm-icon {
  font-size: 80rpx;
  z-index: 2;
}

.alarm-icon-ring {
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  border: 3rpx solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  animation: ringPulse 1.5s ease-in-out infinite;
}

@keyframes ringPulse {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50% { transform: scale(1.15); opacity: 0.1; }
}

.alarm-type {
  font-size: 48rpx;
  font-weight: 900;
  color: #fff;
  letter-spacing: 4rpx;
  margin-bottom: 40rpx;
}

.alarm-cancel-btn {
  padding: 20rpx 48rpx;
  border: 2rpx solid rgba(255, 255, 255, 0.3);
  border-radius: 12rpx;
}

.alarm-cancel-btn text {
  font-size: 28rpx;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.8);
  letter-spacing: 2rpx;
}
```

- [ ] **Step 2: Commit**

```bash
git add 02_Software/WeChatMiniProgram/pages/control/control.wxss
git commit -m "feat(miniprogram): add control page WXSS styles"
```

---

## Task 8: Index 页面改造 — eventBus + 报警弹窗

**Files:**
- Modify: `02_Software/WeChatMiniProgram/pages/index/index.js`
- Modify: `02_Software/WeChatMiniProgram/pages/index/index.wxml`

- [ ] **Step 1: Read current index.js to identify modification points**

需要修改的部分：
1. 添加 eventBus import 和 CtrlService import
2. onLoad 中绑定 eventBus 监听
3. onUnload 中解绑
4. onData 中新增 t=7 处理
5. BLE 断连时 emit 事件
6. BLE 连接时 emit 事件

- [ ] **Step 2: index.js — 添加 import**

在文件顶部现有 require 之后添加：
```javascript
var CtrlService = require('../../services/ctrl-service');
```

- [ ] **Step 3: index.js — onLoad 中初始化 eventBus 监听**

在 onLoad 函数中，现有代码之后添加：
```javascript
// eventBus 监听
var bus = app.eventBus;
if (bus) {
  that._onAlarmTriggered = function() {
    that.setData({ showAlarmPopup: true, alarmPopupClass: 'alarm-popup' });
  };
  that._onAlarmCancelled = function() {
    that.setData({ showAlarmPopup: false, alarm: '正常' });
  };
  bus.on('alarm:triggered', that._onAlarmTriggered);
  bus.on('alarm:cancelled', that._onAlarmCancelled);
}
```

- [ ] **Step 4: index.js — onUnload 中解绑**

在 onUnload 中添加：
```javascript
var bus = app.eventBus;
if (bus) {
  bus.off('alarm:triggered', this._onAlarmTriggered);
  bus.off('alarm:cancelled', this._onAlarmCancelled);
}
```

- [ ] **Step 5: index.js — onData 中新增 t=7 处理**

在 `data.t === 6` 分支之后添加：
```javascript
else if (data.t === 7) {
  var state = CtrlService.parseCtrlState(data);
  if (state && app.globalData) {
    app.globalData.ctrlState = state;
    if (app.eventBus) app.eventBus.emit('ctrl:stateChanged', state);
  }
}
```

- [ ] **Step 6: index.js — BLE 连接/断连 emit 事件**

在 onConnected 回调中添加：
```javascript
app.globalData.bleConnected = true;
app.globalData.bleStatus = '已连接';
if (app.eventBus) app.eventBus.emit('ble:connected');
```

在 onDisconnected 回调中添加：
```javascript
app.globalData.bleConnected = false;
app.globalData.bleStatus = '已断开';
CtrlService.reset();
if (app.eventBus) app.eventBus.emit('ble:disconnected');
```

- [ ] **Step 7: index.js — TabBar 选中态**

在 onShow 中添加：
```javascript
var tabbar = this.getTabBar();
if (tabbar) tabbar.setData({ selected: 0 });
```

- [ ] **Step 8: index.wxml — 添加 TabBar 引用**

在 `</view>` 闭合标签之前（页面最底部）添加：
```xml
<custom-tab-bar></custom-tab-bar>
```

- [ ] **Step 9: index.json — 注册 custom-tab-bar 组件**

读取现有 index.json，添加 usingComponents：
```json
{
  "usingComponents": {
    "custom-tab-bar": "../../custom-tab-bar/index"
  }
}
```

- [ ] **Step 10: Verify syntax**

Run: `node -c 02_Software/WeChatMiniProgram/pages/index/index.js`
Expected: no output

- [ ] **Step 11: Commit**

```bash
git add 02_Software/WeChatMiniProgram/pages/index/index.js 02_Software/WeChatMiniProgram/pages/index/index.wxml 02_Software/WeChatMiniProgram/pages/index/index.json
git commit -m "feat(miniprogram): integrate eventBus + alarm popup + tab bar into index page"
```

---

## Task 9: 文档更新

**Files:**
- Modify: `02_Software/WeChatMiniProgram/doc/requirements.md`
- Modify: `02_Software/WeChatMiniProgram/doc/architecture.md`

- [ ] **Step 1: requirements.md — 更新 R11**

将 R11 从"首页内嵌面板"改为：

```markdown
## R11 远端控制 *(✅ 已实现)*

**R11.1 控制页面**
- 独立控制页面（pages/control/control）
- 自定义底部 TabBar 切换骑行/控制页
- 灯光控制：自动/手动模式、开/关灯、亮度 0-100%（100%=PWM50%）
- 音量控制：0-7 级
- 电源模式：正常/省电
- BLE 未连接时所有控制禁用

**R11.2 指令下发**
- 通过 BLE FFF3 `sendCtrl(cmd)` 下发控制指令
- 指令格式：`{"a":"ctrl","d":{"cmd":"<command>"}}`
- 固件执行后通过 t=7 回推状态

**R11.3 状态同步**
- App.js globalData 持有 ctrlState
- EventBus 跨页面事件通知
- 页面 onShow 时从 globalData 同步
```

- [ ] **Step 2: architecture.md — 新增组件**

在 C3 组件表中添加：

```
| RemoteControlComponent | 控制面板 UI + BLE FFF3 指令下发 | pages/control/control.js |
| EventBus | 跨页面事件通知 | utils/event-bus.js |
| CustomTabBar | 底部骑行/控制切换 | custom-tab-bar/ |
```

- [ ] **Step 3: architecture.md — 更新架构约束**

全局状态从 5 个更新为 7 个。

- [ ] **Step 4: Commit**

```bash
git add 02_Software/WeChatMiniProgram/doc/requirements.md 02_Software/WeChatMiniProgram/doc/architecture.md
git commit -m "docs: update R11 requirements and architecture for remote control"
```

---

## Task 10: 端到端验证

- [ ] **Step 1: 微信开发者工具编译**

打开微信开发者工具，导入 `02_Software/WeChatMiniProgram/` 目录，编译预览。

- [ ] **Step 2: 验证页面切换**

点击底部 TabBar「控制」→ 跳转控制页 → 点击「骑行」→ 跳回骑行页。

- [ ] **Step 3: 验证控制功能**

连接头盔 BLE → 控制页 → 点击灯光/音量/电源按钮 → 观察头盔反应。

- [ ] **Step 4: 验证状态回推**

发送控制指令后，观察 UI 状态是否随 t=7 回推更新。

- [ ] **Step 5: 验证报警跨页**

触发报警 → 控制页显示弹窗 → 取消报警 → 弹窗关闭。

- [ ] **Step 6: 验证导航不中断**

导航中切换到控制页 → 导航状态条显示 → 切回骑行页 → 导航继续。
