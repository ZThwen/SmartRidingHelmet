/**
 * 自定义底部导航栏 — 骑行/控制切换 + 浮动骑行/导航按钮
 *
 * v2 修复：updateNav/_syncSelected 直接从 NavService 读取状态，
 *          绕过页面异步 setData 导致读到旧数据的 bug；
 *          isNavigating 包含 planning 状态；
 *          onNavBtn 处理控制页场景。
 */
var app = getApp();
var NavService = require('../services/navigation-service');

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
        // 导航中/规划中 → 取消导航
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
        riding: globalData.isRiding,
        isNavigating: _isNavActive(navState),
        bleConnected: globalData.bleConnected,
      });
    },
  },

  lifetimes: {
    attached: function() {
      this._syncSelected();
    },
  },

  pageLifetimes: {
    show: function() {
      this._syncSelected();
    },
  },
});
