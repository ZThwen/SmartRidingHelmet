/**
 * 自定义底部导航栏 — 骑行/控制切换 + 浮动骑行/导航按钮
 *
 * v3 修复：渲染不及时问题
 *  - wx:if→hidden（DOM 不销毁，切换更可靠）
 *  - eventBus 自动同步（ride:start/end + nav:stateChange）
 *  - getTabBar() 仅作兜底，不再依赖页面手动 _syncTabBar
 *  - 取消导航→结束导航（用户预期语义）
 */
var app = getApp();
var NavService = require('../services/navigation-service');
var RideService = require('../services/ride-service');

/** 导航活跃状态：planning(规划中) / navigating(导航中) / paused(暂停) */
function _isNavActive(navState) {
  return navState === 'navigating' || navState === 'paused' || navState === 'planning';
}

Component({
  data: {
    selected: 0,  // 0=骑行, 1=控制
    riding: false,
    isNavigating: false,
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
      if (this.data.selected === 1) {
        // 在控制页点击"开始骑行"/"结束骑行"→ 跳回骑行页
        wx.redirectTo({ url: '/pages/index/index' });
        return;
      }
      var pages = getCurrentPages();
      var current = pages[pages.length - 1];
      if (current && current.onToggleRide) {
        current.onToggleRide();
      }
    },

    onNavBtn: function() {
      // 控制页：导航操作跳回骑行页处理
      if (this.data.selected === 1) {
        wx.redirectTo({ url: '/pages/index/index' });
        return;
      }
      var pages = getCurrentPages();
      var current = pages[pages.length - 1];
      if (!current) return;

      if (this.data.isNavigating) {
        // 导航中/规划中 → 结束导航
        if (current.onCancelNavigation) {
          current.onCancelNavigation();
        }
      } else {
        // 未导航 + 骑行中 → 开始导航
        if (current.onRestartNav) {
          current.onRestartNav();
        }
      }
    },

    updateRiding: function() {
      this.setData({ riding: !!app.globalData.isRiding });
    },

    updateNav: function() {
      // 直接从 NavService 读取状态，绕过页面异步 setData
      var navState = NavService.getState().state;
      this.setData({ isNavigating: _isNavActive(navState) });
    },

    /** 全量同步 — 从全局数据 + NavService 读取真实状态 */
    _syncSelected: function() {
      var globalData = app.globalData;
      var pages = getCurrentPages();
      var currentPage = pages[pages.length - 1];
      var currentPath = currentPage ? '/' + currentPage.route : '';
      var selected = 0;
      for (var i = 0; i < this.data.tabs.length; i++) {
        if (this.data.tabs[i].pagePath === currentPath) {
          selected = i;
          break;
        }
      }
      // 直接从 NavService 读取状态，绕过页面异步 setData
      var navState = NavService.getState().state;
      this.setData({
        selected: selected,
        riding: !!globalData.isRiding,
        isNavigating: _isNavActive(navState),
        bleConnected: !!globalData.bleConnected,
      });
    },

    /** eventBus 回调 — ride:start 时自动同步骑行状态 */
    _onRideStart: function() {
      this.setData({ riding: true });
    },

    /** eventBus 回调 — ride:end 时自动同步骑行状态 */
    _onRideEnd: function() {
      this.setData({ riding: false, isNavigating: false });
    },

    /** eventBus 回调 — nav:stateChange 时自动同步导航状态 */
    _onNavStateChange: function(navState) {
      this.setData({ isNavigating: _isNavActive(navState) });
    },
  },

  lifetimes: {
    attached: function() {
      this._syncSelected();
      // 注册 eventBus 自动同步（核心修复：不再依赖页面手动 _syncTabBar）
      var bus = app.eventBus;
      if (bus) {
        bus.on('ride:start', this._onRideStart.bind(this));
        bus.on('ride:end', this._onRideEnd.bind(this));
        bus.on('nav:stateChange', this._onNavStateChange.bind(this));
      }
    },
    detached: function() {
      // 清理 eventBus 监听
      var bus = app.eventBus;
      if (bus) {
        bus.off('ride:start', this._onRideStart);
        bus.off('ride:end', this._onRideEnd);
        bus.off('nav:stateChange', this._onNavStateChange);
      }
    },
  },

  pageLifetimes: {
    show: function() {
      this._syncSelected();
    },
  },
});
