/**
 * BLE 协议层 — 常量定义 + 数据类型映射
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
  0: 'merged',        // 传感器合并数据（温度/湿度/速度/经纬度/海拔/光照/电量/航向/心率/血氧）
  5: 'alarm',
  6: 'alarm_cancel',
  7: 'ctrl_state',
  99: 'keepalive',
};

module.exports = {
  SERVICE_UUID, CHAR_DATA, CHAR_NAV, CHAR_CTRL, CHAR_ACK,
  DEVICE_PREFIX, RECONNECT_MAX, RECONNECT_DELAY, TYPE_MAP,
};
