/**
 * DataService — 数据获取 + TSL 解析
 * 
 * C3 组件层: DataComponent
 * 职责: HTTP 轮询设备数据，将原始 TSL items 解析为结构化对象
 * 
 * 接口契约 (§3.3):
 *   startPoll(onData: (items, deviceTime) → void, onStatus: (str) → void) → void
 *   stopPoll() → void
 *   parseItems(items, isAlarm) → {u, raw}
 */
const config = require('../utils/config');
const logger = require('../utils/logger');

const ID_MAP = {
  1: 'temp_val', 2: 'humid_val', 3: 'speed_val',
  4: 'lat_val', 5: 'signal_val', 6: 'alarm_type_val',
  7: 'alarm_level_val', 8: 'lon_val', 9: 'alt_val',
};
const SIGNAL_TEXT = { 3: '良好', 2: '一般', 1: '差', 0: '无' };

var _timer = null;
var _onData = null;
var _onStatus = null;

function getToken() {
  var app = getApp();
  return app.globalData.token || '';
}

function startPoll(onData, onStatus) {
  _onData = onData;
  _onStatus = onStatus;
  _status('连接中...');
  _fetchDevice();
  _timer = setInterval(_fetchDevice, 2000);
}

function stopPoll() {
  if (_timer) { clearInterval(_timer); _timer = null; }
  logger.flush();
}

function _fetchDevice() {
  var url = config.BASE_URL + '/v2/binding/enduserapi/getDeviceBusinessAttributes?pk=' + config.PRODUCT_KEY + '&dk=' + config.DEVICE_KEY;

  wx.request({
    url: url,
    method: 'GET',
    header: {
      'accept': '*/*',
      'Authorization': getToken(),
    },
    success: function(res) {
      var d = res.data;
      if (d && d.code === 200 && d.data && d.data.customizeTslInfo) {
        var items = d.data.customizeTslInfo;
        var updateTime = (d.data.deviceData || {}).updateTime || 0;
        var now = Date.now();
        var stale = (now - updateTime) > 15000;
        var age = Math.floor((now - updateTime) / 1000);

        _status(stale ? '设备离线 (' + age + 's)' : '在线 (' + items.length + ' 条)');
        logger.log('QC', '轮询 ─── ' + (stale ? '⚠离线' : '✓在线') + ' age=' + age + 's');
        items.forEach(function(it) {
          logger.log('QC', 'abId=' + it.abId + '  ' + (it.resourceCode || '').padEnd(18) + ' = ' + it.resourceValce);
        });

        if (_onData) {
          _onData(items, { stale: stale, age: age, updateTime: updateTime });
        }
      } else if (d && d.code === 5032) {
        _status('Token 过期 — 需重新登录');
        logger.log('QC', 'ERROR: Token 过期');
      } else {
        _status('数据异常: ' + (d ? d.code + '/' + d.msg : '无响应'));
      }
    },
    fail: function(err) {
      _status('网络错误: ' + err.errMsg);
      logger.log('QC', 'ERROR: 网络错误 ' + err.errMsg);
    },
  });
}

function _status(str) {
  logger.log('QC', '状态: ' + str);
  if (_onStatus) _onStatus(str);
}

/**
 * 解析 TSL items → 页面显示数据 + 缓存原始值
 * @param {Array} items  - TSL items[{abId, resourceCode, resourceValce}]
 * @param {boolean} isAlarm - 跳过温湿度/速度
 * @returns {{ u: object, raw: object }}
 *   u  = {temp, humid, speed, lat, lon, alt, signal, alarm, time} — 显示用字符串
 *   raw = {temp, humid, speed, lat, lon, alt, signal, alarmType, alarmLevel, time} — 缓存用数值
 */
function parseItems(items, isAlarm) {
  var u = {
    temp: '--', humid: '--', speed: '--',
    lat: '--', lon: '--', alt: '--',
    signal: '--', alarm: '正常',
    time: '',
  };
  var raw = { time: Date.now() };
  var alarmType = '';
  var alarmLevel = '';

  items.forEach(function(it) {
    var field = ID_MAP[it.abId];
    if (!field) return;

    if (isAlarm && (field === 'temp_val' || field === 'humid_val' || field === 'speed_val')) {
      return;
    }

    var v = it.resourceValce;
    var n = Number(v);

    switch (field) {
      case 'temp_val':
        raw.temp = n; u.temp = n.toFixed(1) + '°C'; break;
      case 'humid_val':
        raw.humid = n; u.humid = n.toFixed(1) + '%'; break;
      case 'speed_val':
        raw.speed = n; u.speed = n.toFixed(1) + ' km/h'; break;
      case 'lat_val':
        raw.lat = n; u.lat = n.toFixed(4); break;
      case 'lon_val':
        raw.lon = n; u.lon = n.toFixed(4); break;
      case 'alt_val':
        raw.alt = n; u.alt = n.toFixed(1) + 'm'; break;
      case 'signal_val':
        raw.signal = n; u.signal = SIGNAL_TEXT[n] || '--'; break;
      case 'alarm_type_val':
        raw.alarmType = { 1: '碰撞', 2: 'SOS' }[n] || '';
        raw.alarm = n; break;
      case 'alarm_level_val':
        raw.alarmLevel = n;
        break;
    }
  });

  u.time = new Date().toLocaleTimeString();

  if (raw.alarmType) {
    u.alarm = raw.alarmType + ' Lv' + raw.alarmLevel;
  }

  return { u: u, raw: raw };
}

module.exports = { startPoll: startPoll, stopPoll: stopPoll, parseItems: parseItems };
