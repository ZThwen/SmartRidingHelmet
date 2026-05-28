/**
 * 移远云 DMP 平台配置
 * 
 * OpenAPI BaseURL：iot-api.quectelcn.com（中国数据中心）
 * API 路径前缀：/v2/enduser/enduserapi/
 */
module.exports = {
  // ========== 用户域（DMP 平台 → App 详情页） ==========
  USER_DOMAIN: 'C.DM.1507151130577592.1',
  USER_DOMAIN_SECRET: '9hGmrVHHK2RQVmAi9nR6TLbhMF8w5diWhF1wshk2P4TS',

  // ========== API 地址 ==========
  BASE_URL: 'https://iot-api.quectelcn.com',

  // ========== 设备信息 ==========
  PRODUCT_KEY: 'p11yMv',
  DEVICE_KEY: '66ccff',

  // ========== BLE 配置 ==========
  BLE_SERVICE_UUID: '0000FFF0-0000-1000-8000-00805F9B34FB',
  BLE_DEVICE_PREFIX: 'SmartHelmet-',
};
