/**
 * StateService — 全局 BLE 状态管理中心
 *
 * 职责:
 *   1. 接收 BLE 所有数据（t=0/5/6/7/8/9），统一解析
 *   2. 更新 app.globalData（传感器、控制状态、报警、BLE 连接）
 *   3. 通过 EventBus 广播状态变更事件
 *   4. 页面不再直接设置 BLE 回调，仅订阅 EventBus
 *
 * 事件:
 *   'state:sensorUpdate'   — 传感器数据更新 {formatted, raw}
 *   'state:alarmTriggered' — 报警触发 {type, level, displayText, popupClass, icon}
 *   'state:alarmCancelled' — 报警取消
 *   'state:ctrlChanged'    — 控制状态变更 {lightMode, brightness, volume, powerMode}
 *   'ble:connected'        — BLE 连接成功
 *   'ble:disconnected'     — BLE 断开
 *   'ble:status'           — BLE 状态文字
 *   'ble:deviceFound'      — 发现 BLE 设备
 */
var AlarmService = require('./alarm-service');
var CtrlService = require('./ctrl-service');
var RideService = require('./ride-service');
var logger = require('../utils/logger');

var _app = null;
var _bus = null;

/**
 * 初始化 — 获取 app 和 bus 引用
 * 在 app.js onLaunch 之后调用
 */
function init() {
  _app = getApp();
  _bus = _app.eventBus;
  logger.log('STATE', 'StateService 初始化');
}

// ==================== BLE 回调（全局唯一） ====================

/**
 * 返回给 BleService 的全局回调集合
 * 页面不再自己注册 BLE 回调，统一由 StateService 处理
 */
function getBleCallbacks() {
  return {
    onConnected: function() {
      logger.log('STATE', 'BLE 连接成功');
      _app.globalData.bleConnected = true;
      _app.globalData.bleStatus = '已连接';
      if (_bus) _bus.emit('ble:connected');
    },
    onDisconnected: function() {
      logger.log('STATE', 'BLE 断开');
      _app.globalData.bleConnected = false;
      _app.globalData.bleStatus = '已断开';
      CtrlService.reset();
      if (_bus) _bus.emit('ble:disconnected');
    },
    onData: function(data) {
      _handleBleData(data);
    },
    onStatus: function(msg) {
      _app.globalData.bleStatus = msg;
      if (_bus) _bus.emit('ble:status', msg);
    },
    onDeviceFound: function(devices) {
      if (_bus) _bus.emit('ble:deviceFound', devices);
    },
  };
}

// ==================== BLE 数据解析 ====================

function _handleBleData(data) {
  logger.log('STATE', '收到 BLE 数据: t=' + data.t);

  if (data.t === 0 && data.d) {
    _handleSensorData(data.d);
  } else if (data.t === 5) {
    _handleAlarm(data);
  } else if (data.t === 6) {
    _handleAlarmCancel();
  } else if (data.t === 7 || data.t === 8 || data.t === 9) {
    _handleCtrlState(data);
  }
}

/**
 * t=0 传感器合并数据
 * 解析 → 格式化显示字符串 + 缓存原始数值 → 更新 globalData + 发事件
 */
function _handleSensorData(d) {
  var formatted = {};
  if (d.tmp != null) formatted.temp = d.tmp.toFixed(1) + '°C';
  if (d.hum != null) formatted.humid = d.hum.toFixed(1) + '%';
  if (d.spd != null) formatted.speed = d.spd.toFixed(1) + ' km/h';
  if (d.lat != null) formatted.lat = d.lat.toFixed(4);
  if (d.lon != null) formatted.lon = d.lon.toFixed(4);
  if (d.alt != null) formatted.alt = d.alt.toFixed(1) + 'm';
  if (d.cog != null) formatted.cog = d.cog.toFixed(0) + '°';
  if (d.lux != null) formatted.lux = d.lux;
  if (d.bat != null) formatted.battery = d.bat + '档';
  formatted.time = new Date().toLocaleTimeString();
  formatted.isOnline = true;

  // 心率/血氧
  if (d.hr != null) {
    formatted.heartRate = d.hr;
    var hc = _computeHeartClasses(d.hr, d.spo2);
    formatted.heartClass = hc.heartClass;
    formatted.spo2Class = hc.spo2Class;
    formatted.heartIcon = '\u2665';
  }
  if (d.spo2 != null) formatted.spo2 = d.spo2;

  // 缓存到 globalData（页面切换恢复用）
  _app.globalData.latestSensorData = {
    temp: formatted.temp, humid: formatted.humid, speed: formatted.speed,
    lat: formatted.lat, lon: formatted.lon, alt: formatted.alt, cog: formatted.cog,
    lux: formatted.lux, battery: formatted.battery, time: formatted.time,
    heartRate: formatted.heartRate, spo2: formatted.spo2,
    heartClass: formatted.heartClass, spo2Class: formatted.spo2Class,
  };

  // 广播传感器数据更新
  if (_bus) {
    _bus.emit('state:sensorUpdate', {
      formatted: formatted,
      raw: d,
    });
  }
}

/**
 * t=5 报警
 */
function _handleAlarm(data) {
  // 支持紧凑格式 {t:5, a:1, l:2} 和旧格式 {t:5, d:{type:'collision', lvl:2}}
  var typeCode = data.a || (data.d && data.d.type === 'collision' ? 1 : 2);
  var alarmLevel = data.l || (data.d && data.d.lvl) || 1;
  var typeName = typeCode === 1 ? '碰撞' : 'SOS';
  var alarmResult = AlarmService.analyze(typeCode, alarmLevel);

  _app.globalData.alarmActive = true;

  if (_bus) {
    _bus.emit('state:alarmTriggered', {
      type: typeName,
      level: alarmLevel,
      displayText: alarmResult.displayText,
      shouldPopup: alarmResult.shouldPopup,
      popupClass: alarmResult.popupClass,
      icon: alarmResult.icon,
    });
  }
}

/**
 * t=6 报警取消
 */
function _handleAlarmCancel() {
  _app.globalData.alarmActive = false;
  if (_bus) _bus.emit('state:alarmCancelled');
}

/**
 * t=7/8/9 控制状态回推
 */
function _handleCtrlState(data) {
  var state = CtrlService.parseCtrlState(data);
  if (state) {
    _app.globalData.ctrlState = state;
    if (_bus) _bus.emit('state:ctrlChanged', state);
  }
}

// ==================== 心率预警样式 ====================

function _computeHeartClasses(hr, spo2) {
  var result = { heartClass: '', spo2Class: '' };
  if (hr == null) {
    result.heartClass = 'hr-off';
    return result;
  }
  if (spo2 != null && spo2 < 90) {
    result.heartClass = 'hr-danger';
    result.spo2Class = 'spo2-danger';
  } else if (hr < 50 || hr > 190) {
    result.heartClass = 'hr-warn';
  }
  return result;
}

// ==================== 便捷方法 ====================

/**
 * 从 globalData 同步所有状态到页面 data
 * 用于页面 onShow 恢复状态
 */
function syncToPageData() {
  var gd = _app.globalData;
  var cs = gd.ctrlState;
  var cached = gd.latestSensorData;
  var data = {};

  // BLE
  data.bleConnected = gd.bleConnected;
  data.bleStatus = gd.bleStatus;

  // 骑行
  data.riding = !!gd.isRiding;

  // 报警
  data.alarmActive = gd.alarmActive;

  // 控制状态
  data.lightMode = cs.lightMode;
  data.lightBrightness = cs.brightness;
  data.volume = cs.volume;
  data.powerMode = cs.powerMode;
  data.lightBlink = cs.blink;
  data.brightnessDisplay = cs.blink ? '跳变' : cs.brightness + '%';

  // 传感器数据（仅已连接时恢复）
  if (gd.bleConnected && cached) {
    if (cached.temp) data.temp = cached.temp;
    if (cached.humid) data.humid = cached.humid;
    if (cached.speed) data.speed = cached.speed;
    if (cached.lat) data.lat = cached.lat;
    if (cached.lon) data.lon = cached.lon;
    if (cached.alt) data.alt = cached.alt;
    if (cached.cog) data.cog = cached.cog;
    if (cached.lux != null) data.lux = cached.lux;
    if (cached.battery) data.battery = cached.battery;
    if (cached.time) data.time = cached.time;
    if (cached.heartRate != null) {
      data.heartRate = cached.heartRate;
      data.heartClass = cached.heartClass || '';
      data.heartIcon = '\u2665';
    }
    if (cached.spo2 != null) data.spo2 = cached.spo2;
    if (cached.spo2Class) data.spo2Class = cached.spo2Class;
  }

  return data;
}

module.exports = {
  init: init,
  getBleCallbacks: getBleCallbacks,
  syncToPageData: syncToPageData,
};
