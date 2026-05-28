/**
 * 登录页 — 手机号 + 密码登录 QuecCloud
 */
var config;
var crypto;
try {
  config = require('../../utils/config');
  crypto = require('../../utils/crypto');
} catch (e) {
  console.error('Login page require failed:', e);
}

Page({
  data: {
    phone: '13368190189',
    pwd: '',
    loading: false,
    error: '',
  },

  onPhoneInput(e) { this.setData({ phone: e.detail.value, error: '' }); },
  onPwdInput(e)  { this.setData({ pwd: e.detail.value, error: '' }); },

  onLogin() {
    const phone = this.data.phone.trim();
    const pwd = this.data.pwd;
    if (!phone || phone.length !== 11) {
      this.setData({ error: '请输入正确的 11 位手机号' });
      return;
    }
    if (!pwd || pwd.length < 6) {
      this.setData({ error: '密码至少 6 位' });
      return;
    }

    this.setData({ loading: true, error: '' });

    // 1. 加密密码
    const rand = crypto.random16();
    const epwd = crypto.encryptPassword(pwd, rand);

    // 2. 计算签名: SHA256(internationalCode + phone + pwd + random + userDomainSecret)
    const sigRaw = '86' + phone + epwd + rand + config.USER_DOMAIN_SECRET;
    const sig = crypto.sha256(sigRaw);

    // 3. 调用登录 API
    const url = config.BASE_URL + '/v2/enduser/enduserapi/phonePwdLogin'
      + '?internationalCode=86'
      + '&phone=' + phone
      + '&pwd=' + encodeURIComponent(epwd)
      + '&random=' + rand
      + '&signature=' + sig
      + '&userDomain=' + config.USER_DOMAIN;

    wx.request({
      url: url,
      method: 'POST',
      header: { 'accept': '*/*' },
      success: (res) => {
        this.setData({ loading: false });
        const d = res.data;
        if (d && d.code === 200 && d.data && d.data.accessToken) {
          // 登录成功 — 存 token 到全局
          const app = getApp();
          app.globalData.token = d.data.accessToken.token;
          app.globalData.refreshToken = d.data.refreshToken.token;

          // 跳转首页（redirectTo 不保留登录页在返回栈）
          wx.reLaunch({ url: '/pages/index/index' });
        } else {
          const msg = d ? (d.msg || '登录失败') : '网络错误';
          this.setData({ error: msg });
        }
      },
      fail: (err) => {
        this.setData({ loading: false, error: '网络错误: ' + err.errMsg });
      },
    });
  },
});
