/**
 * NavigationService — 路线规划 + 导航状态机 + BLE 指令推送
 *
 * 职责: 调用腾讯地图 WebService API 算路，解析逐条拐弯指令，
 *       每 5 秒通过 BLE FFF2 推送当前指令到头盔
 *
 * 状态机: idle → planning → navigating → arrived / cancelled
 *                                    ↕ (报警暂停)
 *                                  paused
 */
var config = require('../utils/config');
var BleService = require('./ble-service');
var logger = require('../utils/logger');

var PUSH_INTERVAL = 5000; // 5 秒推送间隔

var _state = {
  state: 'idle',      // idle | planning | navigating | paused | arrived | cancelled
  dest: null,         // {lat, lng, name}
  steps: [],          // [{instruction, road_name, distance, action}]
  stepIndex: 0,
  routePolyline: [],  // 解压后的坐标 [{latitude, longitude}]
  totalDistance: 0,
  remainDistance: 0,
  _timer: null,
  _onStateChange: null, // 状态变化回调 (state) → void
};

// ==================== 公开接口 ====================

function selectDestination() {
  return new Promise(function(resolve, reject) {
    wx.chooseLocation({
      success: function(res) {
        if (res.latitude && res.longitude) {
          resolve({ lat: res.latitude, lng: res.longitude, name: res.name || '目的地' });
        } else {
          reject(new Error('未获取到位置'));
        }
      },
      fail: function(err) {
        reject(err);
      },
    });
  });
}

function startNavigation(dest, origin) {
  if (_state.state !== 'idle' && _state.state !== 'arrived' && _state.state !== 'cancelled') {
    return;
  }

  _state.state = 'planning';
  _state.dest = dest;
  _notifyState();

  logger.log('NAV', '开始规划路线 → ' + dest.name);

  if (origin && origin.lat && origin.lng) {
    // 用板子 BLE 坐标做路线规划起点
    logger.log('NAV', '使用板子坐标: ' + origin.lat + ', ' + origin.lng);
    _fetchRoute(origin.lat, origin.lng, dest.lat, dest.lng);
  } else {
    // fallback 手机 GPS
    wx.getLocation({
      type: 'gcj02',
      isHighAccuracy: true,
      success: function(res) {
        _fetchRoute(res.latitude, res.longitude, dest.lat, dest.lng);
      },
      fail: function() {
        _fetchRoute(22.5431, 113.9523, dest.lat, dest.lng);
      },
    });
  }
}

function stopNavigation(reason) {
  _clearTimer();
  _state.state = reason; // 'arrived' or 'cancelled'
  _state.stepIndex = 0;
  _notifyState();

  logger.log('NAV', '导航结束: ' + reason);

  // 通知头盔导航结束
  if (BleService.isConnected()) {
    var dir = reason === 'arrived' ? 'arrive' : 'cancel';
    BleService.sendNav(dir, 0, '');
  }
}

function pause() {
  if (_state.state === 'navigating') {
    _clearTimer();
    _state.state = 'paused';
    _notifyState();
    logger.log('NAV', '导航暂停');
  }
}

function resume() {
  if (_state.state === 'paused') {
    _state.state = 'navigating';
    _notifyState();
    _startTimer();
    logger.log('NAV', '导航恢复');
  }
}

function getState() {
  return {
    state: _state.state,
    stepIndex: _state.stepIndex,
    steps: _state.steps,
    dest: _state.dest,
    totalDistance: _state.totalDistance,
    remainDistance: _state.remainDistance,
    routePolyline: _state.routePolyline,
  };
}

function isNavigating() {
  return _state.state === 'navigating';
}

function getCurrentInstruction() {
  if (_state.state !== 'navigating' && _state.state !== 'paused') return null;
  if (_state.stepIndex <= 0 || _state.steps.length === 0) return null;
  var step = _state.steps[_state.stepIndex - 1];
  return {
    instruction: step.instruction,
    road_name: step.road_name,
    distance: step.distance,
    action: step.action,
  };
}

function onStateChange(callback) {
  _state._onStateChange = callback;
}

// ==================== 内部实现 ====================

function _fetchRoute(fromLat, fromLng, toLat, toLng) {
  var key = config.TENCENT_MAP_KEY;
  var url = 'https://apis.map.qq.com/ws/direction/v1/bicycling/'
    + '?from=' + fromLat + ',' + fromLng
    + '&to=' + toLat + ',' + toLng
    + '&key=' + key;

  wx.request({
    url: url,
    method: 'GET',
    success: function(res) {
      if (res.data && res.data.status === 0 && res.data.result && res.data.result.routes && res.data.result.routes.length > 0) {
        var route = res.data.result.routes[0];
        _parseRoute(route);
      } else {
        logger.log('NAV', '算路失败: ' + (res.data ? res.data.message : '无响应'));
        _state.state = 'idle';
        _notifyState();
      }
    },
    fail: function(err) {
      logger.log('NAV', '请求失败: ' + err.errMsg);
      _state.state = 'idle';
      _notifyState();
    },
  });
}

/**
 * 腾讯地图 act_desc → 板子方向值
 * act_desc: 左转/右转/偏左转/偏右转/左后转/右后转/左转掉头/直行/空
 */
function _mapActDesc(actDesc) {
  if (actDesc === '左转') return 'left';
  if (actDesc === '右转') return 'right';
  if (actDesc === '偏左转') return 'slight_left';
  if (actDesc === '偏右转') return 'slight_right';
  if (actDesc === '左后转' || actDesc === '右后转' || actDesc === '左转掉头') return 'uturn';
  if (actDesc === '直行') return 'straight';
  if (actDesc === '' || actDesc === '到达') return 'arrive';
  return 'straight';
}

function _parseRoute(route) {
  // 解压 polyline 坐标（前向差分解压）
  _state.routePolyline = _decodePolyline(route.polyline || []);

  // 解析 steps（用 act_desc 映射方向）
  _state.steps = (route.steps || []).map(function(step) {
    return {
      instruction: step.instruction || '',
      road_name: step.road_name || '',
      distance: step.distance || 0,
      action: _mapActDesc(step.act_desc || ''),
    };
  });

  _state.totalDistance = route.distance || 0;
  _state.remainDistance = route.distance || 0;
  _state.stepIndex = 0;

  logger.log('NAV', '路线就绪: ' + _state.steps.length + ' 步, ' + _state.totalDistance + 'm');

  // 切换到导航状态
  _state.state = 'navigating';
  _notifyState();

  // 推送第一条指令
  updateStep();
  _startTimer();
}

/**
 * 腾讯地图 polyline 差分解压
 * 第一个点是绝对坐标，后续是相对前一个点的偏移量
 */
/**
 * 腾讯地图 polyline 前向差分解压
 * 官方格式：[lat1, lng1, delta_lat2, delta_lng2, ...]
 * 解压：coors[i] = coors[i-2] + coors[i] / 1e6
 */
function _decodePolyline(coors) {
  if (!coors || coors.length < 2) return [];

  // 前向差分解压（参考腾讯地图官方示例）
  var kr = 1000000;
  for (var i = 2; i < coors.length; i++) {
    coors[i] = Number(coors[i - 2]) + Number(coors[i]) / kr;
  }

  // 转为 [{latitude, longitude}, ...] 格式
  var points = [];
  for (var i = 0; i < coors.length; i += 2) {
    points.push({ latitude: coors[i], longitude: coors[i + 1] });
  }
  return points;
}

function _startTimer() {
  _clearTimer();
  _state._timer = setInterval(function() {
    updateStep();
  }, PUSH_INTERVAL);
}

function _clearTimer() {
  if (_state._timer) {
    clearInterval(_state._timer);
    _state._timer = null;
  }
}

function updateStep() {
  if (_state.state !== 'navigating') return;
  if (_state.stepIndex >= _state.steps.length) {
    stopNavigation('arrived');
    return;
  }

  var step = _state.steps[_state.stepIndex];

  // 通过 BLE 推送到头盔
  if (BleService.isConnected()) {
    BleService.sendNav(step.action, step.distance, step.road_name);
    logger.log('NAV', '推送 [' + _state.stepIndex + '] ' + step.instruction);
  } else {
    logger.log('NAV', 'BLE 未连接，跳过推送');
  }

  // 更新剩余距离
  _state.remainDistance -= step.distance;
  if (_state.remainDistance < 0) _state.remainDistance = 0;

  // 前进到下一步
  _state.stepIndex++;
  _notifyState();
}

function _notifyState() {
  if (_state._onStateChange) {
    _state._onStateChange(_state.state);
  }
}

module.exports = {
  selectDestination: selectDestination,
  startNavigation: startNavigation,
  stopNavigation: stopNavigation,
  pause: pause,
  resume: resume,
  getState: getState,
  isNavigating: isNavigating,
  getCurrentInstruction: getCurrentInstruction,
  updateStep: updateStep,
  onStateChange: onStateChange,
};
