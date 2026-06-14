/**
 * EventBus — 简易事件发射器
 * 用于跨页面状态通知（报警、控制状态、BLE 连接）
 */
function EventBus() {
  this._listeners = {};
}

EventBus.prototype.on = function(event, fn) {
  if (!this._listeners[event]) this._listeners[event] = [];
  this._listeners[event].push(fn);
};

EventBus.prototype.off = function(event, fn) {
  var list = this._listeners[event];
  if (!list) return;
  for (var i = list.length - 1; i >= 0; i--) {
    if (list[i] === fn) list.splice(i, 1);
  }
};

EventBus.prototype.emit = function(event, data) {
  var list = this._listeners[event];
  if (!list) return;
  for (var i = 0; i < list.length; i++) {
    list[i](data);
  }
};

module.exports = EventBus;
