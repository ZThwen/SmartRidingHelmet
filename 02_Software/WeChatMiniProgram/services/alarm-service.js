/**
 * AlarmService — 报警检测 + 显示规则
 * 
 * C3 组件层: AlarmComponent
 * 职责: 纯函数，确定报警显示内容和弹窗规则
 * 
 * 接口 (§3.3):
 *   analyze(isAlarm, alarmType, alarmLevel) → AlarmResult
 *   AlarmResult = { displayText, shouldPopup, icon, popupClass }
 * 
 * 规则:
 *   碰撞 Lv1  → 卡片红字，不弹窗
 *   碰撞 Lv2+ → 卡片红字 + 全屏弹窗
 *   SOS 任意  → 卡片红字 + 全屏弹窗(闪烁)
 *   alarm 清除 → displayText='正常', shouldPopup=false
 */
var ALARM_MAP = { 1: '碰撞', 2: 'SOS' };

function analyze(alarmType, alarmLevel) {
  var result = {
    displayText: '正常',
    shouldPopup: false,
    icon: '',
    popupClass: '',
  };

  if (!alarmType || alarmType === 0) return result;

  var typeName = ALARM_MAP[alarmType] || '';
  var levelNum = Number(alarmLevel) || 0;
  result.displayText = typeName + ' Lv' + levelNum;

  // 碰撞 Lv1 → 不弹窗
  if (typeName === '碰撞' && levelNum < 2) return result;

  // 碰撞 Lv2+ 或 SOS → 全屏弹窗
  result.shouldPopup = true;
  if (typeName === 'SOS') {
    result.icon = '🆘';
    result.popupClass = 'sos';
  } else {
    result.icon = '💥';
    result.popupClass = '';
  }

  return result;
}

module.exports = { analyze: analyze };
