/**
 * RideService — 骑行状态管理 + 总结计算
 * 
 * C3 组件层: RideComponent
 * 职责: 骑行生命周期，数据缓存，骑行总结
 * 
 * 接口 (§3.3):
 *   start() → void             重置状态，计时开始
 *   addRecord(parsed) → void   追加缓存
 *   end() → RideSummary         停止→计算总结
 *   isActive() → bool
 *   clear() → void
 *   getCache() → []             只读
 *   getLatestPoint() → {lat,lon}|null
 */
var APP = typeof getApp !== 'undefined' ? getApp : function(){ return {globalData:{}}; };

function start() {
  var app = APP();
  app.globalData.isRiding = true;
  app.globalData.rideCache = [];
  app.globalData.rideStartTime = Date.now();
}

function addRecord(parsed) {
  if (!isActive()) return;
  // 过滤无 GPS 数据的记录（避免膨胀采集点数）
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

  if (cache.length === 0) return null;

  var duration = Math.floor((endTime - startTime) / 1000);
  var durMin = Math.floor(duration / 60);
  var durSec = duration % 60;

  var speeds = [];
  var temps = [];
  for (var i = 0; i < cache.length; i++) {
    if (cache[i].speed != null) speeds.push(cache[i].speed);
    if (cache[i].temp != null) temps.push(cache[i].temp);
  }

  var avgSpeed = speeds.length ? speeds.reduce(function(a,b){return a+b;}, 0) / speeds.length : 0;
  var maxSpeed = speeds.length ? Math.max.apply(null, speeds) : 0;
  var avgTemp = temps.length ? temps.reduce(function(a,b){return a+b;}, 0) / temps.length : 0;
  var maxTemp = temps.length ? Math.max.apply(null, temps) : 0;

  // Haversine 里程
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

module.exports = { start: start, addRecord: addRecord, end: end, isActive: isActive, clear: clear, getCache: getCache, getLatestPoint: getLatestPoint };
