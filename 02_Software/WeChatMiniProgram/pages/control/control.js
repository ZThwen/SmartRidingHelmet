/**
 * 远端控制页 — 灯光/音量/电源控制
 */
var BleService = require('../../services/ble-service');
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
    // 报警
    alarmMode: 'normal',
    alarmActive: false,
    showAlarmPopup: false,
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
  },

  onLoad: function() {
    var sysInfo = wx.getSystemInfoSync();
    var safeTop = sysInfo.safeArea ? sysInfo.safeArea.top : (sysInfo.statusBarHeight || 44);
    logger.log('CTRL', 'onLoad safeTop=' + safeTop);
    this.setData({ statusBarHeight: safeTop });
    this._syncFromGlobal();
    this._bindEvents();
  },

  onShow: function() {
    logger.log('CTRL', 'onShow');
    this._syncFromGlobal();
  },

  onUnload: function() {
    logger.log('CTRL', 'onUnload');
    this._unbindEvents();
  },

  _syncFromGlobal: function() {
    var gd = app.globalData;
    var cs = gd.ctrlState;
    var data = {
      bleConnected: gd.bleConnected,
      bleStatus: gd.bleStatus,
      deviceName: gd.bleConnected ? 'SmartHelmet-66ccff' : '',
      lightMode: cs.lightMode,
      lightBrightness: cs.brightness,
      volume: cs.volume,
      powerMode: cs.powerMode,
      riding: gd.isRiding,
      alarmActive: gd.alarmActive,
      showAlarmPopup: gd.alarmActive,
    };
    logger.log('CTRL', '_syncFromGlobal ble=' + gd.bleConnected +
      ' light=' + cs.lightMode + '/' + cs.brightness +
      ' vol=' + cs.volume + ' power=' + cs.powerMode +
      ' alarm=' + gd.alarmActive);
    this.setData(data);
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
    if (!bus) { logger.log('CTRL', '_bindEvents no bus'); return; }

    this._onCtrlState = function(state) {
      logger.log('CTRL', 'event ctrl:stateChanged mode=' + state.lightMode +
        ' bri=' + state.brightness + ' vol=' + state.volume + ' pwr=' + state.powerMode);
      that.setData({
        lightMode: state.lightMode,
        lightBrightness: state.brightness,
        volume: state.volume,
        powerMode: state.powerMode,
      });
    };

    this._onAlarmTriggered = function() {
      logger.log('CTRL', 'event alarm:triggered');
      that.setData({ alarmActive: true, showAlarmPopup: true });
    };

    this._onAlarmCancelled = function() {
      logger.log('CTRL', 'event alarm:cancelled');
      that.setData({ alarmActive: false, showAlarmPopup: false });
    };

    this._onBleDisconnected = function() {
      logger.log('CTRL', 'event ble:disconnected');
      that.setData({
        bleConnected: false,
        bleStatus: '已断开',
        deviceName: '',
      });
      CtrlService.reset();
      that._syncFromGlobal();
    };

    this._onBleConnected = function() {
      logger.log('CTRL', 'event ble:connected');
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
    logger.log('CTRL', '_bindEvents OK');
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
    if (!this.data.bleConnected) { logger.log('CTRL', 'lightMode blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var mode = e.currentTarget.dataset.mode;
    logger.log('CTRL', 'lightMode -> ' + mode);
    // 乐观更新：点击后立即切换模式高亮，不等硬件回推
    this.setData({ lightMode: mode });
    if (mode === 'auto') {
      CtrlService.lightAuto();
    } else if (mode === 'manual') {
      // 手动模式：发送 light_on（固件无独立 manual 指令，light_on 会自动切 manual）
      CtrlService.lightOn();
    }
    wx.showToast({ title: '已切换', icon: 'success', duration: 600 });
  },

  onLightOn: function() {
    if (this.data.lightMode === 'auto') { logger.log('CTRL', 'lightOn blocked: auto mode'); wx.showToast({ title: '当前为自动模式', icon: 'none' }); return; }
    if (!this.data.bleConnected) { logger.log('CTRL', 'lightOn blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    logger.log('CTRL', 'lightOn');
    // 乐观更新：开灯→显示100%（硬件PWM=50），不等硬件回推
    this.setData({ lightBrightness: 100 });
    CtrlService.lightOn();
    wx.showToast({ title: '已发送', icon: 'success', duration: 600 });
  },

  onLightOff: function() {
    if (this.data.lightMode === 'auto') { logger.log('CTRL', 'lightOff blocked: auto mode'); wx.showToast({ title: '当前为自动模式', icon: 'none' }); return; }
    if (!this.data.bleConnected) { logger.log('CTRL', 'lightOff blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    logger.log('CTRL', 'lightOff');
    // 乐观更新：关灯→亮度0%
    this.setData({ lightBrightness: 0 });
    CtrlService.lightOff();
    wx.showToast({ title: '已发送', icon: 'success', duration: 600 });
  },

  onBrightnessUp: function() {
    if (this.data.lightMode === 'auto') { logger.log('CTRL', 'brightnessUp blocked: auto mode'); wx.showToast({ title: '当前为自动模式', icon: 'none' }); return; }
    if (!this.data.bleConnected) { logger.log('CTRL', 'brightnessUp blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    logger.log('CTRL', 'brightnessUp');
    var newBri = Math.min((this.data.lightBrightness || 0) + 10, 100);
    this.setData({ lightBrightness: newBri });
    CtrlService.brightnessUp();
  },

  onBrightnessDown: function() {
    if (this.data.lightMode === 'auto') { logger.log('CTRL', 'brightnessDown blocked: auto mode'); wx.showToast({ title: '当前为自动模式', icon: 'none' }); return; }
    if (!this.data.bleConnected) { logger.log('CTRL', 'brightnessDown blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    logger.log('CTRL', 'brightnessDown');
    var newBri = Math.max((this.data.lightBrightness || 0) - 10, 0);
    this.setData({ lightBrightness: newBri });
    CtrlService.brightnessDown();
  },

  // ==================== 音量控制 ====================

  onVolumeUp: function() {
    if (!this.data.bleConnected) { logger.log('CTRL', 'volumeUp blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    logger.log('CTRL', 'volumeUp');
    var newVol = Math.min((this.data.volume || 0) + 1, 5);
    this.setData({ volume: newVol });
    CtrlService.volumeUp();
  },

  onVolumeDown: function() {
    if (!this.data.bleConnected) { logger.log('CTRL', 'volumeDown blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    logger.log('CTRL', 'volumeDown');
    var newVol = Math.max((this.data.volume || 0) - 1, 0);
    this.setData({ volume: newVol });
    CtrlService.volumeDown();
  },

  // ==================== 电源控制 ====================

  onPowerMode: function(e) {
    if (!this.data.bleConnected) { logger.log('CTRL', 'powerMode blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var mode = e.currentTarget.dataset.mode;
    var modeMap = { save: 'suspended', emergency: 'emergency', active: 'active' };
    var newPower = modeMap[mode] || mode;
    logger.log('CTRL', 'powerMode -> ' + mode + ' optimistic=' + newPower);
    this.setData({ powerMode: newPower });
    if (mode === 'save') {
      CtrlService.powerSave();
    } else if (mode === 'emergency') {
      CtrlService.powerEmergency();
    } else {
      CtrlService.powerNormal();
    }
    wx.showToast({ title: '已发送', icon: 'success', duration: 600 });
  },

  // ==================== 报警控制 ====================

  onAlarmMode: function(e) {
    if (!this.data.bleConnected) { logger.log('CTRL', 'alarmMode blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
    var mode = e.currentTarget.dataset.mode;
    logger.log('CTRL', 'alarmMode -> ' + mode);
    this.setData({ alarmMode: mode });
    wx.showToast({ title: '已切换', icon: 'success', duration: 600 });
  },

  onAlarmSos: function() {
    logger.log('CTRL', 'onAlarmSos ENTER');
    try {
      if (!this.data.bleConnected) { logger.log('CTRL', 'alarmSos blocked: no BLE'); wx.showToast({ title: '请先连接蓝牙设备', icon: 'none' }); return; }
      var isStealth = this.data.alarmMode === 'stealth';
      logger.log('CTRL', 'alarmSos showModal mode=' + this.data.alarmMode + ' stealth=' + isStealth);
      var that = this;
      wx.showModal({
        title: isStealth ? '发送静默报警' : '发送 SOS 报警',
        content: isStealth ? '静默模式下报警，无声无光。' : '确定触发 SOS 报警？设备将发送紧急求助信号。',
        confirmText: isStealth ? '发送静默' : '发送 SOS',
        confirmColor: isStealth ? '#9c27b0' : '#ff2a4d',
        cancelText: '取消',
        success: function(res) {
          if (res.confirm) {
            logger.log('CTRL', 'alarmSos confirmed, stealth=' + isStealth);
            try {
              if (isStealth) {
                logger.log('CTRL', 'CtrlService.alarmStealth() calling...');
                CtrlService.alarmStealth();
              } else {
                logger.log('CTRL', 'CtrlService.alarmSos() calling...');
                CtrlService.alarmSos();
              }
            } catch (e) {
              logger.log('CTRL', 'alarmSos send ERROR: ' + (e.message || e));
              console.error('[ctrl] alarmSos error:', e);
            }
            that.setData({ alarmActive: true, showAlarmPopup: true });
          } else {
            logger.log('CTRL', 'alarmSos cancelled by user');
          }
        },
        fail: function(err) {
          logger.log('CTRL', 'alarmSos showModal FAIL: ' + JSON.stringify(err));
        },
      });
    } catch (e) {
      logger.log('CTRL', 'onAlarmSos EXCEPTION: ' + (e.message || e));
    }
  },

  // ==================== 导航 ====================

  onNavIndicatorTap: function() {
    logger.log('CTRL', 'navIndicatorTap -> redirect to index');
    wx.redirectTo({ url: '/pages/index/index' });
  },

  // ==================== 报警 ====================

  onCancelAlarm: function() {
    logger.log('CTRL', 'cancelAlarm alarmActive=' + this.data.alarmActive + ' ble=' + this.data.bleConnected);
    this.setData({ alarmActive: false, showAlarmPopup: false });
    if (this.data.bleConnected) {
      CtrlService.alarmCancel();
    }
  },

  // ==================== 导航栏 ====================

  onBackPress: function() {
    wx.redirectTo({ url: '/pages/index/index' });
  },
});
