/**
 * 登录页 — UserService stub 登录
 *
 * 移远云登录已移除（2026-06-24）
 * 当前使用 UserService 本地 stub，未来接入云端后端
 */
var UserService = require('../../services/user-service');

Page({
  data: {
    phone: '',
    pwd: '',
    loading: false,
    error: '',
  },

  onLoad: function() {
    // 自动登录检查：如果本地有缓存，直接跳转
    if (UserService.isLoggedIn()) {
      var app = getApp();
      app.globalData.userInfo = UserService.getUserInfo();
      wx.reLaunch({ url: '/pages/index/index' });
    }
  },

  onPhoneInput: function(e) {
    this.setData({ phone: e.detail.value, error: '' });
  },

  onPwdInput: function(e) {
    this.setData({ pwd: e.detail.value, error: '' });
  },

  onLogin: function() {
    var that = this;
    var phone = this.data.phone.trim();
    var pwd = this.data.pwd;

    if (!phone || phone.length !== 11) {
      this.setData({ error: '请输入正确的 11 位手机号' });
      return;
    }
    if (!pwd || pwd.length < 6) {
      this.setData({ error: '密码至少 6 位' });
      return;
    }

    this.setData({ loading: true, error: '' });

    UserService.login(phone, pwd).then(function(userInfo) {
      // 登录成功 — 写入 globalData
      var app = getApp();
      app.globalData.userInfo = userInfo;

      that.setData({ loading: false });
      wx.reLaunch({ url: '/pages/index/index' });
    }).catch(function(err) {
      that.setData({ loading: false, error: err.message || '登录失败' });
    });
  },
});
