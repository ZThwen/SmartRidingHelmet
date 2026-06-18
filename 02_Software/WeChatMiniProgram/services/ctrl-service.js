/**
 * CtrlService — 远端控制服务
 *
 * 职责: 发送控制指令（BLE FFF3）+ 管理控制状态（type=7 回推）
 * 依赖: ble-service.js (sendCtrl)
 * 指令格式: {"a":"ctrl","d":{"cmd":"<command>"}}
 */
var BleService = require('./ble-service');
var logger = require('../utils/logger');

// 控制指令常量
var CMD = {
  LIGHT_ON: 'light_on',
  LIGHT_OFF: 'light_off',
  BRIGHTNESS_UP: 'brightness_up',
  BRIGHTNESS_DOWN: 'brightness_down',
  LIGHT_AUTO: 'light_auto',
  VOLUME_UP: 'volume_up',
  VOLUME_DOWN: 'volume_down',
  ALARM_CANCEL: 'alarm_cancel',
  ALARM_SOS: 'alarm_sos',
  ALARM_STEALTH: 'alarm_stealth',
  POWER_SAVE: 'power_save',
  POWER_NORMAL: 'power_normal',
  POWER_EMERGENCY: 'power_emergency',
  QUERY_STATUS: 'query_status',
  QUERY_SPEED: 'query_speed',
  QUERY_TEMP: 'query_temp',
  QUERY_HUMID: 'query_humid',
  QUERY_LOCATION: 'query_location',
  QUERY_BATTERY: 'query_battery',
};

// 控制状态缓存（type=7 回推时更新）
var _state = {
  lightMode: 'auto',
  brightness: 0,
  volume: 5,
  powerMode: 'active',
};

// ==================== 指令发送 ====================

function lightOn() {
  BleService.sendCtrl(CMD.LIGHT_ON);
  logger.log('CTRL', 'light_on sent');
}

function lightOff() {
  BleService.sendCtrl(CMD.LIGHT_OFF);
  logger.log('CTRL', 'light_off sent');
}

function lightAuto() {
  BleService.sendCtrl(CMD.LIGHT_AUTO);
  logger.log('CTRL', 'light_auto sent');
}

function brightnessUp() {
  BleService.sendCtrl(CMD.BRIGHTNESS_UP);
  logger.log('CTRL', 'brightness_up sent');
}

function brightnessDown() {
  BleService.sendCtrl(CMD.BRIGHTNESS_DOWN);
  logger.log('CTRL', 'brightness_down sent');
}

function volumeUp() {
  BleService.sendCtrl(CMD.VOLUME_UP);
  logger.log('CTRL', 'volume_up sent');
}

function volumeDown() {
  BleService.sendCtrl(CMD.VOLUME_DOWN);
  logger.log('CTRL', 'volume_down sent');
}

function powerSave() {
  BleService.sendCtrl(CMD.POWER_SAVE);
  logger.log('CTRL', 'power_save sent');
}

function powerNormal() {
  BleService.sendCtrl(CMD.POWER_NORMAL);
  logger.log('CTRL', 'power_normal sent');
}

function alarmSos() {
  BleService.sendCtrl(CMD.ALARM_SOS);
  logger.log('CTRL', 'alarm_sos sent');
}

function alarmCancel() {
  BleService.sendCtrl(CMD.ALARM_CANCEL);
  logger.log('CTRL', 'alarm_cancel sent');
}

function alarmStealth() {
  BleService.sendCtrl(CMD.ALARM_STEALTH);
  logger.log('CTRL', 'alarm_stealth sent');
}

function powerEmergency() {
  BleService.sendCtrl(CMD.POWER_EMERGENCY);
  logger.log('CTRL', 'power_emergency sent');
}

function queryStatus() {
  BleService.sendCtrl(CMD.QUERY_STATUS);
  logger.log('CTRL', 'query_status sent');
}

function querySpeed() {
  BleService.sendCtrl(CMD.QUERY_SPEED);
  logger.log('CTRL', 'query_speed sent');
}

function queryTemp() {
  BleService.sendCtrl(CMD.QUERY_TEMP);
  logger.log('CTRL', 'query_temp sent');
}

function queryHumid() {
  BleService.sendCtrl(CMD.QUERY_HUMID);
  logger.log('CTRL', 'query_humid sent');
}

function queryLocation() {
  BleService.sendCtrl(CMD.QUERY_LOCATION);
  logger.log('CTRL', 'query_location sent');
}

function queryBattery() {
  BleService.sendCtrl(CMD.QUERY_BATTERY);
  logger.log('CTRL', 'query_battery sent');
}

// ==================== 状态解析 ====================

/**
 * 解析控制状态回推（硬件扁平格式）
 * @param {object} data - 旧格式: {t:7,m:0,b:50} / {t:8,v:5} / {t:9,p:1}
 *                       新格式: {t:7,m:0,b:50,v:5,p:0}（合并推送）
 * @returns {object|null} {lightMode, brightness, volume, powerMode} or null
 */
function parseCtrlState(data) {
  try {
    if (!data) return null;
    // t=7: 灯光 {m:0=auto/1=manual, b:brightness}
    if (data.t === 7) {
      if (data.m != null) _state.lightMode = data.m === 1 ? 'manual' : 'auto';
      if (data.b != null) _state.brightness = data.b * 2;
    }
    // t=8: 音量 {v:volume}
    if (data.t === 8) {
      if (data.v != null) _state.volume = data.v;
    }
    // t=9: 电源 {p:0=active/1=suspended/2=emergency/3=custom}
    if (data.t === 9) {
      var pMap = {0: 'active', 1: 'suspended', 2: 'emergency', 3: 'custom'};
      if (data.p != null) _state.powerMode = pMap[data.p] || 'active';
    }
    // 合并格式：t=7 但包含 v 和 p 字段
    if (data.t === 7 && data.v != null) _state.volume = data.v;
    if (data.t === 7 && data.p != null) {
      var pMap = {0: 'active', 1: 'suspended', 2: 'emergency', 3: 'custom'};
      _state.powerMode = pMap[data.p] || 'active';
    }
    logger.log('CTRL', 'state recv: t=' + data.t +
      ' light=' + _state.lightMode + '/' + _state.brightness +
      ' vol=' + _state.volume + ' power=' + _state.powerMode);
    return getState();
  } catch (e) {
    console.error('[ctrl-service] parseCtrlState error:', e);
    return null;
  }
}

function getState() {
  return {
    lightMode: _state.lightMode,
    brightness: _state.brightness,
    volume: _state.volume,
    powerMode: _state.powerMode,
  };
}

function reset() {
  _state = { lightMode: 'auto', brightness: 0, volume: 5, powerMode: 'active' };
  logger.log('CTRL', 'state reset');
}

module.exports = {
  CMD: CMD,
  lightOn: lightOn,
  lightOff: lightOff,
  lightAuto: lightAuto,
  brightnessUp: brightnessUp,
  brightnessDown: brightnessDown,
  volumeUp: volumeUp,
  volumeDown: volumeDown,
  powerSave: powerSave,
  powerNormal: powerNormal,
  alarmSos: alarmSos,
  alarmCancel: alarmCancel,
  alarmStealth: alarmStealth,
  powerEmergency: powerEmergency,
  queryStatus: queryStatus,
  querySpeed: querySpeed,
  queryTemp: queryTemp,
  queryHumid: queryHumid,
  queryLocation: queryLocation,
  queryBattery: queryBattery,
  parseCtrlState: parseCtrlState,
  getState: getState,
  reset: reset,
};
