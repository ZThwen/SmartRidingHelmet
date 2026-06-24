/**
 * RideService — 骑行状态管理 + 总结计算 + 轨迹点管理
 *
 * 职责:
 *   骑行生命周期、数据缓存、骑行总结、轨迹点管理
 *
 * P2 修复: trackPoints 数据所有权迁移到 RideService
 *   - trackPoints 格式: [{latitude, longitude}]（地图显示用）
 *   - 页面不再自己维护 trackPoints，从 RideService 读取
 *   - _endRide() 后 trackPoints 仍然保留（直到 clear()）
 *
 * 接口:
 *   start() → void                     重置状态，计时开始
 *   addRecord(parsed) → void           追加缓存
 *   end() → RideSummary                 停止→计算总结
 *   isActive() → bool
 *   clear() → void                      清除所有数据（包括轨迹）
 *   getCache() → []                     只读
 *   getLatestPoint() → {lat,lon}|null
 *   getTrackPoints() → []               获取轨迹点（地图显示用）
 *   addTrackPoint(lat, lon) → void      追加轨迹点
 *   getTrackPolylines() → []            获取轨迹 polyline（缓存，避免重复计算）
 *   getTrackMarkers(iconPath, cog) → [] 获取轨迹 markers（缓存）
 */
var APP = typeof getApp !== 'undefined' ? getApp : function(){ return {globalData:{}}; };
var MapService = require('./map-service');

var _trackPoints = [];
var _trackPolylines = [];
var _trackMarkers = [];
var _lastIconPath = '';
var _lastCog = null;

function start() {
  var app = APP();
  app.globalData.isRiding = true;
  app.globalData.rideCache = [];
  app.globalData.rideStartTime = Date.now();
  // P2: 重置轨迹数据
  _trackPoints = [];
  _trackPolylines = [];
  _trackMarkers = [];
  _lastIconPath = '';
  _lastCog = null;
}

function addRecord(parsed) {
  if (!isActive()) return;
  if (parsed.lat == null || parsed.lon == null) return;
  var app = APP();
  app.globalData.rideCache.push(parsed);
}

function end() {
  var app = APP();
  app.globalData.isRiding = false;
  var cache = app.globalData.rideCache || [];
  var startTime = app.globalData.rideStartTime || Date.now();
  var endTime = Date.now();

  var duration = Math.floor((endTime - startTime) / 1000);

  if (cache.length === 0 && duration < 60) return null;
  var durMin = Math.floor(duration / 60);
  var durSec = duration % 60;

  var speeds = [];
  var temps = [];
  var heartRates = [];
  var spo2Values = [];
  for (var i = 0; i < cache.length; i++) {
    if (cache[i].speed != null) speeds.push(cache[i].speed);
    if (cache[i].temp != null) temps.push(cache[i].temp);
    if (cache[i].hr != null) heartRates.push(cache[i].hr);
    if (cache[i].spo2 != null) spo2Values.push(cache[i].spo2);
  }

  var avgSpeed = speeds.length ? speeds.reduce(function(a,b){return a+b;}, 0) / speeds.length : 0;
  var maxSpeed = speeds.length ? Math.max.apply(null, speeds) : 0;
  var avgTemp = temps.length ? temps.reduce(function(a,b){return a+b;}, 0) / temps.length : 0;
  var maxTemp = temps.length ? Math.max.apply(null, temps) : 0;

  var avgHR = heartRates.length ? heartRates.reduce(function(a,b){return a+b;}, 0) / heartRates.length : null;
  var maxHR = heartRates.length ? Math.max.apply(null, heartRates) : null;
  var avgSp = spo2Values.length ? spo2Values.reduce(function(a,b){return a+b;}, 0) / spo2Values.length : null;
  var minSp = spo2Values.length ? Math.min.apply(null, spo2Values) : null;

  var hrTimeSeries = [];
  if (heartRates.length > 0) {
    var avgIntervalSec = duration / cache.length;
    var step = heartRates.length > 60 ? Math.ceil(heartRates.length / 60) : 1;
    for (var h = 0; h < cache.length; h += step) {
      if (cache[h].hr != null) {
        hrTimeSeries.push({ time: Math.round(h * avgIntervalSec), hr: cache[h].hr });
        if (hrTimeSeries.length >= 60) break;
      }
    }
  }

  var dist = 0;
  var distCount = 0;
  for (var j = 1; j < cache.length; j++) {
    var cj = cache[j], cp = cache[j-1];
    if (cj.lat != null && cp.lat != null && cj.lon != null && cp.lon != null) {
      var d = _haversine(cp.lat, cp.lon, cj.lat, cj.lon);
      if (!isNaN(d) && d < 1000) { dist += d; distCount++; }
    }
  }

  var alarmCount = 0;
  for (var k = 0; k < cache.length; k++) {
    if (cache[k].alarm && cache[k].alarm !== 0) alarmCount++;
  }

  return {
    duration: durMin + '分' + durSec + '秒',
    avgSpeed: avgSpeed.toFixed(1) + ' km/h',
    maxSpeed: maxSpeed.toFixed(1) + ' km/h',
    avgTemp: avgTemp.toFixed(1) + '°C',
    maxTemp: maxTemp.toFixed(1) + '°C',
    avgHeartRate: avgHR != null ? avgHR.toFixed(1) + ' bpm' : '--',
    maxHeartRate: maxHR != null ? maxHR.toFixed(0) + ' bpm' : '--',
    avgSpO2: avgSp != null ? avgSp.toFixed(1) + '%' : '--',
    minSpO2: minSp != null ? minSp.toFixed(0) + '%' : '--',
    hrTimeSeries: hrTimeSeries,
    distance: dist < 1000 ? dist.toFixed(0) + 'm' : (dist/1000).toFixed(2) + 'km',
    alarmCount: alarmCount + ' 次',
    points: cache.length,
  };
}

function isActive() {
  var app = APP();
  return !!app.globalData.isRiding;
}

function clear() {
  var app = APP();
  app.globalData.isRiding = false;
  app.globalData.rideCache = [];
  app.globalData.rideStartTime = 0;
  // P2: clear 时也清空轨迹
  _trackPoints = [];
  _trackPolylines = [];
  _trackMarkers = [];
  _lastIconPath = '';
  _lastCog = null;
}

function getCache() {
  var app = APP();
  return (app.globalData.rideCache || []).slice();
}

function getLatestPoint() {
  var app = APP();
  var cache = app.globalData.rideCache || [];
  if (cache.length === 0) return null;
  var last = cache[cache.length - 1];
  if (last.lat != null && last.lon != null) {
    return { lat: last.lat, lon: last.lon };
  }
  return null;
}

// ==================== P2: 轨迹点管理 ====================

/**
 * 追加轨迹点（坐标变化时调用）
 * @param {number} lat 纬度
 * @param {number} lon 经度
 */
function addTrackPoint(lat, lon) {
  // 去重：坐标与上一个点相同时不添加（避免静止时浪费 MAX_POINTS 预算）
  if (_trackPoints.length > 0) {
    var last = _trackPoints[_trackPoints.length - 1];
    if (last.latitude === lat && last.longitude === lon) return;
  }
  _trackPoints = MapService.pushPoint(_trackPoints, lat, lon);
  // 更新缓存的 polyline 和 markers
  _trackPolylines = MapService.buildPolyline(_trackPoints);
}

/**
 * 获取轨迹点数组（只读）
 * @returns {Array} [{latitude, longitude}, ...]
 */
function getTrackPoints() {
  return _trackPoints.slice();
}

/**
 * 获取轨迹 polyline（缓存）
 * @returns {Array} polyline 数组
 */
function getTrackPolylines() {
  return _trackPolylines;
}

/**
 * 获取轨迹 markers（带图标和方向）
 * @param {string} iconPath 蓝点图标路径
 * @param {number|null} cog 方向角
 * @returns {Array} markers 数组
 */
function getTrackMarkers(iconPath, cog) {
  _trackMarkers = MapService.buildMarker(_trackPoints, iconPath, cog);
  return _trackMarkers;
}

/**
 * 获取轨迹点数量
 */
function getTrackPointCount() {
  return _trackPoints.length;
}

/** Haversine 球面距离 (米) — 内部使用 */
function _haversine(lat1, lon1, lat2, lon2) {
  var R = 6371000;
  var dLat = (lat2 - lat1) * Math.PI / 180;
  var dLon = (lon2 - lon1) * Math.PI / 180;
  var a = Math.sin(dLat/2)*Math.sin(dLat/2) +
          Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) *
          Math.sin(dLon/2)*Math.sin(dLon/2);
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

module.exports = {
  start: start, addRecord: addRecord, end: end,
  isActive: isActive, clear: clear,
  getCache: getCache, getLatestPoint: getLatestPoint,
  addTrackPoint: addTrackPoint,
  getTrackPoints: getTrackPoints,
  getTrackPolylines: getTrackPolylines,
  getTrackMarkers: getTrackMarkers,
  getTrackPointCount: getTrackPointCount,
};
