/**
 * UserService — 用户系统占位（stub）
 *
 * 当前为本地 stub，无云端后端。
 * 接口预留：
 *   login(phone, pwd)  → Promise(userInfo)   手机号+密码登录
 *   logout()            → void                注销
 *   isLoggedIn()        → boolean             是否已登录
 *   getUserInfo()       → userInfo|null       获取用户信息
 *
 * TODO: 接入云端用户系统后替换内部实现
 */

var STORAGE_KEY = 'smart_helmet_user';

var _userInfo = null;

/**
 * 登录 stub — 目前仅做本地存储，不做真实认证
 * @param {string} phone 手机号
 * @param {string} pwd   密码（当前 stub 不验证）
 * @returns {Promise<object>} userInfo
 */
function login(phone, pwd) {
  return new Promise(function(resolve, reject) {
    // 前端格式校验
    if (!phone || phone.length !== 11) {
      reject(new Error('请输入正确的 11 位手机号'));
      return;
    }
    if (!pwd || pwd.length < 6) {
      reject(new Error('密码至少 6 位'));
      return;
    }

    // stub: 直接创建用户信息并本地存储
    _userInfo = {
      phone: phone,
      nickname: '骑手_' + phone.slice(-4),
      avatarUrl: '',
      loginTime: Date.now(),
    };

    // 持久化到微信本地存储
    try {
      wx.setStorageSync(STORAGE_KEY, _userInfo);
    } catch (e) {
      // 存储失败不影响使用
    }

    resolve(_userInfo);
  });
}

/**
 * 注销 — 清除本地存储 + 全局缓存
 */
function logout() {
  _userInfo = null;
  try {
    wx.removeStorageSync(STORAGE_KEY);
  } catch (e) {
    // 忽略
  }
}

/**
 * 是否已登录
 */
function isLoggedIn() {
  if (_userInfo) return true;
  // 尝试从本地存储恢复
  try {
    var stored = wx.getStorageSync(STORAGE_KEY);
    if (stored && stored.phone) {
      _userInfo = stored;
      return true;
    }
  } catch (e) {
    // 忽略
  }
  return false;
}

/**
 * 获取用户信息
 * @returns {object|null} {phone, nickname, avatarUrl, loginTime}
 */
function getUserInfo() {
  if (!_userInfo) {
    try {
      _userInfo = wx.getStorageSync(STORAGE_KEY) || null;
    } catch (e) {
      // 忽略
    }
  }
  return _userInfo;
}

module.exports = {
  login: login,
  logout: logout,
  isLoggedIn: isLoggedIn,
  getUserInfo: getUserInfo,
};
