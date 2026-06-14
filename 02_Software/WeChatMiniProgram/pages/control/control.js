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
