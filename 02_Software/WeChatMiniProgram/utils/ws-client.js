/**
 * ws-client.js — 兼容层，转发到 services/data-service.js
 * 
 * 旧代码 (login.js 等) 通过 require('./ws-client') 引入 QuecClient 类。
 * 新版推荐直接 require('../../services/data-service')。
 * 
 * 2026-05-23: 业务逻辑已迁移到 services/，此文件保持接口兼容。
 */
module.exports = require('../services/data-service');
