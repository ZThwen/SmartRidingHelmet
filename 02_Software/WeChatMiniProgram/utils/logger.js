/**
 * 日志 — console + 本地文件（最多 1000 条）
 * 文件: app.log（小程序数据目录）
 */
var _start = Date.now();
var _queue = [];
var _fileOk = false;

function _ts() {
  return ((Date.now() - _start) / 1000).toFixed(2) + 's';
}

function init() {
  _start = Date.now();
  try {
    var fs = wx.getFileSystemManager();
    // 直接写文件名，自动存到小程序数据目录
    fs.writeFileSync('app.log', '', 'utf8');
    _fileOk = true;
    console.log('[LOG] 文件日志已启动');
  } catch (e) {
    _fileOk = false;
    console.log('[LOG] 文件日志不可用: ' + e.message);
  }
}

function log(tag, msg) {
  var line = '[' + _ts() + '] [' + tag + '] ' + msg;
  console.log(line);
  if (!_fileOk) return;

  _queue.push(line);
  if (_queue.length >= 5) _flush();
}

function _flush() {
  if (!_fileOk || _queue.length === 0) return;
  try {
    var fs = wx.getFileSystemManager();
    var text = _queue.join('\n') + '\n';
    _queue = [];
    fs.appendFileSync('app.log', text, 'utf8');

    // 限制 1000 行
    var content = fs.readFileSync('app.log', 'utf8');
    var lines = content.split('\n').filter(function(l) { return l.length > 0; });
    if (lines.length > 1000) {
      fs.writeFileSync('app.log', lines.slice(-1000).join('\n') + '\n', 'utf8');
    }
  } catch (e) {}
}

function flush() { _flush(); }

module.exports = { init: init, log: log, flush: flush };
