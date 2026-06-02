/**
 * MapService — 地图轨迹 + 标记生成
 * 
 * C3 组件层: MapComponent
 * 职责: 纯函数，根据坐标点生成 polyline 和 markers
 * 
 * 接口 (§3.3):
 *   buildPolyline(points) → [{points, color, width, arrowLine}]
 *   buildMarker(point, label) → [{id, latitude, longitude, width, height, callout}]
 *   MAX_POINTS = 500
 */
var MAX_POINTS = 500;
var LINE_COLOR = '#66ccff';

/**
 * 从坐标点数组生成 polyline
 * @param {Array} points - [{latitude, longitude}, ...]
 * @returns {Array} polylines - 空或长度为 1
 */
function buildPolyline(points) {
  if (!points || points.length < 2) return [];
  return [{
    points: points,
    color: LINE_COLOR,
    width: 4,
    arrowLine: true,
  }];
}

/**
 * 在最后一个点生成标记
 * @param {Array} points - [{latitude, longitude}, ...]
 * @param {string} label - 标记文字
 * @returns {Array} markers
 */
function buildMarker(points, iconPath) {
  if (!points || points.length === 0) return [];
  var last = points[points.length - 1];
  var marker = {
    id: 1,
    latitude: last.latitude,
    longitude: last.longitude,
    width: 20,
    height: 20,
  };
  if (iconPath) {
    marker.iconPath = iconPath;
  }
  return [marker];
}

/**
 * 追加一个点，超出上限时删最早
 */
function pushPoint(points, lat, lon) {
  var newPoints = points.slice();
  newPoints.push({ latitude: lat, longitude: lon });
  if (newPoints.length > MAX_POINTS) newPoints.shift();
  return newPoints;
}

/**
 * 构建规划路线 polyline（绿色，与蓝色轨迹区分）
 * @param {Array} points - [{latitude, longitude}, ...]
 * @returns {Array} polylines
 */
function buildRoutePolyline(points) {
  if (!points || points.length < 2) return [];
  return [{
    points: points,
    color: '#00e676',
    width: 5,
  }];
}

/**
 * 构建目的地 marker
 * @param {number} lat
 * @param {number} lon
 * @param {string} name
 * @returns {Array} markers
 */
function buildDestMarker(lat, lon, name) {
  return [{
    id: 999,
    latitude: lat,
    longitude: lon,
    width: 24,
    height: 24,
    callout: {
      content: name || '目的地',
      color: '#ffffff',
      bgColor: '#00e676',
      borderRadius: 8,
      padding: 6,
      fontSize: 12,
      display: 'ALWAYS',
    },
  }];
}

module.exports = {
  buildPolyline: buildPolyline,
  buildMarker: buildMarker,
  pushPoint: pushPoint,
  buildRoutePolyline: buildRoutePolyline,
  buildDestMarker: buildDestMarker,
  MAX_POINTS: MAX_POINTS,
};
