/**
 * 自定义底部导航栏 — 骑行/控制切换 + 浮动骑行按钮
 */
var app = getApp();

Component({
  data: {
    selected: 0,  // 0=骑行, 1=控制
    riding: false,
    bleConnected: false,
    tabs: [
      { pagePath: '/pages/index/index', text: '骑行', icon: '🚴' },
      { pagePath: '/pages/control/control', text: '控制', icon: '⚙' },
    ],
  },

  methods: {
    switchTab: function(e) {
      var index = e.currentTarget.dataset.index;
      var tab = this.data.tabs[index];
      if (this.data.selected === index) return;
      wx.redirectTo({ url: tab.pagePath });
    },

    onRideBtn: function() {
      // 控制页点击骑行按钮 → 跳回骑行页
      if (this.data.selected === 1) {
        wx.redirectTo({ url: '/pages/index/index' });
        return;
      }
      // 骑行页 → 触发页面的 onToggleRide
      var pages = getCurrentPages();
      var current = pages[pages.length - 1];
      if (current && current.onToggleRide) {
        current.onToggleRide();
      }
    },
  },

  pageLifetimes: {
    show: function() {
      var globalData = app.globalData;
      this.setData({
        riding: globalData.isRiding,
        bleConnected: globalData.bleConnected,
      });
    },
  },
});
