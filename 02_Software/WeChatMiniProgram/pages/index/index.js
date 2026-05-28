/**
 * 首页 — 薄调度器
 */
var DataService = require('../../services/data-service');
var AlarmService = require('../../services/alarm-service');
var RideService = require('../../services/ride-service');
var MapService = require('../../services/map-service');
var BleService = require('../../services/ble-service');
var logger = require('../../utils/logger');

Page({
  data: {
    status: '未开始',
    isOnline: false,
    bleStatus: '未连接',
    bleConnected: false,
    bleDevices: [],
    showBlePicker: false,
    temp: '--', humid: '--', speed: '--',
    lat: '--', lon: '--', alt: '--',
    signal: '--', alarm: '正常', time: '',
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
  },

  onLoad: function() {
    logger.init();
    logger.log('PAGE', '首页加载');
    var that = this;

    wx.getLocation({
      type: 'gcj02',
      isHighAccuracy: true,
      success: function(res) {
        that.setData({ mapLat: res.latitude, mapLon: res.longitude });
      },
    });

    wx.startLocationUpdate({
      success: function() {
        wx.onLocationChange(function(res) {
          if (!RideService.isActive() && that.data.mapFollowing) {
            that.setData({ mapLat: res.latitude, mapLon: res.longitude });
          }
        });
      },
    });
  },

  onUnload: function() {
    DataService.stopPoll();
    wx.stopLocationUpdate({ success: function(){}, fail: function(){} });
  },

  onToggleRide: function() {
    if (!RideService.isActive()) {
      this._startRide();
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
          RideService.clear();
          DataService.stopPoll();
          wx.reLaunch({ url: '/pages/login/login' });
        }
      },
    });
  },

  _startRide: function() {
    logger.log('PAGE', '=== 开始骑行 ===');
    RideService.start();
    var that = this;

    this.setData({
      riding: true, status: '骑行中...', isOnline: true,
      btnText: '结束骑行', btnClass: 'btn-end',
      temp: '--', humid: '--', speed: '--',
      lat: '--', lon: '--', alt: '--',
      signal: '--', alarm: '正常', time: '',
      trackPoints: [], trackPolylines: [], trackMarkers: [],
      mapFollowing: true, showSummary: false, showAlarmPopup: false,
    });

    this._rideStartTime = Date.now();
    DataService.startPoll(
      function(items, meta) { that._onData(items, meta); },
      function(status) {
        var isOnline = status.indexOf('在线') >= 0 || status === '骑行中...' || status === '连接中...';
        that.setData({ status: status, isOnline: isOnline });
      },
    );
  },

  _endRide: function() {
    logger.log('PAGE', '=== 结束骑行 ===');
    DataService.stopPoll();

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
      temp: '--', humid: '--', speed: '--',
      lat: '--', lon: '--', alt: '--',
      signal: '--', alarm: '--', time: '',
      trackPoints: [], trackPolylines: [], trackMarkers: [],
    };

    if (summary) {
      data.showSummary = true;
      data.summary = summary;
      data._summaryPolyline = polylineData;
      data._summaryMarkers = markerData;
      data._summaryMapLat = firstPt ? firstPt.latitude : 22.5431;
      data._summaryMapLon = firstPt ? firstPt.longitude : 113.9523;
    }

    this.setData(data);
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
      this.setData({ bleConnected: false, bleStatus: '已断开' });
      return;
    }
    var that = this;
    that.setData({ bleStatus: '初始化...' });
    BleService.init({
      onConnected: function() {
        that.setData({ bleConnected: true, bleStatus: '已连接', status: '骑行中...', isOnline: true });
        logger.log('BLE', '连接成功');
      },
      onDisconnected: function() {
        that.setData({ bleConnected: false, bleStatus: '已断开' });
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
          u.time = new Date().toLocaleTimeString();
          that.setData(u);
        } else if (data.t === 5 && data.d) {
          var alarmResult = AlarmService.analyze(data.d.type === 'collision' ? 1 : 2, data.d.lvl || 1);
          that.setData({ alarm: alarmResult.displayText });
          if (alarmResult.shouldPopup) {
            that.setData({
              showAlarmPopup: true,
              alarmPopupClass: alarmResult.popupClass,
              alarmPopupData: {
                icon: alarmResult.icon,
                type: (data.d.type || '') + ' 报警',
                level: 'Lv' + (data.d.lvl || ''),
                lat: that.data.lat,
                lon: that.data.lon,
                time: that.data.time,
              },
            });
          }
        } else if (data.t === 6) {
          that.setData({ alarm: '正常' });
          if (that.data.showAlarmPopup) that.setData({ showAlarmPopup: false });
        }
      },
      onStatus: function(msg) {
        that.setData({ bleStatus: msg });
      },
      onDeviceFound: function(devices) {
        that.setData({ bleDevices: devices, showBlePicker: true });
      },
    }).then(function() {
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
    if (meta && meta.stale) {
      this.setData({
        temp: '--', humid: '--', speed: '--',
        lat: '--', lon: '--', alt: '--',
        signal: '--', alarm: '离线', time: '',
        isOnline: false,
      });
      if (this.data.showAlarmPopup) { this.setData({ showAlarmPopup: false }); }
      return;
    }

    if (this._rideStartTime && meta && meta.updateTime && meta.updateTime < this._rideStartTime) {
      return;
    }

    if (!items) return;
    var isAlarm = false;
    for (var i = 0; i < items.length; i++) {
      if (items[i].abId === 6 && Number(items[i].resourceValce) !== 0) {
        isAlarm = true;
        break;
      }
    }

    var result = DataService.parseItems(items, isAlarm);
    var u = result.u;
    var raw = result.raw;

    var alarmResult = AlarmService.analyze(raw.alarmType, raw.alarmLevel);
    u.alarm = alarmResult.displayText;

    if (alarmResult.shouldPopup) {
      this.setData({
        showAlarmPopup: true,
        alarmPopupClass: alarmResult.popupClass,
        alarmPopupData: {
          icon: alarmResult.icon,
          type: (raw.alarmType || '') + ' 报警',
          level: 'Lv' + (raw.alarmLevel || ''),
          lat: u.lat,
          lon: u.lon,
          time: u.time,
        },
      });
    } else if (this.data.showAlarmPopup) {
      this.setData({ showAlarmPopup: false });
    }

    this.setData(u);

    if (RideService.isActive()) {
      RideService.addRecord(raw);
      if (raw.lat != null && raw.lon != null) {
        var points = MapService.pushPoint(this.data.trackPoints, raw.lat, raw.lon);
        this.setData({
          trackPoints: points,
          trackPolylines: MapService.buildPolyline(points),
          trackMarkers: MapService.buildMarker(points, '头盔'),
        });
        if (this.data.mapFollowing) {
          this.setData({ mapLat: raw.lat, mapLon: raw.lon });
        }
      }
    }
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
