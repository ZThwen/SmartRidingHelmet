/**
 * 首页 — 薄调度器
 */
var AlarmService = require('../../services/alarm-service');
var RideService = require('../../services/ride-service');
var MapService = require('../../services/map-service');
var BleService = require('../../services/ble-service');
var NavService = require('../../services/navigation-service');
var logger = require('../../utils/logger');
var CtrlService = require('../../services/ctrl-service');
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
        // DevTools 兜底：离屏 canvas
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
          // 未骑行时用手机 GPS 更新地图中心，骑行中用 BLE 坐标
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

    // 监听导航状态变化
    NavService.onStateChange(function(navState) {
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
        // 导航模式：地图只显示导航路线（不显示轨迹）
        data.trackPolylines = navPoly;
        data.trackMarkers = navMarker;
        data._navPolylines = navPoly;
        data._navMarkers = navMarker;
      } else {
        // 导航结束：恢复骑行轨迹
        var trackPoly = MapService.buildPolyline(that.data.trackPoints || []);
        var trackMarks = MapService.buildMarker(that.data.trackPoints || [], that._dotIconPath);
        data.trackPolylines = trackPoly;
        data.trackMarkers = trackMarks;
        data._navPolylines = [];
        data._navMarkers = [];
        data.navInstruction = '';
      }
      that.setData(data);
      // 通知自定义 tab bar 同步导航状态
      that._syncTabBar();
    });

    // eventBus 监听（报警跨页面同步）
    var bus = app.eventBus;
    if (bus) {
      that._onAlarmTriggered = function() {
        that.setData({ showAlarmPopup: true, alarmPopupClass: 'alarm-popup' });
      };
      that._onAlarmCancelled = function() {
        that.setData({ showAlarmPopup: false, alarm: '正常' });
      };
      bus.on('alarm:triggered', that._onAlarmTriggered);
      bus.on('alarm:cancelled', that._onAlarmCancelled);
    }
  },

  onUnload: function() {
    var bus = app.eventBus;
    if (bus) {
      bus.off('alarm:triggered', this._onAlarmTriggered);
      bus.off('alarm:cancelled', this._onAlarmCancelled);
    }
  },

  onShow: function() {
    // 从 globalData 同步报警状态（从控制页返回时）
    if (app.globalData.alarmActive && !this.data.showAlarmPopup) {
      this.setData({ showAlarmPopup: true });
    }
    // 同步 BLE 连接状态（以底层真实状态为准）
    var realConnected = BleService.isConnected();
    var syncData = {};
    if (this.data.bleConnected !== realConnected) {
      syncData.bleConnected = realConnected;
      syncData.bleStatus = realConnected ? '已连接' : '未连接';
    }
    // 同步骑行状态（wx.redirectTo 重建页面后恢复）
    var realRiding = !!app.globalData.isRiding;
    if (realRiding) {
      syncData.riding = true;
      syncData.status = realConnected ? '骑行中...' : '已断开';
      syncData.isOnline = realConnected;
      syncData.btnText = '结束骑行';
      syncData.btnClass = 'btn-end';
    }
    // 同步导航状态（从控制页返回时恢复导航 UI）
    if (NavService.isNavigating() || NavService.getState().state === 'paused') {
      var navState = NavService.getState();
      var instr = NavService.getCurrentInstruction();
      syncData.navState = navState.state;
      syncData.showNavCard = true;
      if (!realRiding) {
        syncData.status = '导航中...';
        syncData.isOnline = true;
      }
      if (instr) {
        syncData.navInstruction = navState.state === 'paused' ? '报警中，导航暂停' : instr.instruction;
        syncData.navCurDistance = instr.distance;
      }
      syncData.navRemainDistance = navState.remainDistance;
    }
    // 恢复缓存的传感器数据（页面重建后等待 BLE 推送前显示）
    if (realConnected) {
      var cached = app.globalData.latestSensorData;
      if (cached) {
        if (cached.temp && syncData.temp === undefined) syncData.temp = cached.temp;
        if (cached.humid && syncData.humid === undefined) syncData.humid = cached.humid;
        if (cached.speed && syncData.speed === undefined) syncData.speed = cached.speed;
        if (cached.lat && syncData.lat === undefined) syncData.lat = cached.lat;
        if (cached.lon && syncData.lon === undefined) syncData.lon = cached.lon;
        if (cached.alt && syncData.alt === undefined) syncData.alt = cached.alt;
        if (cached.cog && syncData.cog === undefined) syncData.cog = cached.cog;
        if (cached.lux != null && syncData.lux === undefined) syncData.lux = cached.lux;
        if (cached.battery && syncData.battery === undefined) syncData.battery = cached.battery;
        if (cached.time && syncData.time === undefined) syncData.time = cached.time;
      }
    }
    if (Object.keys(syncData).length > 0) {
      this.setData(syncData);
    }
    // 重新注册 BLE 回调（wx.redirectTo 重建页面后 onData 指向旧页面）
    if (realConnected && !this._bleCallbacksRegistered) {
      this._restoreBleCallbacks();
    }
    // 通知自定义 tab bar 同步状态
    this._syncTabBar();
  },

  _restoreBleCallbacks: function() {
    var that = this;
    logger.log('PAGE', '重新注册 BLE 回调');
    BleService.setCallbacks({
      onConnected: function() {
        that.setData({ bleConnected: true, bleStatus: '已连接', status: '骑行中...', isOnline: true });
        app.globalData.bleConnected = true;
        app.globalData.bleStatus = '已连接';
        if (app.eventBus) app.eventBus.emit('ble:connected');
      },
      onDisconnected: function() {
        that.setData({ bleConnected: false, bleStatus: '已断开' });
        app.globalData.bleConnected = false;
        app.globalData.bleStatus = '已断开';
        CtrlService.reset();
        if (app.eventBus) app.eventBus.emit('ble:disconnected');
      },
      onData: function(data) {
        if (data.t === 0 && data.d) {
          var d = data.d;
          var u = {};
          if (d.tmp != null) u.temp = d.tmp.toFixed(1) + '°C';
          if (d.hum != null) u.humid = d.hum.toFixed(1) + '%';
          if (d.spd != null) u.speed = d.spd.toFixed(1) + ' km/h';
          if (d.lat != null) u.lat = d.lat.toFixed(4);
          if (d.lon != null) u.lon = d.lon.toFixed(4);
          if (d.alt != null) u.alt = d.alt.toFixed(1) + 'm';
          if (d.cog != null) u.cog = d.cog.toFixed(0) + '°';
          if (d.lux != null) u.lux = d.lux;
          if (d.bat != null) u.battery = d.bat + '档';
          u.time = new Date().toLocaleTimeString();
          u.isOnline = true;
          app.globalData.latestSensorData = {
            temp: u.temp, humid: u.humid, speed: u.speed,
            lat: u.lat, lon: u.lon, alt: u.alt, cog: u.cog,
            lux: u.lux, battery: u.battery, time: u.time,
          };
          if (d.lat != null && d.lon != null) {
            that._lastBleLat = d.lat;
            that._lastBleLon = d.lon;
            if (RideService.isActive() && that.data.mapFollowing) {
              u.mapLat = d.lat;
              u.mapLon = d.lon;
            }
          }
          if (RideService.isActive() && d.lat != null && d.lon != null) {
            RideService.addRecord({
              temp: d.tmp, humid: d.hum, speed: d.spd, cog: d.cog,
              lat: d.lat, lon: d.lon, alt: d.alt,
            });
            var lastPt = that.data.trackPoints.length > 0 ? that.data.trackPoints[that.data.trackPoints.length - 1] : null;
            var posChanged = !lastPt || lastPt.latitude !== d.lat || lastPt.longitude !== d.lon;
            if (NavService.isNavigating()) {
              var userMarker = MapService.buildMarker([{latitude: d.lat, longitude: d.lon}], that._dotIconPath, d.cog);
              var navPoly = that.data._navPolylines || [];
              var navMarker = that.data._navMarkers || [];
              u.trackPolylines = navPoly;
              u.trackMarkers = navMarker.concat(userMarker);
            } else {
              var points = posChanged ? MapService.pushPoint(that.data.trackPoints, d.lat, d.lon) : that.data.trackPoints;
              if (posChanged) {
                u.trackPoints = points;
                u.trackPolylines = MapService.buildPolyline(points);
                u.trackMarkers = MapService.buildMarker(points, that._dotIconPath, d.cog);
              }
            }
          }
          that.setData(u);
        }
      },
      onStatus: function(msg) {
        that.setData({ bleStatus: msg });
      },
      onDeviceFound: function(devices) {
        that.setData({ bleDevices: devices, showBlePicker: true });
      },
    });
    this._bleCallbacksRegistered = true;
  },

  onToggleRide: function() {
    if (!RideService.isActive()) {
      // 前置检查：BLE 必须已连接
      if (!BleService.isConnected()) {
        wx.showToast({ title: '请先连接蓝牙设备', icon: 'none', duration: 2000 });
        return;
      }
      // 前置检查：GPS 必须可用
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
      // 显示导航选择弹窗
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
    // 选目的地前再次确认 BLE 连接
    if (!BleService.isConnected()) {
      wx.showToast({ title: '请先连接蓝牙设备', icon: 'none', duration: 2000 });
      return;
    }
    that.setData({ showNavPicker: false });
    NavService.selectDestination().then(function(dest) {
      that._navDest = dest;
      that._beginNavOrRide();
    }).catch(function() {
      // 用户取消选择，直接开始骑行
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

  /**
   * 开始导航或骑行（根据是否已在骑行中分流）
   * - 未骑行：调用 _startRide() 开始骑行 + 导航
   * - 已骑行：直接在当前骑行中启动导航
   */
  _beginNavOrRide: function() {
    if (RideService.isActive()) {
      // 已在骑行中，直接启动导航
      if (this._navDest) {
        var origin = null;
        if (this.data.bleConnected && this._lastBleLat && this._lastBleLon) {
          origin = { lat: this._lastBleLat, lng: this._lastBleLon };
        }
        NavService.startNavigation(this._navDest, origin);
        this._navDest = null;
      }
      // 通知 tab bar 同步导航状态
      if (this.getTabBar() && this.getTabBar().updateNav) {
        this.getTabBar().updateNav();
      }
    } else {
      this._startRide();
    }
  },

  onCancelNavigation: function() {
    var that = this;
    wx.showModal({
      title: '取消导航',
      content: '确定取消当前导航？',
      confirmText: '取消导航',
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
    // 关闭报警弹窗
    this.setData({ showAlarmPopup: false, alarm: '正常' });
    // 通过 BLE 通知板子取消报警
    if (BleService.isConnected()) {
      BleService.sendCtrl('alarm_cancel');
      logger.log('PAGE', '已发送取消报警指令');
    }
  },

  _startRide: function() {
    logger.log('PAGE', '=== 开始骑行 ===');
    RideService.start();

    this.setData({
      riding: true, status: '骑行中...', isOnline: true,
      btnText: '结束骑行', btnClass: 'btn-end',
      temp: '--', humid: '--', speed: '--', cog: '--',
      lat: '--', lon: '--', alt: '--',
      lux: '--', alarm: '正常', time: '',
      trackPoints: [], trackPolylines: [], trackMarkers: [],
      mapFollowing: true, showSummary: false, showAlarmPopup: false,
    });

    this._rideStartTime = Date.now();

    // 保存原始轨迹数据（导航结束时恢复）
    this._savedTrackPolylines = [];
    this._savedTrackMarkers = [];

    // 如果选择了目的地，开始导航（用缓存的 BLE 坐标）
    if (this._navDest) {
      var origin = null;
      if (this.data.bleConnected && this._lastBleLat && this._lastBleLon) {
        origin = { lat: this._lastBleLat, lng: this._lastBleLon };
        logger.log('NAV', '使用板子坐标作为起点: ' + origin.lat + ', ' + origin.lng);
      }
      NavService.startNavigation(this._navDest, origin);
      this._navDest = null;
    }

    // 通知自定义 tab bar 同步骑行+导航状态
    this._syncTabBar();
  },

  _endRide: function() {
    logger.log('PAGE', '=== 结束骑行 ===');

    // 结束导航（覆盖所有活跃状态：planning/navigating/paused）
    var navSt = NavService.getState().state;
    if (navSt === 'planning' || navSt === 'navigating' || navSt === 'paused') {
      NavService.stopNavigation('cancelled');
    }

    var summary = RideService.end();
    RideService.clear();

    // 缓存轨迹数据（拿到本地变量，再一次性 setData）
    var polylineData = this.data.trackPolylines;
    var markerData = this.data.trackMarkers;
    var pointData = this.data.trackPoints;
    var firstPt = pointData.length > 0 ? pointData[0] : null;

    logger.log('PAGE', '轨迹点数=' + pointData.length + ' polyline=' + JSON.stringify(polylineData).slice(0, 100));

    var data = {
      riding: false, status: '已结束', isOnline: false,
      btnText: '开始骑行', btnClass: 'btn-start',
      temp: '--', humid: '--', speed: '--', cog: '--',
      lat: '--', lon: '--', alt: '--',
      lux: '--', alarm: '--', time: '',
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
      // 构建起点和终点标记
      var summaryMarkers = [];
      var lastPt = pointData.length > 0 ? pointData[pointData.length - 1] : null;
      if (firstPt) {
        summaryMarkers.push({
          id: 0,
          latitude: firstPt.latitude,
          longitude: firstPt.longitude,
          width: 20,
          height: 20,
          callout: {
            content: '起点',
            color: '#ffffff',
            bgColor: '#66ccff',
            borderRadius: 8,
            padding: 6,
            fontSize: 12,
            display: 'ALWAYS',
          },
        });
      }
      if (lastPt && (!firstPt || lastPt.latitude !== firstPt.latitude || lastPt.longitude !== firstPt.longitude)) {
        summaryMarkers.push({
          id: 1,
          latitude: lastPt.latitude,
          longitude: lastPt.longitude,
          width: 20,
          height: 20,
          callout: {
            content: '终点',
            color: '#ffffff',
            bgColor: '#ff3d00',
            borderRadius: 8,
            padding: 6,
            fontSize: 12,
            display: 'ALWAYS',
          },
        });
      }
      data._summaryMarkers = summaryMarkers;
      data._summaryMapLat = firstPt ? firstPt.latitude : 22.5431;
      data._summaryMapLon = firstPt ? firstPt.longitude : 113.9523;
    }

    this.setData(data);

    // 通知自定义 tab bar 同步骑行+导航状态
    this._syncTabBar();
  },

  _syncTabBar: function() {
    var tabBar = this.getTabBar();
    if (!tabBar) return;
    if (tabBar.updateRiding) tabBar.updateRiding();
    if (tabBar.updateNav) tabBar.updateNav();
  },

  onCloseSummary: function() {
    this.setData({
      showSummary: false,
      _summaryPolyline: [],
      _summaryMarkers: [],
      _summaryMapLat: 22.5431,
      _summaryMapLon: 113.9523,
    });
  },

  onToggleBle: function() {
    if (this.data.bleConnected) {
      BleService.disconnect();
      this._bleCallbacksRegistered = false;
      this.setData({ bleConnected: false, bleStatus: '已断开' });
      return;
    }
    var that = this;
    that.setData({ bleStatus: '初始化...' });
    BleService.init({
      onConnected: function() {
        that.setData({ bleConnected: true, bleStatus: '已连接', status: '骑行中...', isOnline: true });
        app.globalData.bleConnected = true;
        app.globalData.bleStatus = '已连接';
        if (app.eventBus) app.eventBus.emit('ble:connected');
        logger.log('BLE', '连接成功');
      },
      onDisconnected: function() {
        that.setData({ bleConnected: false, bleStatus: '已断开' });
        app.globalData.bleConnected = false;
        app.globalData.bleStatus = '已断开';
        CtrlService.reset();
        if (app.eventBus) app.eventBus.emit('ble:disconnected');
        logger.log('BLE', '连接断开');
      },
      onData: function(data) {
        logger.log('BLE', '收到: ' + JSON.stringify(data));
        if (data.t === 0 && data.d) {
          var d = data.d;
          var u = {};
          if (d.tmp != null) u.temp = d.tmp.toFixed(1) + '°C';
          if (d.hum != null) u.humid = d.hum.toFixed(1) + '%';
          if (d.spd != null) u.speed = d.spd.toFixed(1) + ' km/h';
          if (d.lat != null) u.lat = d.lat.toFixed(4);
          if (d.lon != null) u.lon = d.lon.toFixed(4);
          if (d.alt != null) u.alt = d.alt.toFixed(1) + 'm';
          if (d.cog != null) u.cog = d.cog.toFixed(0) + '°';
          if (d.lux != null) u.lux = d.lux;
          if (d.bat != null) u.battery = d.bat + '档';
          u.time = new Date().toLocaleTimeString();
          u.isOnline = true;

          // 缓存最新 BLE 坐标（无论是否骑行）
          if (d.lat != null && d.lon != null) {
            that._lastBleLat = d.lat;
            that._lastBleLon = d.lon;
            // 骑行中用 BLE 坐标更新地图中心（替代手机 GPS）
            if (RideService.isActive() && that.data.mapFollowing) {
              u.mapLat = d.lat;
              u.mapLon = d.lon;
            }
          }

          // 骑行记录（始终记录轨迹数据，用于最终总结）
          if (RideService.isActive() && d.lat != null && d.lon != null) {
            RideService.addRecord({
              temp: d.tmp, humid: d.hum, speed: d.spd, cog: d.cog,
              lat: d.lat, lon: d.lon, alt: d.alt,
            });

            // 只在坐标变化时更新地图（避免闪烁）
            var lastPt = that.data.trackPoints.length > 0 ? that.data.trackPoints[that.data.trackPoints.length - 1] : null;
            var posChanged = !lastPt || lastPt.latitude !== d.lat || lastPt.longitude !== d.lon;

            if (NavService.isNavigating()) {
              // 导航模式：每次 BLE 数据都更新（保持 marker 持久显示）
              var userMarker = MapService.buildMarker([{latitude: d.lat, longitude: d.lon}], that._dotIconPath, d.cog);
              var navPoly = that.data._navPolylines || [];
              var navMarker = that.data._navMarkers || [];
              u.trackPolylines = navPoly;
              u.trackMarkers = navMarker.concat(userMarker);
            } else {
              // 直接骑行：显示轨迹 + 用户位置蓝点
              var points = posChanged ? MapService.pushPoint(that.data.trackPoints, d.lat, d.lon) : that.data.trackPoints;
              if (posChanged) {
                u.trackPoints = points;
                u.trackPolylines = MapService.buildPolyline(points);
                u.trackMarkers = MapService.buildMarker(points, that._dotIconPath, d.cog);
              }
            }
          }

          // 缓存最新传感器数据到全局（页面切换恢复用）
          app.globalData.latestSensorData = {
            temp: u.temp, humid: u.humid, speed: u.speed,
            lat: u.lat, lon: u.lon, alt: u.alt, cog: u.cog,
            lux: u.lux, battery: u.battery, time: u.time,
          };

          // 合并所有数据为一次 setData
          that.setData(u);
        } else if (data.t === 5) {
          // 支持紧凑格式 {t:5, a:1, l:2} 和旧格式 {t:5, d:{type:'collision', lvl:2}}
          var typeCode = data.a || (data.d && data.d.type === 'collision' ? 1 : 2);
          var alarmLevel = data.l || (data.d && data.d.lvl) || 1;
          var typeName = typeCode === 1 ? '碰撞' : 'SOS';
          var alarmResult = AlarmService.analyze(typeCode, alarmLevel);
          that.setData({ alarm: alarmResult.displayText });
          if (alarmResult.shouldPopup) {
            that.setData({
              showAlarmPopup: true,
              alarmPopupClass: alarmResult.popupClass,
              alarmPopupData: {
                icon: alarmResult.icon,
                type: typeName + ' 报警',
                level: 'Lv' + alarmLevel,
                lat: that.data.lat,
                lon: that.data.lon,
                time: that.data.time,
              },
            });
          }
          // ★ 同步全局报警状态（双端同步）
          app.globalData.alarmActive = true;
          var bus = app.eventBus;
          if (bus) {
            bus.emit('alarm:triggered', {
              type: typeName,
              level: alarmLevel,
              time: new Date().toLocaleTimeString(),
            });
          }
          // 导航暂停
          if (NavService.isNavigating()) NavService.pause();
        } else if (data.t === 6) {
          that.setData({ alarm: '正常', alarmPopupClass: '' });
          if (that.data.showAlarmPopup) that.setData({ showAlarmPopup: false });
          // ★ 同步全局报警状态（双端同步）
          app.globalData.alarmActive = false;
          var bus = app.eventBus;
          if (bus) {
            bus.emit('alarm:cancelled');
          }
          // 导航恢复
          if (NavService.getState().state === 'paused') NavService.resume();
        }
        else if (data.t === 7 || data.t === 8 || data.t === 9) {
          // 控制状态回推（t=7灯光/t=8音量/t=9电源）→ 更新全局状态 + 通知控制页
          var state = CtrlService.parseCtrlState(data);
          if (state) {
            app.globalData.ctrlState = state;
            if (app.eventBus) app.eventBus.emit('ctrl:stateChanged', state);
          }
        }
      },
      onStatus: function(msg) {
        that.setData({ bleStatus: msg });
      },
      onDeviceFound: function(devices) {
        that.setData({ bleDevices: devices, showBlePicker: true });
      },
    }).then(function() {
      that._bleCallbacksRegistered = true;
      that.setData({ bleStatus: '扫描中...' });
      BleService.scan();
    }).catch(function(err) {
      that.setData({ bleStatus: 'BLE 不可用' });
      logger.log('BLE', '初始化失败: ' + err.errMsg);
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

  _onData: function(items, meta) {
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
