/**
 * EventBus 单元测试
 * 运行方式: node 02_Software/WeChatMiniProgram/Tests/test_event_bus.js
 */
var EventBus = require('../utils/event-bus');

var bus = new EventBus();
var received = null;

// 测试 on/emit
bus.on('test', function(data) { received = data; });
bus.emit('test', { value: 42 });

if (received === null || received.value !== 42) {
  console.log('FAIL: emit/on not working');
  process.exit(1);
}

// 测试 off
var count = 0;
var fn = function() { count++; };
bus.on('count', fn);
bus.emit('count');
bus.off('count', fn);
bus.emit('count');

if (count !== 1) {
  console.log('FAIL: off not working, count=' + count);
  process.exit(1);
}

console.log('PASS: all event-bus tests');
