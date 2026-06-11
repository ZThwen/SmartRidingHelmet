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
  POWER_SAVE: 'power_save',
  POWER_NORMAL: 'power_normal',
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

// ==================== 状态解析 ====================

/**
 * 解析 type=7 控制状态回推
 * @param {object} data - 已解析的 JSON 对象 {t:7, d:{light_mode,light_brightness,volume,power_mode}}
 * @returns {object|null} {lightMode, brightness, volume, powerMode} or null
 */
function parseCtrlState(data) {
  try {
    if (!data || data.t !== 7 || !data.d) return null;
    var d = data.d;
    _state.lightMode = d.light_mode || 'auto';
    _state.brightness = d.light_brightness || 0;
    _state.volume = d.volume || 0;
    _state.powerMode = d.power_mode || 'active';
    logger.log('CTRL', 'state recv: mode=' + _state.lightMode +
      ' bri=' + _state.brightness + ' vol=' + _state.volume);
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
  parseCtrlState: parseCtrlState,
  getState: getState,
  reset: reset,
};
