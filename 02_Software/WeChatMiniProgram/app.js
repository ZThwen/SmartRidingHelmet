/**
 * 智能骑行头盔 — 全局入口
 */
var EventBus = require('./utils/event-bus');

App({
  onLaunch: function() {
    this.eventBus = new EventBus();
  },
  globalData: {
    // 认证
    token: '',
    refreshToken: '',
    // 骑行
    isRiding: false,
    rideCache: [],
    rideStartTime: 0,
    // BLE
    bleConnected: false,
    bleStatus: '未连接',
    // 控制状态（从 t=7 回推更新）
    ctrlState: {
      lightMode: 'auto',
      lightBrightness: 0,
      volume: 5,
      powerMode: 'active',
    },
    // 报警
    alarmActive: false,
  },
});
