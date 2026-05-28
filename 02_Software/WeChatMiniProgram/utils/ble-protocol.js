/**
 * BLE 协议层 — 常量定义 + 数据解析
 */
var SERVICE_UUID = '0000FFF0-0000-1000-8000-00805F9B34FB';
var CHAR_DATA    = '0000FFF1-0000-1000-8000-00805F9B34FB';
var CHAR_NAV     = '0000FFF2-0000-1000-8000-00805F9B34FB';
var CHAR_CTRL    = '0000FFF3-0000-1000-8000-00805F9B34FB';
var CHAR_ACK     = '0000FFF4-0000-1000-8000-00805F9B34FB';
var DEVICE_PREFIX = 'SmartHelmet-';
var RECONNECT_MAX = 3;
var RECONNECT_DELAY = 2000;

var TYPE_MAP = {
  0: 'merged',
  1: 'temp_humid', 2: 'gnss', 4: 'light',
  5: 'alarm', 6: 'alarm_cancel', 99: 'keepalive',
};

function parseData(data) {
  var type = TYPE_MAP[data.t] || 'unknown';
  return { type: type, payload: data.d, raw: data };
}

module.exports = {
  SERVICE_UUID, CHAR_DATA, CHAR_NAV, CHAR_CTRL, CHAR_ACK,
  DEVICE_PREFIX, RECONNECT_MAX, RECONNECT_DELAY, parseData,
};
