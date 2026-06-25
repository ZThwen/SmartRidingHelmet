/**
 * 远端控制页 — 灯光/音量/电源控制
 *
 * P1 修复: 统一使用 StateService EventBus 事件
 * 事件名变更:
 *   alarm:triggered → state:alarmTriggered
 *   alarm:cancelled → state:alarmCancelled
 *   ctrl:stateChanged → state:ctrlChanged
 *   ble:connected → ble:connected (不变)
 *   ble:disconnected → ble:disconnected (不变)
 */
var BleService = require('../../services/ble-service');
var CtrlService = require('../../services/ctrl-service');
var NavService = require('../../services/navigation-service');
var StateService = require('../../services/state-service');
var logger = require('../../utils/logger');
var app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    lightMode: 'auto',
    lightBrightness: 0,
    volume: 5,
    powerMode: 'active',
    alarmMode: 'normal',
    alarmActive: false,
    showAlarmPopup: false,
    bleConnected: false,
    bleStatus: '未连接',
    deviceName: '',
    showNavIndicator: false,
    navInstruction: '',
    navRemainDistance: 0,
    riding: false,
    lightBlink: false,
    brightnessDisplay: '0%',
    emergencyPhone: '',
    emergencyPhoneSaved: '',
    emergencyPhoneInput: '',
  },

  onLoad: function() {
    var sysInfo = wx.getSystemInfoSync();
    var safeTop = sysInfo.safeArea ? sysInfo.safeArea.top : (sysInfo.statusBarHeight || 44);
    logger.log('CTRL', 'onLoad safeTop=' + safeTop);
    this.setData({ statusBarHeight: safeTop });
    this._bindEvents();
  },

  onShow: function() {
    logger.log('CTRL', 'onShow');
    // 从 StateService 同步全局状态
    var syncData = StateService.syncToPageData();
    // 控制页额外补充
    syncData.deviceName = syncData.bleConnected ? 'SmartHelmet-66ccff' : '';
    syncData.showAlarmPopup = syncData.alarmActive;
    this.setData(syncData);
    // 同步紧急联系人号码（本地缓存）
    var savedPhone = app.globalData.smsPhone || '';
    syncData.emergencyPhoneSaved = savedPhone;
    syncData.emergencyPhoneInput = savedPhone;
    this.setData(syncData);

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

    // 重新注册 NavService 回调（index 页 onShow 可能覆盖了本页的回调）
    NavService.onStateChange(this._onNavStateChange);

    this._syncTabBar();
  },

  onUnload: function() {
    logger.log('CTRL', 'onUnload');
    this._unbindEvents();
  },

  // ==================== EventBus 绑定 ====================

  _bindEvents: function() {
    var that = this;
    var bus = app.eventBus;
    if (!bus) { logger.log('CTRL', '_bindEvents no bus'); return; }

    // 控制状态变更
    this._onCtrlChanged = function(state) {
      logger.log('CTRL', 'event state:ctrlChanged mode=' + state.lightMode +
        ' bri=' + state.brightness + ' vol=' + state.volume + ' pwr=' + state.powerMode +
        ' blink=' + state.blink);
      that.setData({
        lightMode: state.lightMode,
        lightBrightness: state.brightness,
        lightBlink: state.blink,
        brightnessDisplay: that._calcBrightnessDisplay(state.blink, state.brightness),
        volume: state.volume,
        powerMode: state.powerMode,
      });
    };

    // 报警触发
    this._onAlarmTriggered = function(evt) {
      logger.log('CTRL', 'event state:alarmTriggered');
      that.setData({ alarmActive: true, showAlarmPopup: true, alarm: evt.displayText });
      that._syncTabBar();
    };

    // 报警取消
    this._onAlarmCancelled = function() {
      logger.log('CTRL', 'event state:alarmCancelled');
      that.setData({ alarmActive: false, showAlarmPopup: false, alarm: '正常' });
      that._syncTabBar();
    };

    // BLE 断开
    this._onBleDisconnected = function() {
      logger.log('CTRL', 'event ble:disconnected');
      that.setData({ bleConnected: false, bleStatus: '已断开', deviceName: '' });
      CtrlService.reset();
      that._syncTabBar();
    };

    // BLE 连接
    this._onBleConnected = function() {
      logger.log('CTRL', 'event ble:connected');
      that.setData({ bleConnected: true, bleStatus: '已连接', deviceName: 'SmartHelmet-66ccff' });
      that._syncTabBar();
    };

    // 导航状态变化
    this._onNavStateChange = function(navState) {
      logger.log('CTRL', 'event navState: ' + navState);
      if (NavService.isNavigating()) {
        var s = NavService.getState();
        var instr = NavService.getCurrentInstruction();
        that.setData({
          showNavIndicator: true,
          navInstruction: instr ? instr.instruction : '',
          navRemainDistance: s.remainDistance,
        });
      } else {
        that.setData({ showNavIndicator: false });
      }
      that._syncTabBar();
    };

    bus.on('state:ctrlChanged', this._onCtrlChanged);
    bus.on('state:alarmTriggered', this._onAlarmTriggered);
    bus.on('state:alarmCancelled', this._onAlarmCancelled);
    bus.on('ble:disconnected', this._onBleDisconnected);
    bus.on('ble:connected', this._onBleConnected);
    NavService.onStateChange(this._onNavStateChange);
    logger.log('CTRL', '_bindEvents OK');
  },

  _unbindEvents: function() {
    var bus = app.eventBus;
    if (!bus) return;
    bus.off('state:ctrlChanged', this._onCtrlChanged);
    bus.off('state:alarmTriggered', this._onAlarmTriggered);
    bus.off('state:alarmCancelled', this._onAlarmCancelled);
    bus.off('ble:disconnected', this._onBleDisconnected);
    bus.off('ble:connected', this._onBleConnected);
    NavService.onStateChange(null);
  },

  _syncTabBar: function() {
    var tabBar = this.getTabBar();
    if (!tabBar) return;
    if (tabBar.updateRiding) tabBar.updateRiding();
    if (tabBar.updateNav) tabBar.updateNav();
  },

  _calcBrightnessDisplay: function(blink, brightness) {
    return blink ? '跳变' : brightness + '%';
  },

  // ==================== 灯光控制 ====================

  onLightMode: function(e) {
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var mode = e.currentTarget.dataset.mode;
    this.setData({ lightMode: mode, lightBrightness: mode === 'manual' ? 100 : this.data.lightBrightness, brightnessDisplay: this._calcBrightnessDisplay(this.data.lightBlink, mode === 'manual' ? 100 : this.data.lightBrightness) });
    if (mode === 'auto') CtrlService.lightAuto();
    else if (mode === 'manual') CtrlService.lightOn();
    wx.showToast({ title: '已切换', icon: 'success', duration: 600 });
  },

  onLightOn: function() {
    if (this.data.lightMode === 'auto') { wx.showToast({ title: '当前为自动模式', icon: 'none' }); return; }
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    this.setData({ lightBrightness: 100, lightBlink: false, brightnessDisplay: '100%' });
    CtrlService.lightOn();
    wx.showToast({ title: '已发送', icon: 'success', duration: 600 });
  },

  onLightOff: function() {
    if (this.data.lightMode === 'auto') { wx.showToast({ title: '当前为自动模式', icon: 'none' }); return; }
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    this.setData({ lightBrightness: 0, lightBlink: false, brightnessDisplay: '0%' });
    CtrlService.lightOff();
    wx.showToast({ title: '已发送', icon: 'success', duration: 600 });
  },

  onLightBlink: function() {
    if (this.data.lightMode === 'auto') { wx.showToast({ title: '当前为自动模式', icon: 'none' }); return; }
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    CtrlService.blink();
    wx.showToast({ title: '闪烁指令已发送', icon: 'success', duration: 600 });
  },

  onBrightnessUp: function() {
    if (this.data.lightMode === 'auto') { wx.showToast({ title: '当前为自动模式', icon: 'none' }); return; }
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var newBri = Math.min((this.data.lightBrightness || 0) + 10, 100);
    this.setData({ lightBrightness: newBri, brightnessDisplay: this._calcBrightnessDisplay(this.data.lightBlink, newBri) });
    CtrlService.brightnessUp();
  },

  onBrightnessDown: function() {
    if (this.data.lightMode === 'auto') { wx.showToast({ title: '当前为自动模式', icon: 'none' }); return; }
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var newBri = Math.max((this.data.lightBrightness || 0) - 10, 0);
    this.setData({ lightBrightness: newBri, brightnessDisplay: this._calcBrightnessDisplay(this.data.lightBlink, newBri) });
    CtrlService.brightnessDown();
  },

  // ==================== 音量控制 ====================

  onVolumeUp: function() {
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var newVol = Math.min((this.data.volume || 0) + 1, 5);
    this.setData({ volume: newVol });
    CtrlService.volumeUp();
  },

  onVolumeDown: function() {
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var newVol = Math.max((this.data.volume || 0) - 1, 0);
    this.setData({ volume: newVol });
    CtrlService.volumeDown();
  },

  // ==================== 电源控制 ====================

  onPowerMode: function(e) {
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var mode = e.currentTarget.dataset.mode;
    var modeMap = { save: 'suspended', emergency: 'emergency', active: 'active' };
    var newPower = modeMap[mode] || mode;
    this.setData({ powerMode: newPower });
    if (mode === 'save') CtrlService.powerSave();
    else if (mode === 'emergency') CtrlService.powerEmergency();
    else CtrlService.powerNormal();
    wx.showToast({ title: '已发送', icon: 'success', duration: 600 });
  },

  // ==================== 报警控制 ====================

  onAlarmMode: function(e) {
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var mode = e.currentTarget.dataset.mode;
    this.setData({ alarmMode: mode });
    wx.showToast({ title: '已切换', icon: 'success', duration: 600 });
  },

  onAlarmSos: function() {
    if (!this.data.bleConnected) { wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var isStealth = this.data.alarmMode === 'stealth';
    var that = this;
    wx.showModal({
      title: isStealth ? '发送静默报警' : '发送 SOS 报警',
      content: isStealth ? '静默模式下报警，无声无光。' : '确定触发 SOS 报警？设备将发送紧急求助信号。',
      confirmText: isStealth ? '发送静默' : '发送 SOS',
      confirmColor: isStealth ? '#9c27b0' : '#ff2a4d',
      cancelText: '取消',
      success: function(res) {
        if (res.confirm) {
          if (isStealth) CtrlService.alarmStealth();
          else CtrlService.alarmSos();
          that.setData({ alarmActive: true, showAlarmPopup: true });
        }
      },
    });
  },

  onCancelAlarm: function() {
    this.setData({ alarmActive: false, showAlarmPopup: false });
    if (this.data.bleConnected) CtrlService.alarmCancel();
  },

  // ==================== 紧急联系人 ====================

  onPhoneInput: function(e) {
    this.setData({ emergencyPhoneInput: e.detail.value });
  },

  onSetPhone: function() {
    if (!this.data.bleConnected) {
      wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' });
      return;
    }
    var phone = this.data.emergencyPhoneInput.trim();
    if (!phone || phone.length !== 11 || !/^1\d{10}$/.test(phone)) {
      wx.showToast({ title: '请输入正确的11位手机号', icon: 'none' });
      return;
    }
    CtrlService.setPhone(phone);
    app.globalData.smsPhone = phone;
    this.setData({ emergencyPhoneSaved: phone });
    wx.showToast({ title: '紧急联系人已配置', icon: 'success' });
  },

  onClearPhone: function() {
    if (!this.data.bleConnected) {
      wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' });
      return;
    }
    this.setData({ emergencyPhoneInput: '', emergencyPhoneSaved: '' });
    app.globalData.smsPhone = '';
  },

  // ==================== 导航 ====================

  onNavIndicatorTap: function() {
    wx.redirectTo({ url: '/pages/index/index' });
  },

  // ==================== 导航栏 ====================

  onBackPress: function() {
    wx.redirectTo({ url: '/pages/index/index' });
  },
});
