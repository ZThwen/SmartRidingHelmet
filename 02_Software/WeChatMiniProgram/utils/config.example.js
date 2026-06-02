/**
 * 移远云 DMP 平台配置（示例文件）
 *
 * 使用方法：复制为 config.js，填入真实凭据
 * config.js 已被 .gitignore 排除，不会提交到仓库
 */
module.exports = {
  // 用户域（DMP 平台 → App 详情页）
  USER_DOMAIN: 'your_user_domain',
  USER_DOMAIN_SECRET: 'your_user_domain_secret',

  // API 地址
  BASE_URL: 'https://iot-api.quectelcn.com',

  // 设备信息
  PRODUCT_KEY: 'your_product_key',
  DEVICE_KEY: 'your_device_key',

  // BLE 配置
  BLE_SERVICE_UUID: '0000FFF0-0000-1000-8000-00805F9B34FB',
  BLE_DEVICE_PREFIX: 'SmartHelmet-',

  // 腾讯地图 WebService API
  TENCENT_MAP_KEY: 'your_tencent_map_key',
};
