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
function buildMarker(points, label) {
  if (!points || points.length === 0) return [];
  var last = points[points.length - 1];
  return [{
    id: 1,
    latitude: last.latitude,
    longitude: last.longitude,
    width: 16,
    height: 16,
    callout: {
      content: label || '头盔',
      fontSize: 11,
      borderRadius: 4,
      padding: 4,
      display: 'ALWAYS',
    },
  }];
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

module.exports = { buildPolyline: buildPolyline, buildMarker: buildMarker, pushPoint: pushPoint, MAX_POINTS: MAX_POINTS };
