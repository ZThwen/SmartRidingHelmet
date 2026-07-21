/**
 * 首页 — 薄调度器
 *
 * P1 修复: BLE 数据路由已迁移到 StateService，
 * 页面仅通过 EventBus 接收状态更新。
 * 不再有 _restoreBleCallbacks 或 onToggleBle 中的重复 onData 逻辑。
 */
var RideService = require('../../services/ride-service');
var MapService = require('../../services/map-service');
var BleService = require('../../services/ble-service');
var NavService = require('../../services/navigation-service');
var StateService = require('../../services/state-service');
var logger = require('../../utils/logger');
var app = getApp();

Page({
  data: {
    statusBarHeight: 44,
    status: '未开始',
    isOnline: false,
    bleStatus: '未连接',
    bleConnected: false,
    bleDevices: [],
    showBlePicker: false,
    temp: '--', humid: '--', speed: '--', cog: '--',
    lat: '--', lon: '--', alt: '--',
    lux: '--', battery: '--', alarm: '正常', time: '',
    heartRate: '--', spo2: '--', heartClass: '', spo2Class: '', heartIcon: '\u2665',
    riding: false,
    btnText: '开始骑行',
    btnClass: 'btn-start',
    mapExpanded: false,
    mapHeight: 360,
    mapFollowing: true,
    mapLat: 22.5431,
    mapLon: 113.9523,
    trackPoints: [],
    trackPolylines: [],
    trackMarkers: [],
    showSummary: false,
    summary: {},
    showAlarmPopup: false,
    alarmPopupClass: '',
    alarmPopupData: { icon: '', type: '', level: '', lat: '', lon: '', time: '' },

    // 总结弹窗轨迹缓存（不随 setData 清空 trackPolylines 而丢失）
    _summaryPolyline: [],
    _summaryMarkers: [],
    _summaryMapLat: 22.5431,
    _summaryMapLon: 113.9523,

    // 导航相关
    navState: 'idle',
    navInstruction: '',
    navCurDistance: 0,
    navRemainDistance: 0,
    navRoutePolylines: [],
    navDestMarker: [],
    showNavCard: false,
    showNavPicker: false,

    // 前置检查
    gpsReady: false,
  },

  onLoad: function() {
    var sysInfo = wx.getSystemInfoSync();
    var safeTop = sysInfo.safeArea ? sysInfo.safeArea.top : (sysInfo.statusBarHeight || 44);
    this.setData({ statusBarHeight: safeTop });
    logger.init();
    logger.log('PAGE', '首页加载');
    logger.log('PAGE', '基础库=' + sysInfo.SDKVersion + ' 平台=' + sysInfo.platform + ' 系统=' + sysInfo.system);
    var that = this;

    // 用 canvas 画蓝色圆点作为当前位置标记
    function _drawDot(ctx) {
      ctx.beginPath();
      ctx.arc(10, 10, 9, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(102, 204, 255, 0.3)';
      ctx.fill();
      ctx.beginPath();
      ctx.arc(10, 10, 5, 0, Math.PI * 2);
      ctx.fillStyle = '#66ccff';
      ctx.fill();
      ctx.beginPath();
      ctx.arc(10, 10, 5, 0, Math.PI * 2);
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }
    var query = wx.createSelectorQuery();
    query.select('#dotCanvas').fields({ node: true, size: true }).exec(function(res) {
      if (res[0] && res[0].node) {
        var canvas = res[0].node;
        canvas.width = 20;
        canvas.height = 20;
        _drawDot(canvas.getContext('2d'));
        wx.canvasToTempFilePath({
          canvas: canvas,
          success: function(r) { that._dotIconPath = r.tempFilePath; logger.log('PAGE', '蓝点图标就绪(DOM)'); },
        });
      } else {
        try {
          var off = wx.createOffscreenCanvas({ type: '2d', width: 20, height: 20 });
          _drawDot(off.getContext('2d'));
          that._dotIconPath = off.toTempFilePathSync();
          logger.log('PAGE', '蓝点图标就绪(离屏)');
        } catch (e) {
          logger.log('PAGE', '蓝点图标生成失败: ' + e.message);
        }
      }
    });

    wx.getLocation({
      type: 'gcj02',
      isHighAccuracy: true,
      success: function(res) {
        that.setData({ mapLat: res.latitude, mapLon: res.longitude, gpsReady: true });
        logger.log('PAGE', 'GPS 定位成功');
      },
      fail: function() {
        logger.log('PAGE', 'GPS 定位失败');
      },
    });

    wx.startLocationUpdate({
      success: function() {
        logger.log('PAGE', 'startLocationUpdate 成功，注册 onLocationChange');
        var _gpsLogIdx = 0;
        wx.offLocationChange();
        wx.onLocationChange(function(res) {
          _gpsLogIdx++;
          if (_gpsLogIdx % 10 === 0) {
            logger.log('PAGE', 'onLocationChange: lat=' + res.latitude + ' lon=' + res.longitude);
          }
          if (that.data.mapFollowing && !RideService.isActive()) {
            that.setData({ mapLat: res.latitude, mapLon: res.longitude });
          }
        });
      },
      fail: function(err) {
        logger.log('PAGE', 'startLocationUpdate 失败: ' + JSON.stringify(err));
        wx.showToast({ title: '定位服务不可用', icon: 'none', duration: 3000 });
      },
    });

    // 注册 EventBus 监听（★ P1 核心：页面不再设置 BLE onData 回调）
    this._bindEvents();
  },

  onUnload: function() {
    this._unbindEvents();
  },

  onShow: function() {
    // 从 StateService 同步全局状态到页面
    var syncData = StateService.syncToPageData();
    var gd = app.globalData;

    // 骑行状态补充
    if (gd.isRiding) {
      syncData.riding = true;
      syncData.status = gd.bleConnected ? '骑行中...' : '已断开';
      syncData.isOnline = gd.bleConnected;
      syncData.btnText = '结束骑行';
      syncData.btnClass = 'btn-end';
    }

    // 导航状态恢复
    if (NavService.isNavigating() || NavService.getState().state === 'paused') {
      var navState = NavService.getState();
      var instr = NavService.getCurrentInstruction();
      syncData.navState = navState.state;
      syncData.showNavCard = true;
      if (!gd.isRiding) {
        syncData.status = '导航中...';
        syncData.isOnline = true;
      }
      if (instr) {
        syncData.navInstruction = navState.state === 'paused' ? '报警中，导航暂停' : instr.instruction;
        syncData.navCurDistance = instr.distance;
      }
      syncData.navRemainDistance = navState.remainDistance;
    }

    // 报警弹窗恢复
    if (gd.alarmActive && !this.data.showAlarmPopup) {
      syncData.showAlarmPopup = true;
    }

    if (Object.keys(syncData).length > 0) {
      this.setData(syncData);
    }

    // P2: 骑行中恢复轨迹数据（从 RideService 获取）
    if (gd.isRiding) {
      var trackPts = RideService.getTrackPoints();
      var trackPoly = RideService.getTrackPolylines();
      var trackMarks = RideService.getTrackMarkers(this._dotIconPath);
      if (trackPts.length > 0 && this.data.trackPoints.length === 0) {
        this.setData({
          trackPoints: trackPts,
          trackPolylines: trackPoly,
          trackMarkers: trackMarks,
        });
      }
    }

    // 重新注册 NavService 回调（control 页 onShow 可能覆盖了本页的回调）
    NavService.onStateChange(this._onNavStateChange);

    this._syncTabBar();
  },

  // ==================== EventBus 绑定 ====================

  _bindEvents: function() {
    var that = this;
    var bus = app.eventBus;
    if (!bus) return;

    // 传感器数据更新
    this._onSensorUpdate = function(evt) {
      var f = evt.formatted;
      var r = evt.raw;
      var u = {};
      // 格式化显示字符串
      if (f.temp) u.temp = f.temp;
      if (f.humid) u.humid = f.humid;
      if (f.speed) u.speed = f.speed;
      if (f.lat) u.lat = f.lat;
      if (f.lon) u.lon = f.lon;
      if (f.alt) u.alt = f.alt;
      if (f.cog) u.cog = f.cog;
      if (f.lux != null) u.lux = f.lux;
      if (f.battery) u.battery = f.battery;
      if (f.heartRate != null) {
        u.heartRate = f.heartRate;
        u.heartClass = f.heartClass;
        u.spo2Class = f.spo2Class;
        u.heartIcon = f.heartIcon || '\u2665';
      }
      if (f.spo2 != null) u.spo2 = f.spo2;
      u.time = f.time;
      u.isOnline = true;

      // BLE 坐标更新地图中心
      if (r.lat != null && r.lon != null) {
        that._lastBleLat = r.lat;
        that._lastBleLon = r.lon;
        if (RideService.isActive() && that.data.mapFollowing) {
          u.mapLat = r.lat;
          u.mapLon = r.lon;
        }
      }

      // 骑行记录（★ P2: 轨迹数据由 RideService 管理）
      if (RideService.isActive() && r.lat != null && r.lon != null) {
        RideService.addRecord({
          temp: r.tmp, humid: r.hum, speed: r.spd, cog: r.cog,
          lat: r.lat, lon: r.lon, alt: r.alt,
          hr: r.hr != null ? r.hr : undefined,
          spo2: r.spo2 != null ? r.spo2 : undefined,
        });

        if (NavService.isNavigating()) {
          var userMarker = MapService.buildMarker([{latitude: r.lat, longitude: r.lon}], that._dotIconPath, r.cog);
          var navPoly = that.data._navPolylines || [];
          var navMarker = that.data._navMarkers || [];
          u.trackPolylines = navPoly;
          u.trackMarkers = navMarker.concat(userMarker);
        } else {
          // P2: 坐标变化时由 RideService 管理轨迹点
          var prevCount = RideService.getTrackPointCount();
          RideService.addTrackPoint(r.lat, r.lon);
          var newCount = RideService.getTrackPointCount();
          if (newCount > prevCount) {
            u.trackPoints = RideService.getTrackPoints();
            u.trackPolylines = RideService.getTrackPolylines();
            u.trackMarkers = RideService.getTrackMarkers(that._dotIconPath, r.cog);
          }
        }
      }

      that.setData(u);
    };

    // 报警触发
    this._onAlarmTriggered = function(evt) {
      that.setData({ alarm: evt.displayText });
      if (evt.shouldPopup) {
        that.setData({
          showAlarmPopup: true,
          alarmPopupClass: evt.popupClass,
          alarmPopupData: {
            icon: evt.icon,
            type: evt.type + ' 报警',
            level: 'Lv' + evt.level,
            lat: that.data.lat,
            lon: that.data.lon,
            time: that.data.time,
          },
        });
      }
      if (NavService.isNavigating()) NavService.pause();
      that._syncTabBar();
    };

    // 报警取消
    this._onAlarmCancelled = function() {
      that.setData({ alarm: '正常', alarmPopupClass: '', showAlarmPopup: false });
      if (NavService.getState().state === 'paused') NavService.resume();
      that._syncTabBar();
    };

    // 控制状态变更（index 页不需要直接处理，但保留监听用于状态同步）
    this._onCtrlChanged = function(state) {
      // index 页主要显示传感器数据，不显示控制面板
      // 但如果有需要可以在这里处理
    };

    // BLE 连接/断开
    this._onBleConnected = function() {
      // 根据骑行状态设置 status，避免未骑行时显示"骑行中..."
      if (RideService.isActive()) {
        that.setData({ bleConnected: true, bleStatus: '已连接', status: '骑行中...', isOnline: true, showBlePicker: false });
      } else {
        that.setData({ bleConnected: true, bleStatus: '已连接', status: '已连接', isOnline: true, showBlePicker: false });
      }
      that._syncTabBar();
    };

    this._onBleDisconnected = function() {
      // 断连时：重置状态 + 清除残留传感器数据
      var resetData = {
        bleConnected: false, bleStatus: '已断开',
        isOnline: false,
        temp: '--', humid: '--', speed: '--', cog: '--',
        lat: '--', lon: '--', alt: '--',
        lux: '--', battery: '--', time: '',
        heartRate: '--', spo2: '--', heartClass: '', spo2Class: '', heartIcon: '\u2665',
      };
      // 骑行中断连：状态显示"已断开"；非骑行断连：显示"未连接"
      resetData.status = RideService.isActive() ? '已断开' : '未连接';
      that.setData(resetData);
      that._syncTabBar();
    };

    // BLE 设备发现
    this._onDeviceFound = function(devices) {
      if (that.data.bleConnected) return;
      that.setData({ bleDevices: devices, showBlePicker: true });
    };

    // BLE 状态文字
    this._onBleStatus = function(msg) {
      that.setData({ bleStatus: msg });
    };

    // 导航状态变化
    this._onNavStateChange = function(navState) {
      if (app.eventBus) app.eventBus.emit('nav:stateChange', navState);

      var s = NavService.getState();
      var data = {
        navState: navState,
        showNavCard: navState === 'navigating' || navState === 'paused',
      };
      if (navState === 'navigating' || navState === 'paused') {
        var instr = NavService.getCurrentInstruction();
        if (instr) {
          data.navInstruction = navState === 'paused' ? '报警中，导航暂停' : instr.instruction;
          data.navCurDistance = instr.distance;
        }
        data.navRemainDistance = s.remainDistance;
        var navPoly = MapService.buildRoutePolyline(s.routePolyline);
        var navMarker = s.dest ? MapService.buildDestMarker(s.dest.lat, s.dest.lng, s.dest.name) : [];
        data.trackPolylines = navPoly;
        data.trackMarkers = navMarker;
        data._navPolylines = navPoly;
        data._navMarkers = navMarker;
      } else {
        // P2: 从 RideService 获取轨迹数据恢复
        var trackPoly = RideService.getTrackPolylines() || [];
        var trackMarks = RideService.getTrackMarkers(that._dotIconPath) || [];
        data.trackPolylines = trackPoly;
        data.trackMarkers = trackMarks;
        data._navPolylines = [];
        data._navMarkers = [];
        data.navInstruction = '';
      }
      that.setData(data);
      that._syncTabBar();
    };

    bus.on('state:sensorUpdate', this._onSensorUpdate);
    bus.on('state:alarmTriggered', this._onAlarmTriggered);
    bus.on('state:alarmCancelled', this._onAlarmCancelled);
    bus.on('state:ctrlChanged', this._onCtrlChanged);
    bus.on('ble:connected', this._onBleConnected);
    bus.on('ble:disconnected', this._onBleDisconnected);
    bus.on('ble:deviceFound', this._onDeviceFound);
    bus.on('ble:status', this._onBleStatus);
    NavService.onStateChange(this._onNavStateChange);
  },

  _unbindEvents: function() {
    var bus = app.eventBus;
    if (!bus) return;
    bus.off('state:sensorUpdate', this._onSensorUpdate);
    bus.off('state:alarmTriggered', this._onAlarmTriggered);
    bus.off('state:alarmCancelled', this._onAlarmCancelled);
    bus.off('state:ctrlChanged', this._onCtrlChanged);
    bus.off('ble:connected', this._onBleConnected);
    bus.off('ble:disconnected', this._onBleDisconnected);
    bus.off('ble:deviceFound', this._onDeviceFound);
    bus.off('ble:status', this._onBleStatus);
    NavService.onStateChange(null);
  },

  // ==================== BLE 连接 ====================

  onToggleBle: function() {
    if (this.data.bleConnected) {
      BleService.disconnect();
      this.setData({ bleConnected: false, bleStatus: '已断开' });
      return;
    }
    var that = this;
    that.setData({ bleStatus: '初始化...' });
    // ★ 使用 StateService 的全局回调（不再传入页面级回调）
    BleService.init(StateService.getBleCallbacks()).then(function() {
      that.setData({ bleStatus: '扫描中...' });
      BleService.scan();
    }).catch(function(err) {
      // 适配器可能已打开（断开重连场景），更新回调后直接扫描
      if (err.errMsg && (err.errMsg.indexOf('already') >= 0 || err.errMsg.indexOf('已经') >= 0)) {
        BleService.setCallbacks(StateService.getBleCallbacks());
        that.setData({ bleStatus: '扫描中...' });
        BleService.scan();
        logger.log('BLE', '适配器已打开，直接扫描');
      } else {
        that.setData({ bleStatus: 'BLE 不可用' });
        logger.log('BLE', '初始化失败: ' + err.errMsg);
      }
    });
  },

  onBleDevicePick: function(e) {
    var deviceId = e.currentTarget.dataset.deviceId;
    this.setData({ showBlePicker: false, bleStatus: '连接中...' });
    BleService.connectById(deviceId);
  },

  onBlePickerCancel: function() {
    BleService.stopScan();
    this.setData({ showBlePicker: false, bleDevices: [], bleStatus: '未连接' });
  },

  // ==================== 骑行 ====================

  onToggleRide: function() {
    if (!RideService.isActive()) {
      if (!BleService.isConnected()) {
        wx.showToast({ title: '请先连接蓝牙设备', icon: 'none', duration: 2000 });
        return;
      }
      if (!this.data.gpsReady) {
        var that = this;
        wx.showLoading({ title: '获取定位中...' });
        wx.getLocation({
          type: 'gcj02',
          isHighAccuracy: true,
          success: function(res) {
            wx.hideLoading();
            that.setData({ mapLat: res.latitude, mapLon: res.longitude, gpsReady: true });
            that.setData({ showNavPicker: true });
          },
          fail: function() {
            wx.hideLoading();
            wx.showModal({
              title: '定位失败',
              content: '未检测到GPS信号，请到开阔地带重试',
              showCancel: false,
              confirmText: '知道了',
            });
          },
        });
        return;
      }
      this.setData({ showNavPicker: true });
    } else {
      var that = this;
      wx.showModal({
        title: '结束骑行',
        content: '确定要结束本次骑行吗？',
        confirmText: '结束',
        cancelText: '继续骑行',
        success: function(res) {
          if (res.confirm) that._endRide();
        },
      });
    }
  },

  onBackPress: function() {
    if (!RideService.isActive()) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    var that = this;
    wx.showModal({
      title: '退出骑行',
      content: '确定要退出骑行吗？退出后数据将停止记录。',
      confirmText: '退出',
      cancelText: '继续骑行',
      success: function(res) {
        if (res.confirm) {
          if (NavService.isNavigating()) NavService.stopNavigation('cancelled');
          RideService.clear();
          wx.reLaunch({ url: '/pages/login/login' });
        }
      },
    });
  },

  onPickDestination: function() {
    var that = this;
    if (!BleService.isConnected()) {
      wx.showToast({ title: '请先连接蓝牙设备', icon: 'none', duration: 2000 });
      return;
    }
    that.setData({ showNavPicker: false });
    NavService.selectDestination().then(function(dest) {
      that._navDest = dest;
      that._beginNavOrRide();
    }).catch(function() {
      that._beginNavOrRide();
    });
  },

  onSkipNavigation: function() {
    if (!BleService.isConnected()) {
      wx.showToast({ title: '请先连接蓝牙设备', icon: 'none', duration: 2000 });
      return;
    }
    this.setData({ showNavPicker: false });
    this._navDest = null;
    this._beginNavOrRide();
  },

  _beginNavOrRide: function() {
    if (RideService.isActive()) {
      if (this._navDest) {
        var origin = null;
        if (this.data.bleConnected && this._lastBleLat && this._lastBleLon) {
          origin = { lat: this._lastBleLat, lng: this._lastBleLon };
        }
        NavService.startNavigation(this._navDest, origin);
        this._navDest = null;
      }
      this._syncTabBar();
    } else {
      this._startRide();
    }
  },

  onCancelNavigation: function() {
    var that = this;
    wx.showModal({
      title: '结束导航',
      content: '确定结束当前导航？',
      confirmText: '结束导航',
      cancelText: '继续',
      success: function(res) {
        if (res.confirm) {
          NavService.stopNavigation('cancelled');
        }
      },
    });
  },

  onRestartNav: function() {
    this.setData({ showNavPicker: true });
  },

  onCancelNavPicker: function() {
    this.setData({ showNavPicker: false });
  },

  onCancelAlarm: function() {
    this.setData({ showAlarmPopup: false, alarm: '正常' });
    if (BleService.isConnected()) {
      BleService.sendCtrl('alarm_cancel');
      logger.log('PAGE', '已发送取消报警指令');
    }
  },

  _startRide: function() {
    logger.log('PAGE', '=== 开始骑行 ===');
    RideService.start();
    if (app.eventBus) app.eventBus.emit('ride:start');

    this.setData({
      riding: true, status: '骑行中...', isOnline: true,
      btnText: '结束骑行', btnClass: 'btn-end',
      temp: '--', humid: '--', speed: '--', cog: '--',
      lat: '--', lon: '--', alt: '--',
      lux: '--', alarm: '正常', time: '',
      heartRate: '--', spo2: '--', heartClass: '', spo2Class: '', heartIcon: '\u2665',
      // P2: trackPoints 显示由 RideService 驱动，初始化为空
      trackPoints: [], trackPolylines: [], trackMarkers: [],
      mapFollowing: true, showSummary: false, showAlarmPopup: false,
    });

    this._rideStartTime = Date.now();
    this._savedTrackPolylines = [];
    this._savedTrackMarkers = [];

    if (this._navDest) {
      var origin = null;
      if (this.data.bleConnected && this._lastBleLat && this._lastBleLon) {
        origin = { lat: this._lastBleLat, lng: this._lastBleLon };
        logger.log('NAV', '使用板子坐标作为起点: ' + origin.lat + ', ' + origin.lng);
      }
      NavService.startNavigation(this._navDest, origin);
      this._navDest = null;
    }

    this._syncTabBar();
  },

  _endRide: function() {
    logger.log('PAGE', '=== 结束骑行 ===');

    var navSt = NavService.getState().state;
    if (navSt === 'planning' || navSt === 'navigating' || navSt === 'paused') {
      NavService.stopNavigation('cancelled');
    }

    var summary = RideService.end();

    // P2: 先获取轨迹数据（clear 会清空 _trackPoints）
    var pointData = RideService.getTrackPoints();
    var polylineData = RideService.getTrackPolylines();
    var firstPt = pointData.length > 0 ? pointData[0] : null;

    RideService.clear();

    if (app.eventBus) app.eventBus.emit('ride:end');

    logger.log('PAGE', '轨迹点数=' + pointData.length + ' polyline=' + JSON.stringify(polylineData).slice(0, 100));

    var data = {
      riding: false, status: '已结束', isOnline: false,
      btnText: '开始骑行', btnClass: 'btn-start',
      temp: '--', humid: '--', speed: '--', cog: '--',
      lat: '--', lon: '--', alt: '--',
      lux: '--', alarm: '--', time: '',
      heartRate: '--', spo2: '--', heartClass: '', spo2Class: '', heartIcon: '\u2665',
      trackPoints: [], trackPolylines: [], trackMarkers: [],
      navState: 'idle', showNavCard: false,
      navRoutePolylines: [], navDestMarker: [],
      navInstruction: '', navCurDistance: 0, navRemainDistance: 0,
      _navPolylines: [], _navMarkers: [],
      _savedTrackPolylines: [], _savedTrackMarkers: [],
    };

    if (summary) {
      data.showSummary = true;
      data.summary = summary;
      data._summaryPolyline = polylineData;
      var summaryMarkers = [];
      var lastPt = pointData.length > 0 ? pointData[pointData.length - 1] : null;
      // P2: pointData 已经来自 RideService.getTrackPoints()
      if (firstPt) {
        summaryMarkers.push({
          id: 0,
          latitude: firstPt.latitude,
          longitude: firstPt.longitude,
          width: 20, height: 20,
          callout: {
            content: '起点', color: '#ffffff', bgColor: '#66ccff',
            borderRadius: 8, padding: 6, fontSize: 12, display: 'ALWAYS',
          },
        });
      }
      if (lastPt && (!firstPt || lastPt.latitude !== firstPt.latitude || lastPt.longitude !== firstPt.longitude)) {
        summaryMarkers.push({
          id: 1,
          latitude: lastPt.latitude,
          longitude: lastPt.longitude,
          width: 20, height: 20,
          callout: {
            content: '终点', color: '#ffffff', bgColor: '#ff3d00',
            borderRadius: 8, padding: 6, fontSize: 12, display: 'ALWAYS',
          },
        });
      }
      data._summaryMarkers = summaryMarkers;
      data._summaryMapLat = firstPt ? firstPt.latitude : 22.5431;
      data._summaryMapLon = firstPt ? firstPt.longitude : 113.9523;
    }

    this.setData(data);

    if (summary && summary.hrTimeSeries && summary.hrTimeSeries.length > 0) {
      var that = this;
      wx.nextTick(function() { that._drawHrChart(); });
    }

    this._syncTabBar();
  },

  _syncTabBar: function() {
    var that = this;
    wx.nextTick(function() {
      var tabBar = that.getTabBar();
      if (!tabBar) return;
      if (tabBar.updateRiding) tabBar.updateRiding();
      if (tabBar.updateNav) tabBar.updateNav();
    });
  },

  _drawHrChart: function() {
    var that = this;
    var query = wx.createSelectorQuery();
    query.select('#hrChart')
      .fields({ node: true, size: true })
      .exec(function(res) {
        if (!res[0] || !res[0].node) return;
        var canvas = res[0].node;
        var ctx = canvas.getContext('2d');
        var dpr = wx.getSystemInfoSync().pixelRatio;
        canvas.width = res[0].width * dpr;
        canvas.height = res[0].height * dpr;
        ctx.scale(dpr, dpr);

        var series = that.data.summary.hrTimeSeries;
        if (!series || series.length === 0) return;

        var w = res[0].width;
        var h = res[0].height;
        var padL = 40, padR = 20, padT = 16, padB = 24;
        var cw = w - padL - padR;
        var ch = h - padT - padB;

        var hrs = series.map(function(p){return p.hr;});
        var hrMin = Math.min.apply(null, hrs);
        var hrMax = Math.max.apply(null, hrs);
        var yMin = Math.max(40, Math.floor(hrMin / 10) * 10);
        var yMax = Math.min(200, Math.ceil(hrMax / 10) * 10);
        if (yMax - yMin < 20) { yMin -= 10; yMax += 10; }
        var yRange = yMax - yMin;

        var maxTime = series[series.length - 1].time || 1;

        var y50 = padT + ch * (1 - (50 - yMin) / yRange);
        var y190 = padT + ch * (1 - (190 - yMin) / yRange);
        ctx.fillStyle = 'rgba(102, 204, 255, 0.06)';
        ctx.fillRect(padL, y190, cw, y50 - y190);

        ctx.strokeStyle = '#e2e8f0';
        ctx.lineWidth = 0.5;
        ctx.fillStyle = '#9aa8b5';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'right';
        for (var yi = 0; yi <= 4; yi++) {
          var yVal = yMin + yRange * yi / 4;
          var yPos = padT + ch * (1 - yi / 4);
          ctx.beginPath(); ctx.moveTo(padL, yPos); ctx.lineTo(padL + cw, yPos); ctx.stroke();
          ctx.fillText(yVal.toFixed(0), padL - 4, yPos + 3);
        }

        ctx.textAlign = 'center';
        for (var xi = 0; xi <= 4; xi++) {
          var xPos = padL + cw * xi / 4;
          ctx.beginPath(); ctx.moveTo(xPos, padT); ctx.lineTo(xPos, padT + ch); ctx.stroke();
          var tLabel = Math.round(maxTime * xi / 4);
          ctx.fillText(tLabel + 's', xPos, padT + ch + 14);
        }

        ctx.strokeStyle = '#66ccff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (var i = 0; i < series.length; i++) {
          var px = padL + cw * (series[i].time / maxTime);
          var py = padT + ch * (1 - (series[i].hr - yMin) / yRange);
          if (i === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.stroke();

        for (var j = 0; j < series.length; j++) {
          var dx = padL + cw * (series[j].time / maxTime);
          var dy = padT + ch * (1 - (series[j].hr - yMin) / yRange);
          var abnormal = series[j].hr < 50 || series[j].hr > 190;
          ctx.fillStyle = abnormal ? '#f6ad55' : '#66ccff';
          ctx.beginPath();
          ctx.arc(dx, dy, abnormal ? 3 : 2, 0, Math.PI * 2);
          ctx.fill();
        }
      });
  },

  onCloseSummary: function() {
    this.setData({
      showSummary: false,
      _summaryPolyline: [],
      _summaryMarkers: [],
      _summaryMapLat: 22.5431,
      _summaryMapLon: 113.9523,
    });
    this._syncTabBar();
  },

  onMapRegionChange: function(e) {
    if (e.causedBy === 'drag' || e.causedBy === 'scale') {
      if (this.data.mapFollowing) {
        this.setData({ mapFollowing: false });
      }
    }
  },

  onMapTap: function() {},
  onMapReset: function() {
    if (RideService.isActive()) {
      var pt = RideService.getLatestPoint();
      if (pt) {
        this.setData({ mapLat: pt.lat, mapLon: pt.lon, mapFollowing: true });
        return;
      }
    }
    var that = this;
    this.setData({ mapFollowing: true });
    wx.getLocation({
      type: 'gcj02',
      isHighAccuracy: true,
      success: function(res) {
        that.setData({ mapLat: res.latitude, mapLon: res.longitude });
      },
    });
  },

  onToggleMap: function() {
    if (this.data.mapExpanded) {
      this.setData({ mapExpanded: false, mapHeight: 360 });
    } else {
      var info = wx.getSystemInfoSync();
      this.setData({
        mapExpanded: true,
        mapHeight: Math.floor(info.windowHeight * 0.5 * (750 / info.windowWidth)),
      });
    }
  },
});
