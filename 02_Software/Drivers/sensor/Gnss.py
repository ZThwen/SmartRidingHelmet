"""
brief GNSS定位驱动 (EC200U内置)
note 严格遵循四元组架构规范
     GNSS区别于普通I2C传感器：
     - 需要 start() 启动搜星，stop() 停止定位
     - get_location() 在未定位时返回 None
     - 需要独立管理定位状态（未启动/搜星中/已定位/信号丢失）
"""
import time
import _thread

from quectel import GNSS
from Drivers.network.thread_queue import ThreadSafeQueue

from core.Base_Module import BaseModule
from core.config import (EVENT_GNSS_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE, EVENT_POWER_STATE_CHANGE,
                    EVENT_GPS_LOST, GNSS_SAMPLE_MS, GNSS_SUSPENDED_MS, GNSS_EMERGENCY_MS,
                    POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED, POWER_STATE_EMERGENCY)


# 定位状态常量
GNSS_STATE_IDLE     = "idle"      # 未启动
GNSS_STATE_STARTING = "starting"  # 启动中
GNSS_STATE_SEARCH   = "searching" # 搜星中
GNSS_STATE_FIXED    = "fixed"     # 已定位
GNSS_STATE_LOST     = "lost"      # 信号丢失


class GNSSDriver(BaseModule):
    def __init__(self, event_bus=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "gnss"

        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            "sample_ms": GNSS_SAMPLE_MS,          # 采样间隔 2000ms
            "max_retry": 3,                        # 连续错误重试次数
            "lost_count": 5,                       # 连续无定位次数阈值（判为丢失）
            "thread_stack_size": 4096,             # 后台线程栈大小
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,         # 硬件初始化完成标志
            "is_busy": False,         # 操作中标志
            "last_tick": 0,           # 上次采样时间戳
            "err_count": 0,           # 连续错误计数
            "power_state": POWER_STATE_ACTIVE,  # 功耗状态
            "gnss_state": GNSS_STATE_IDLE,      # 定位状态
            "no_fix_count": 0,        # 连续无定位次数
            "gps_lost_reported": False,  # 是否已上报丢失（防重复上报）
            "thread_running": False,     # 后台线程运行标志
            "last_publish": 0,           # 上次发布事件时间戳
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "latitude": 0.0,          # 纬度
            "longitude": 0.0,         # 经度
            "altitude": 0.0,          # 海拔 (m)
            "speed_kmh": 0.0,         # 速度 (km/h)
            "cog": 0.0,              # 对地航向 (度, 0-360, 北为0)
            "signal_quality": "none", # 信号质量: good/fair/poor/none
            "valid": False,           # 数据有效性标志
        }

        self.gnss = None              # GNSS 实例句柄
        self._data_queue = ThreadSafeQueue(max_size=5)  # 线程安全队列

    def init(self):
        """初始化：创建实例 + 启动定位 + 启动后台线程 + 订阅事件"""
        try:
            # 1. 创建 GNSS 实例
            self.gnss = GNSS()

            # 2. 启动定位
            if not self.gnss.start():
                raise RuntimeError("GNSS 启动失败")

            self.ctx["gnss_state"] = GNSS_STATE_SEARCH

            # 3. 启动后台线程（阻塞的 get_location() 在线程中执行）
            self.ctx["thread_running"] = True
            old_stack = _thread.stack_size(self.cfg["thread_stack_size"])
            _thread.start_new_thread(self._gnss_thread, ())
            _thread.stack_size(old_stack)

            # 4. 订阅事件
            if self.event_bus:
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_config_update)

            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成 | 采样间隔:{self.cfg['sample_ms']}ms | 线程已启动")

        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        """周期调度（非阻塞）：从队列读取最新定位结果并发布事件"""
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return

        self.ctx["is_busy"] = True
        try:
            # 非阻塞读取队列中的所有数据，只保留最新一条
            latest = None
            while True:
                loc = self._data_queue.get(timeout_ms=0)
                if loc is None:
                    break
                latest = loc

            if latest is not None:
                # 有定位数据
                self._update_position(latest)
            else:
                # 无定位数据（队列空，说明后台线程还未获取到 fix）
                self._data["valid"] = False
                self.ctx["no_fix_count"] += 1

                # 状态降级
                if self.ctx["gnss_state"] == GNSS_STATE_FIXED:
                    self.ctx["gnss_state"] = GNSS_STATE_SEARCH

                # 连续无定位超限 → 判为信号丢失
                if (self.ctx["no_fix_count"] >= self.cfg["lost_count"]
                        and not self.ctx["gps_lost_reported"]
                        and self.event_bus):
                    self.ctx["gnss_state"] = GNSS_STATE_LOST
                    self.ctx["gps_lost_reported"] = True
                    self.event_bus.publish(EVENT_GPS_LOST, {
                        "source": self.name,
                        "timestamp": time.ticks_ms()
                    })
                    print(f"[{self.name}] ⚠ GPS 信号丢失")

            # 定时发布事件（2s 间隔，让订阅者知道状态）
            if time.ticks_diff(now, self.ctx["last_publish"]) >= 2000:
                self.ctx["last_publish"] = now
                if self.event_bus:
                    self.event_bus.publish(EVENT_GNSS_READY, self.get_data())

        except Exception as e:
            self.ctx["err_count"] += 1
            print(f"[{self.name}] 读取异常 ({self.ctx['err_count']}): {e}")
            if self.ctx["err_count"] > self.cfg["max_retry"] and self.event_bus:
                self.event_bus.publish(EVENT_SENSOR_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False
            self.ctx["last_tick"] = now

    # ==================== 后台线程 ====================
    def _gnss_thread(self):
        """后台 GNSS 轮询线程：只做 get_location()，不阻塞主循环"""
        while self.ctx["thread_running"]:
            try:
                # 根据电源模式决定等待时间
                sleep_ms = self.cfg["sample_ms"]
                time.sleep_ms(sleep_ms)

                # 阻塞调用（在后台线程，不影响主循环）
                loc = self.gnss.get_location()

                # 只有获取到有效定位时才入队（队列空 = 无 fix）
                if loc is not None:
                    self._data_queue.put({
                        "latitude": loc["latitude"],
                        "longitude": loc["longitude"],
                        "altitude": loc["altitude"],
                        "speed_kmh": loc["speed_kmh"],
                        "cog": loc.get("cog", 0.0),
                        "satellites": loc.get("satellites", 0),
                        "hdop": loc.get("hdop", 99.0),
                    })

            except Exception as e:
                print(f"[{self.name}] 后台线程异常: {e}")
                time.sleep_ms(1000)

    def _update_position(self, loc):
        """提取定位数据并更新状态"""
        self._data["latitude"] = loc["latitude"]
        self._data["longitude"] = loc["longitude"]
        self._data["altitude"] = loc["altitude"]
        self._data["speed_kmh"] = loc["speed_kmh"]
        self._data["cog"] = loc.get("cog", 0.0)
        self._data["valid"] = True
        self.ctx["err_count"] = 0
        self.ctx["no_fix_count"] = 0

        # 信号质量判定
        satellites = loc.get("satellites", 0)
        hdop = loc.get("hdop", 99.0)
        if satellites >= 4 and hdop < 2.0:
            self._data["signal_quality"] = "good"
        elif satellites >= 3 and hdop < 5.0:
            self._data["signal_quality"] = "fair"
        elif satellites > 0:
            self._data["signal_quality"] = "poor"
        else:
            self._data["signal_quality"] = "none"

        # 状态恢复
        old_state = self.ctx["gnss_state"]
        self.ctx["gnss_state"] = GNSS_STATE_FIXED
        self.ctx["gps_lost_reported"] = False

        if old_state != GNSS_STATE_FIXED:
            print(f"[{self.name}] ✓ 定位成功 | {loc['latitude']:.4f}, {loc['longitude']:.4f} | {self._data['signal_quality']}")

    # ==================== 事件回调 ====================
    def _on_config_update(self, payload):
        """配置更新：采样间隔、lost_count、功耗状态"""
        if payload.get("target") == self.name:
            if "sample_ms" in payload:
                self.cfg["sample_ms"] = int(payload["sample_ms"])
                print(f"[{self.name}] 采样间隔更新为 {self.cfg['sample_ms']}ms")
            if "lost_count" in payload:
                self.cfg["lost_count"] = int(payload["lost_count"])

        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]
            if payload["power_state"] == POWER_STATE_SUSPENDED:
                self.cfg["sample_ms"] = GNSS_SUSPENDED_MS
            elif payload["power_state"] == POWER_STATE_EMERGENCY:
                self.cfg["sample_ms"] = GNSS_EMERGENCY_MS
            elif payload["power_state"] == POWER_STATE_ACTIVE:
                self.cfg["sample_ms"] = GNSS_SAMPLE_MS
            print(f"[{self.name}] 功耗状态: {payload['power_state']}")

    # ==================== 辅助方法 ====================
    def get_data(self):
        """获取定位数据快照"""
        return {
            "latitude": self._data["latitude"],
            "longitude": self._data["longitude"],
            "altitude": self._data["altitude"],
            "speed_kmh": self._data["speed_kmh"],
            "cog": self._data["cog"],
            "signal_quality": self._data["signal_quality"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }

    def force_read(self):
        """
        brief 获取 GNSS 数据快照
        note GPS 数据由卫星信号决定更新率，无法强制获取新 fix
             返回最近一次 tick() 缓存的数据，并发布事件同步到 BLE/LCD
        return dict 数据副本
        """
        if self.event_bus:
            self.event_bus.publish(EVENT_GNSS_READY, self.get_data())
        return self.get_data()

    def get_status(self):
        """查询模块运行状态"""
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
            "gnss_state": self.ctx["gnss_state"],
            "no_fix_count": self.ctx["no_fix_count"],
            "thread_running": self.ctx["thread_running"],
        }

    def deinit(self):
        """停止 GNSS 定位 + 停止后台线程"""
        self.ctx["thread_running"] = False
        time.sleep_ms(100)
        try:
            if self.gnss:
                self.gnss.stop()
            self.ctx["gnss_state"] = GNSS_STATE_IDLE
            print(f"[{self.name}] ✓ 已停止")
        except Exception as e:
            print(f"[{self.name}] ✗ 停止失败: {e}")

    def stop(self):
        """停止 GNSS 定位（释放资源，兼容旧接口）"""
        self.deinit()
        return True