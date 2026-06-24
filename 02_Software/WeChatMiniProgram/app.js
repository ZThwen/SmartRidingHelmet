/**
 * 智能骑行头盔 — 全局入口
 */
var EventBus = require('./utils/event-bus');
var StateService = require('./services/state-service');

App({
  onLaunch: function() {
    this.eventBus = new EventBus();
    StateService.init();
  },
  globalData: {
    // 用户系统（UserService 管理）
    userInfo: null,

    // 骑行
    isRiding: false,
    rideCache: [],
    rideStartTime: 0,

    // BLE 连接状态
    bleConnected: false,
    bleStatus: '未连接',

    // 控制状态（从 t=7 回推更新）
    ctrlState: {
      lightMode: 'auto',
      brightness: 0,
      volume: 5,
      powerMode: 'active',
    },

    // 报警
    alarmActive: false,

    // 传感器数据缓存（页面切换恢复用）
    latestSensorData: null,
  },
});
