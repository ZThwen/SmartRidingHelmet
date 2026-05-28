/**
 * BLE Central 客户端 — 扫描/连接/收发数据/自动重连
 */
var protocol = require('../utils/ble-protocol');
var logger = require('../utils/logger');

var _state = {
  deviceId: '', serviceId: '',
  charNotify: '', charNav: '', charCtrl: '', charAck: '',
  connected: false, scanning: false,
};
var _callbacks = { onData: null, onStatus: null, onConnected: null, onDisconnected: null, onDeviceFound: null };
var _reconnectCount = 0;
var _scanTimeout = null;
var _foundDevices = [];

function init(callbacks) {
  _callbacks = callbacks;
  return new Promise(function(resolve, reject) {
    wx.openBluetoothAdapter({
      success: function() {
        logger.log('BLE', '蓝牙适配器就绪');
        _registerListeners();
        resolve();
      },
      fail: function(err) { reject(err); },
    });
  });
}

function scan() {
  if (_state.scanning) return;
  _foundDevices = [];
  _state.scanning = true;
  wx.startBluetoothDevicesDiscovery({
    allowDuplicates: false,
    success: function() {
      logger.log('BLE', '扫描中...');
      if (_callbacks.onStatus) _callbacks.onStatus('扫描中...');
      _scanTimeout = setTimeout(function() {
        if (!_state.connected) {
          stopScan();
          if (_callbacks.onStatus) _callbacks.onStatus('未找到设备');
          logger.log('BLE', '扫描超时，未找到 SmartHelmet 设备');
        }
      }, 10000);
    },
  });
}

function stopScan() {
  _state.scanning = false;
  if (_scanTimeout) { clearTimeout(_scanTimeout); _scanTimeout = null; }
  wx.stopBluetoothDevicesDiscovery({});
}

function _registerListeners() {
  wx.onBluetoothDeviceFound(function(res) {
    var devices = res.devices || [];
    for (var i = 0; i < devices.length; i++) {
      var d = devices[i];
      if (d.name && d.name.indexOf(protocol.DEVICE_PREFIX) >= 0) {
        var exists = false;
        for (var j = 0; j < _foundDevices.length; j++) {
          if (_foundDevices[j].deviceId === d.deviceId) { exists = true; break; }
        }
        if (!exists) {
          _foundDevices.push({ deviceId: d.deviceId, name: d.name, rssi: d.RSSI || 0 });
          logger.log('BLE', '发现设备: ' + d.name + ' (' + d.deviceId + ')');
          if (_callbacks.onDeviceFound) _callbacks.onDeviceFound(_foundDevices.slice());
        }
      }
    }
  });

  wx.onBLECharacteristicValueChange(function(res) {
    if (!_callbacks.onData) return;
    var str = _ab2str(res.value);
    try {
      var data = JSON.parse(str);
      _callbacks.onData(data);
    } catch (e) {
      logger.log('BLE', '解析失败: ' + str);
    }
  });

  wx.onBLEConnectionStateChange(function(res) {
    if (res.connected) return;
    _state.connected = false;
    logger.log('BLE', '连接已断开');
    if (_callbacks.onDisconnected) _callbacks.onDisconnected();
    _tryReconnect();
  });
}

function connect(deviceId) {
  stopScan();
  logger.log('BLE', '正在连接...');
  wx.createBLEConnection({
    deviceId: deviceId,
    success: function() {
      _state.deviceId = deviceId;
      _discoverServices(deviceId);
    },
    fail: function(err) {
      logger.log('BLE', '连接失败: ' + err.errMsg);
      _tryReconnect();
    },
  });
}

function connectById(deviceId) {
  connect(deviceId);
}

function _discoverServices(deviceId) {
  wx.getBLEDeviceServices({
    deviceId: deviceId,
    success: function(res) {
      for (var i = 0; i < res.services.length; i++) {
        var s = res.services[i];
        if (s.uuid.indexOf('FFF0') >= 0) {
          _state.serviceId = s.uuid;
          _discoverChars(deviceId, s.uuid);
          return;
        }
      }
      logger.log('BLE', '未找到 FFF0 服务');
    },
  });
}

function _discoverChars(deviceId, serviceId) {
  wx.getBLEDeviceCharacteristics({
    deviceId: deviceId,
    serviceId: serviceId,
    success: function(res) {
      var chars = res.characteristics;
      for (var i = 0; i < chars.length; i++) {
        var c = chars[i];
        if (c.uuid.indexOf('FFF1') >= 0) {
          _state.charNotify = c.uuid;
          _enableNotify(deviceId, serviceId, c.uuid);
        } else if (c.uuid.indexOf('FFF2') >= 0) {
          _state.charNav = c.uuid;
        } else if (c.uuid.indexOf('FFF3') >= 0) {
          _state.charCtrl = c.uuid;
        } else if (c.uuid.indexOf('FFF4') >= 0) {
          _state.charAck = c.uuid;
        }
      }
      _state.connected = true;
      _reconnectCount = 0;
      if (_scanTimeout) { clearTimeout(_scanTimeout); _scanTimeout = null; }
      logger.log('BLE', '连接成功');
      if (_callbacks.onConnected) _callbacks.onConnected();
    },
  });
}

function _enableNotify(deviceId, serviceId, charId) {
  wx.notifyBLECharacteristicValueChange({
    deviceId: deviceId,
    serviceId: serviceId,
    characteristicId: charId,
    state: true,
  });
}

function sendNav(dir, dist, road) {
  var json = JSON.stringify({ a: 'nav', d: { dir: dir, dist: dist, road: road } });
  _write(_state.charNav, json);
}

function sendCtrl(cmd) {
  var json = JSON.stringify({ a: 'ctrl', d: { cmd: cmd } });
  _write(_state.charCtrl, json);
}

function sendAck(id) {
  var json = JSON.stringify({ a: 'ack', d: { id: id } });
  _write(_state.charAck, json);
}

function _write(charId, json) {
  if (!_state.connected || !charId) return;
  wx.writeBLECharacteristicValue({
    deviceId: _state.deviceId,
    serviceId: _state.serviceId,
    characteristicId: charId,
    value: _str2ab(json),
  });
}

function disconnect() {
  _reconnectCount = protocol.RECONNECT_MAX;
  if (_state.deviceId) {
    wx.closeBLEConnection({ deviceId: _state.deviceId });
  }
  _state.connected = false;
  logger.log('BLE', '已主动断开');
}

function _tryReconnect() {
  if (_reconnectCount >= protocol.RECONNECT_MAX) return;
  _reconnectCount++;
  logger.log('BLE', '重连中 (%d/%d)', _reconnectCount, protocol.RECONNECT_MAX);
  setTimeout(scan, protocol.RECONNECT_DELAY);
}

function isConnected() {
  return _state.connected;
}

function _ab2str(buf) {
  return String.fromCharCode.apply(null, new Uint8Array(buf));
}

function _str2ab(str) {
  var buf = new ArrayBuffer(str.length);
  var view = new Uint8Array(buf);
  for (var i = 0; i < str.length; i++) view[i] = str.charCodeAt(i);
  return buf;
}

module.exports = { init, scan, stopScan, connect, connectById, sendNav, sendCtrl, sendAck, disconnect, isConnected };
