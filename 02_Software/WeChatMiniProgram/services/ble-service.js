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
var _listenersRegistered = false;

function init(callbacks) {
  _callbacks = callbacks;
  return new Promise(function (resolve, reject) {
    wx.openBluetoothAdapter({
      success: function () {
        logger.log('BLE', '蓝牙适配器就绪');
        _registerListeners();
        resolve();
      },
      fail: function (err) { reject(err); },
    });
  });
}

function _addFoundDevice(d, name) {
  var exists = false;
  for (var j = 0; j < _foundDevices.length; j++) {
    if (_foundDevices[j].deviceId === d.deviceId) {
      exists = true;
      _foundDevices[j].name = name;
      _foundDevices[j].rssi = d.RSSI || 0;
      break;
    }
  }
  if (!exists) {
    _foundDevices.push({ deviceId: d.deviceId, name: name, rssi: d.RSSI || 0 });
    logger.log('BLE', '匹配到目标头盔设备: ' + name + ' (' + d.deviceId + ') RSSI=' + (d.RSSI || 0));
  }
  if (_callbacks.onDeviceFound) {
    _callbacks.onDeviceFound(_foundDevices.slice());
  }
}

function _checkCachedDevices() {
  wx.getBluetoothDevices({
    success: function (res) {
      var devices = res.devices || [];
      logger.log('BLE', 'wx.getBluetoothDevices 查到 ' + devices.length + ' 个已存在/缓存设备');
      for (var i = 0; i < devices.length; i++) {
        var d = devices[i];
        var name = d.localName || d.name || '';
        logger.log('BLE_CACHE', '缓存设备[' + i + ']: name="' + (d.name || '') + '" localName="' + (d.localName || '') + '" id=' + d.deviceId + ' RSSI=' + (d.RSSI || 0));
        if (name && name.indexOf(protocol.DEVICE_PREFIX) >= 0) {
          _addFoundDevice(d, name);
        }
      }
    },
    fail: function (err) {
      logger.log('BLE', 'wx.getBluetoothDevices 失败: ' + err.errMsg);
    }
  });
}

function scan() {
  stopScan();
  _foundDevices = [];
  _state.scanning = true;
  logger.log('BLE', '开始扫描 BLE 设备...');

  wx.startBluetoothDevicesDiscovery({
    allowDuplicates: true,
    success: function () {
      logger.log('BLE', 'wx.startBluetoothDevicesDiscovery 启动成功');
      if (_callbacks.onStatus) _callbacks.onStatus('扫描中...');

      // 1. 立刻主动检查已存在的系统蓝牙缓存
      _checkCachedDevices();

      // 2. 3s 和 6s 再次轮询兜底
      var poll1 = setTimeout(_checkCachedDevices, 3000);
      var poll2 = setTimeout(_checkCachedDevices, 6000);

      _scanTimeout = setTimeout(function () {
        clearTimeout(poll1);
        clearTimeout(poll2);
        if (!_state.connected) {
          stopScan();
          if (_callbacks.onStatus && _foundDevices.length === 0) {
            _callbacks.onStatus('未找到设备');
          }
          logger.log('BLE', '扫描结束，共发现目标设备数: ' + _foundDevices.length);
        }
      }, 10000);
    },
    fail: function (err) {
      _state.scanning = false;
      logger.log('BLE', 'wx.startBluetoothDevicesDiscovery 失败: ' + err.errMsg);
      if (_callbacks.onStatus) _callbacks.onStatus('扫描启动失败');
    }
  });
}

function stopScan() {
  _state.scanning = false;
  if (_scanTimeout) { clearTimeout(_scanTimeout); _scanTimeout = null; }
  wx.stopBluetoothDevicesDiscovery({});
}

function _registerListeners() {
  if (_listenersRegistered) {
    logger.log('BLE', '监听器已注册，无需重复注册');
    return;
  }
  _listenersRegistered = true;

  wx.onBluetoothDeviceFound(function (res) {
    var devices = res.devices || [];
    for (var i = 0; i < devices.length; i++) {
      var d = devices[i];
      var name = d.localName || d.name || '';
      logger.log('BLE_FOUND', '广播: name="' + (d.name || '') + '" localName="' + (d.localName || '') + '" id=' + d.deviceId + ' RSSI=' + (d.RSSI || 0));
      if (name && name.indexOf(protocol.DEVICE_PREFIX) >= 0) {
        _addFoundDevice(d, name);
      }
    }
  });

  wx.onBLECharacteristicValueChange(function (res) {
    if (!_callbacks.onData) return;
    var cid = res.characteristicId || '';
    if (cid.indexOf('FFF1') < 0) return;
    var str = _ab2str(res.value);
    if (!str || str.length < 3) return;
    try {
      var data = JSON.parse(str);
      logger.log('BLE', '收到数据: ' + JSON.stringify(data));
      _callbacks.onData(data);
    } catch (e) {
      logger.log('BLE', '解析失败: ' + str);
    }
  });

  wx.onBLEConnectionStateChange(function (res) {
    logger.log('BLE', '连接状态变更: deviceId=' + res.deviceId + ' connected=' + res.connected);
    if (res.connected) return;
    _state.connected = false;
    _state.charNotify = '';
    _state.charNav = '';
    _state.charCtrl = '';
    _state.charAck = '';
    logger.log('BLE', '连接已断开');
    if (_callbacks.onDisconnected) _callbacks.onDisconnected();
    _tryReconnect();
  });
}

function connect(deviceId) {
  _reconnectCount = 0;
  stopScan();
  logger.log('BLE', '正在连接: ' + deviceId);
  wx.createBLEConnection({
    deviceId: deviceId,
    success: function () {
      _state.deviceId = deviceId;
      logger.log('BLE', 'wx.createBLEConnection 成功，开始获取服务...');
      _discoverServices(deviceId);
    },
    fail: function (err) {
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
    success: function (res) {
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
    success: function (res) {
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
    success: function () {
      logger.log('BLE', 'CCCD 订阅成功: ' + charId.slice(-4));
    },
    fail: function (err) {
      logger.log('BLE', 'CCCD 订阅失败: ' + JSON.stringify(err));
    },
  });
}

function sendNav(dir, dist, road) {
  var json = JSON.stringify({ a: 'nav', d: { dir: dir, dist: dist, road: road } });
  _write(_state.charNav, json);
}

function sendCtrl(cmd) {
  var json = JSON.stringify({ a: 'ctrl', d: { cmd: cmd } });
  logger.log('BLE', 'sendCtrl -> FFF3: ' + json + ' connected=' + _state.connected);
  _write(_state.charCtrl, json);
}

function sendCtrlWithParams(cmd, params) {
  var d = { cmd: cmd };
  for (var k in params) { d[k] = params[k]; }
  var json = JSON.stringify({ a: 'ctrl', d: d });
  logger.log('BLE', 'sendCtrlWithParams -> FFF3: ' + json + ' connected=' + _state.connected);
  _write(_state.charCtrl, json);
}

function sendAck(id) {
  var json = JSON.stringify({ a: 'ack', d: { id: id } });
  _write(_state.charAck, json);
}

function _write(charId, json) {
  if (!_state.connected) { logger.log('BLE', '_write skipped: not connected'); return; }
  if (!charId) { logger.log('BLE', '_write skipped: no charId'); return; }
  logger.log('BLE', '_write -> ' + charId.slice(-4) + ': ' + json + ' len=' + json.length);
  wx.writeBLECharacteristicValue({
    deviceId: _state.deviceId,
    serviceId: _state.serviceId,
    characteristicId: charId,
    value: _str2ab(json),
    success: function () {
      logger.log('BLE', '_write OK ' + charId.slice(-4) + ': ' + json);
    },
    fail: function (err) {
      logger.log('BLE', '_write FAIL ' + charId.slice(-4) + ': ' + err.errMsg + ' json=' + json);
      if (_callbacks.onStatus) _callbacks.onStatus('BLE 写入失败');
    },
  });
}

function disconnect() {
  _reconnectCount = protocol.RECONNECT_MAX;
  stopScan();
  if (_state.deviceId) {
    wx.closeBLEConnection({ deviceId: _state.deviceId });
  }
  _state.connected = false;
  _state.charNotify = '';
  _state.charNav = '';
  _state.charCtrl = '';
  _state.charAck = '';
  logger.log('BLE', '已主动断开');
}

function _tryReconnect() {
  if (_reconnectCount >= protocol.RECONNECT_MAX) return;
  _reconnectCount++;
  logger.log('BLE', '重连中 (%d/%d)', _reconnectCount, protocol.RECONNECT_MAX);
  if (_state.deviceId) {
    // 先尝试直连上次设备
    wx.createBLEConnection({
      deviceId: _state.deviceId,
      success: function () {
        logger.log('BLE', '直连成功');
        _discoverServices(_state.deviceId);
      },
      fail: function () {
        // 直连失败，回退到扫描
        logger.log('BLE', '直连失败，重新扫描');
        setTimeout(scan, protocol.RECONNECT_DELAY);
      },
    });
  } else {
    setTimeout(scan, protocol.RECONNECT_DELAY);
  }
}

function isConnected() {
  return _state.connected;
}

function setCallbacks(callbacks) {
  _callbacks = callbacks;
}

function _ab2str(buf) {
  var bytes = new Uint8Array(buf);
  var str = '';
  for (var i = 0; i < bytes.length; i++) {
    var b = bytes[i];
    if (b < 0x80) {
      str += String.fromCharCode(b);
    } else if (b < 0xE0) {
      str += String.fromCharCode(((b & 0x1F) << 6) | (bytes[++i] & 0x3F));
    } else {
      str += String.fromCharCode(((b & 0x0F) << 12) | ((bytes[++i] & 0x3F) << 6) | (bytes[++i] & 0x3F));
    }
  }
  return str;
}

function _str2ab(str) {
  var utf8 = [];
  for (var i = 0; i < str.length; i++) {
    var c = str.charCodeAt(i);
    if (c < 0x80) {
      utf8.push(c);
    } else if (c < 0x800) {
      utf8.push(0xC0 | (c >> 6), 0x80 | (c & 0x3F));
    } else {
      utf8.push(0xE0 | (c >> 12), 0x80 | ((c >> 6) & 0x3F), 0x80 | (c & 0x3F));
    }
  }
  var buf = new ArrayBuffer(utf8.length);
  var view = new Uint8Array(buf);
  for (var i = 0; i < utf8.length; i++) view[i] = utf8[i];
  return buf;
}

module.exports = { init, scan, stopScan, connect, connectById, sendNav, sendCtrl, sendCtrlWithParams, sendAck, disconnect, isConnected, setCallbacks };
