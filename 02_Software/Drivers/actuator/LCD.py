"""
brief LCD显示驱动模块 (ST7735 1.8寸TFT)
note 严格遵循四元组架构规范，适配移远模组SPI1总线
      Device层纯硬件控制，不包含业务逻辑，不订阅业务/数据事件
      Service层(AlarmService/CloudService/DisplayService)调用LCD公共接口更新显示
"""
import machine
import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_LCD_ERROR, EVENT_CONFIG_UPDATE, EVENT_POWER_STATE_CHANGE,
    LCD_BACKLIGHT_HIGH, LCD_SAMPLE_MS, POWER_STATE_ACTIVE
)
from st7735 import LCD


class LCDDriver(BaseModule):
    def __init__(self, event_bus=None):
        """
        brief 初始化LCD驱动实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus  # 保存事件总线引用
        self.name = "lcd"           # 模块标识符（必须唯一）

        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            "spi_id": 1,                # 移远固件预定义的 SPI1
            "spi_baudrate": 20000000,   # 通信频率 20MHz
            "spi_polarity": 0,          # SPI极性
            "spi_phase": 0,             # SPI相位
            "dc_pin": "F12",            # 数据/命令选择引脚
            "cs_pin": "D14",            # 片选引脚
            "rotation": 1,              # 屏幕旋转角度(1=横向)
            "sample_ms": LCD_SAMPLE_MS, # 默认刷新间隔 2000ms
            "max_retry": 3,             # 连续失败最大重试次数
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,           # 硬件初始化完成标志
            "is_busy": False,           # 显示操作中标志（防重入）
            "busy_started": 0,          # is_busy 锁定起始时间戳（超时自动解锁）
            "last_tick": 0,             # 上次操作时间戳
            "err_count": 0,             # 连续操作错误计数
            "power_state": POWER_STATE_ACTIVE,  # 功耗状态
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "display_mode": "blank",    # 画面模式: normal/alarm_collision/alarm_sos/alarm_unknown/blank
            "temp": 0.0,                # 当前显示温度 (℃)
            "humid": 0.0,               # 当前显示湿度 (%RH)
            "lat": 0.0,                 # 当前显示纬度 (度)
            "lon": 0.0,                 # 当前显示经度 (度)
            "alarm_type": "",           # 当前报警类型: collision/sos/unknown/""
            "backlight": LCD_BACKLIGHT_HIGH,  # 当前背光亮度 0-100(%)
            "valid": False,             # 数据有效性标志
        }

        self.spi = None                 # SPI 实例句柄
        self.lcd = None                 # ST7735 LCD 实例句柄

    def init(self):
        """
        brief 初始化模块：硬件配置 + 订阅事件
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            # ====== 1. 初始化SPI总线 ======
            self.spi = machine.SPI(
                self.cfg["spi_id"],
                baudrate=self.cfg["spi_baudrate"],
                polarity=self.cfg["spi_polarity"],
                phase=self.cfg["spi_phase"]
            )

            # ====== 2. 创建LCD设备实例 ======
            self.lcd = LCD(self.spi, dc_pin=self.cfg["dc_pin"], cs_pin=self.cfg["cs_pin"])

            # ====== 3. 设置屏幕旋转 ======
            self.lcd.set_rotation(self.cfg["rotation"])

            # ====== 4. 初始清屏 ======
            self.lcd.fill_screen(self.lcd.BLACK)
            self.lcd.flush()

            # ====== 5. 订阅事件 ======
            if self.event_bus:
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_config_update)

            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成 | SPI{self.cfg['spi_id']} @ {self.cfg['spi_baudrate']}Hz, dc={self.cfg['dc_pin']}, cs={self.cfg['cs_pin']}")

        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        """
        brief 周期调度：功耗状态检查 + 时间片控制
        note LCD为被动显示设备，tick()不自动执行画面渲染
              显示操作由Service层主动调用公共接口触发
              tick()仅用于功耗守卫、时间片控制和状态维护
        """
        # 状态守卫：功耗模式控制
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

        # 时间片校验：未到间隔立即返回
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return

        # LCD为被动显示，tick()仅更新时间戳
        self.ctx["last_tick"] = now

        # is_busy 超时自动解锁（防止 SPI 挂死导致永久锁定）
        if self.ctx["is_busy"] and self.ctx["busy_started"] > 0:
            if time.ticks_diff(now, self.ctx["busy_started"]) > 5000:
                print("[{}] WARNING: is_busy 超时 5s，强制解锁".format(self.name))
                self.ctx["is_busy"] = False
                self.ctx["busy_started"] = 0

    # ==================== 公共显示接口（供Service层调用）====================

    def show_normal_data(self, temp, humid, lat, lon):
        """
        brief 显示正常骑行数据画面
        param temp: 温度值 (℃)
        param humid: 湿度值 (%RH)
        param lat: 纬度 (度)
        param lon: 经度 (度)
        note CloudService调用此接口刷新骑行数据显示
        """
        if not self.ctx["is_init"]:
            return

        if self._data["display_mode"] in ("alarm_collision", "alarm_sos", "alarm_unknown"):
            return

        if self.ctx["is_busy"]:
            return

        self.ctx["is_busy"] = True
        self.ctx["busy_started"] = time.ticks_ms()
        try:
            # ====== 清屏并绘制标题 ======
            self.lcd.fill_screen(self.lcd.BLACK)

            # ====== 温湿度区域 ======
            self.lcd.show_string(0, 6, "Temp/Humi", self.lcd.BLUE, self.lcd.BLACK)
            temp_humi_str = "{}C / {}%".format(
                self._format_float(temp, 1),
                self._format_float(humid, 1)
            )
            self.lcd.show_string(0, 26, temp_humi_str, self.lcd.WHITE, self.lcd.BLACK)

            # ====== 定位区域 ======
            self.lcd.show_string(0, 46, "Position", self.lcd.BLUE, self.lcd.BLACK)
            lat_str = "Lat:{}".format(self._format_float(lat, 4))
            lon_str = "Lon:{}".format(self._format_float(lon, 4))
            self.lcd.show_string(0, 66, lat_str, self.lcd.WHITE, self.lcd.BLACK)
            self.lcd.show_string(0, 86, lon_str, self.lcd.WHITE, self.lcd.BLACK)

            # ====== 刷新屏幕 ======
            self.lcd.flush()

            # ====== 更新内部数据 ======
            self._data["display_mode"] = "normal"
            self._data["temp"] = temp
            self._data["humid"] = humid
            self._data["lat"] = lat
            self._data["lon"] = lon
            self._data["alarm_type"] = ""
            self._data["valid"] = True
            self.ctx["err_count"] = 0

        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] 显示异常 ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LCD_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False

    def show_alarm(self, alarm_type):
        """
        brief 显示报警画面
        param alarm_type: 报警类型 ("collision" / "sos")
        note AlarmService调用此接口显示碰撞或SOS报警画面
        """
        if not self.ctx["is_init"]:
            return

        if self.ctx["is_busy"]:
            return

        self.ctx["is_busy"] = True
        self.ctx["busy_started"] = time.ticks_ms()
        try:
            # ====== 清屏 ======
            self.lcd.fill_screen(self.lcd.BLACK)

            # ====== 根据报警类型绘制画面 ======
            if alarm_type == "collision":
                self.lcd.show_string(10, 40, "COLLISION!", self.lcd.RED, self.lcd.BLACK)
                self.lcd.show_string(30, 70, "SOS", self.lcd.RED, self.lcd.BLACK)
                self._data["display_mode"] = "alarm_collision"
                self._data["alarm_type"] = "collision"
            elif alarm_type == "sos":
                self.lcd.show_string(10, 40, "EMERGENCY!", self.lcd.RED, self.lcd.BLACK)
                self.lcd.show_string(30, 70, "SOS", self.lcd.RED, self.lcd.BLACK)
                self._data["display_mode"] = "alarm_sos"
                self._data["alarm_type"] = "sos"
            else:
                self.lcd.show_string(10, 40, "ALARM!", self.lcd.RED, self.lcd.BLACK)
                self.lcd.show_string(30, 70, "SOS", self.lcd.RED, self.lcd.BLACK)
                self._data["display_mode"] = "alarm_unknown"
                self._data["alarm_type"] = "unknown"

            # ====== 刷新屏幕 ======
            self.lcd.flush()
            self._data["valid"] = True
            self.ctx["err_count"] = 0

        except Exception as e:
            self.ctx["err_count"] += 1
            self._data["valid"] = False
            print("[{}] 报警显示异常 ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LCD_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False

    def clear(self):
        """
        brief 清屏操作
        note 清除屏幕内容，画面模式切为blank
        """
        if not self.ctx["is_init"]:
            return

        if self.ctx["is_busy"]:
            return

        self.ctx["is_busy"] = True
        self.ctx["busy_started"] = time.ticks_ms()
        try:
            self.lcd.fill_screen(self.lcd.BLACK)
            self.lcd.flush()

            # ====== 重置显示数据 ======
            self._data["display_mode"] = "normal"
            self._data["temp"] = 0.0
            self._data["humid"] = 0.0
            self._data["lat"] = 0.0
            self._data["lon"] = 0.0
            self._data["alarm_type"] = ""
            self._data["valid"] = True
            self.ctx["err_count"] = 0

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 清屏异常 ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LCD_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False

    def set_backlight(self, level):
        """
        brief 设置背光亮度
        param level: 背光亮度百分比 (0-100)，0=关闭/休眠，100=最大亮度
        note DisplayService根据光照强度调用此接口调节背光
              若硬件不支持PWM背光，仅记录亮度值
        """
        if not self.ctx["is_init"]:
            return

        # ====== 边界截断 ======
        if level > 100:
            level = 100
        elif level < 0:
            level = 0

        # ====== 休眠联动 ======
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            level = 0

        old_backlight = self._data["backlight"]
        self._data["backlight"] = level

        if old_backlight > 0 and level == 0:
            print("[{}] 背光关闭，LCD进入休眠".format(self.name))
        elif old_backlight == 0 and level > 0:
            print("[{}] 背光恢复，LCD从休眠唤醒".format(self.name))

    def show_image(self, x, y, w, h, data):
        """
        brief 在指定位置显示RGB565格式图标
        param x: 起始X坐标
        param y: 起始Y坐标
        param w: 图标宽度
        param h: 图标高度
        param data: RGB565格式图标数据 (bytearray)
        """
        if not self.ctx["is_init"]:
            return

        if self.ctx["is_busy"]:
            return

        self.ctx["is_busy"] = True
        self.ctx["busy_started"] = time.ticks_ms()
        try:
            self.lcd.show_image(x, y, w, h, data)
            self.lcd.flush()
            self.ctx["err_count"] = 0

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 图标显示异常 ({}): {}".format(self.name, self.ctx["err_count"], e))
            if self.ctx["err_count"] > self.cfg["max_retry"]:
                if self.event_bus:
                    self.event_bus.publish(EVENT_LCD_ERROR, self.get_error_data(e))
        finally:
            self.ctx["is_busy"] = False

    def show_nav_line(self, x, y, text, fg=None, bg=None):
        """
        brief 在指定位置显示导航文本行（供 NavigationService 调用）
        param x: 起始X坐标
        param y: 起始Y坐标
        param text: 文本内容
        param fg: 前景色，默认 GREEN
        param bg: 背景色，默认 BLACK
        note 封装 lcd.show_string + fill_rectangle，避免外部直接访问 self.lcd
        """
        if not self.ctx["is_init"] or not self.lcd:
            return
        if self.ctx["is_busy"]:
            return
        self.ctx["is_busy"] = True
        self.ctx["busy_started"] = time.ticks_ms()
        try:
            if fg is None:
                fg = self.lcd.GREEN
            if bg is None:
                bg = self.lcd.BLACK
            self.lcd.fill_rectangle(x, y, 150, 16, bg)
            self.lcd.show_string(x, y, text, fg, bg)
            self.lcd.flush()
        except Exception as e:
            print("[{}] show_nav_line 失败: {}".format(self.name, e))
        finally:
            self.ctx["is_busy"] = False

    # ==================== 事件回调 ====================

    def _on_config_update(self, payload):
        """
        brief 配置更新回调处理
        param payload: 配置事件负载
        note
            - target: 指定目标模块（可选，用于模块特定配置）
            - sample_ms: 刷新间隔（需要target）
            - power_state: 功耗状态（全局配置）
        """
        # ====== 1. 刷新间隔更新（模块特定配置）======
        if payload.get("target") == self.name and "sample_ms" in payload:
            self.cfg["sample_ms"] = int(payload["sample_ms"])
            print("[{}] 刷新间隔更新为 {}ms".format(self.name, self.cfg["sample_ms"]))

        # ====== 2. 功耗状态更新（全局配置）======
        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            print("[{}] 功耗状态: {} -> {}".format(self.name, old_state, payload["power_state"]))

            if payload["power_state"] != POWER_STATE_ACTIVE:
                self.set_backlight(0)
            elif old_state != POWER_STATE_ACTIVE:
                self.set_backlight(self._data["backlight"] or LCD_BACKLIGHT_HIGH)

    # ==================== 辅助方法 ====================

    def _format_float(self, value, decimal_places):
        """
        brief 格式化浮点数为字符串（兼容MicroPython）
        param value: 数值
        param decimal_places: 小数位数
        return str 格式化后的字符串
        note MicroPython不一定支持f-string的:.Nf格式，使用round+str兜底
        """
        try:
            rounded = round(float(value), decimal_places)
            if decimal_places == 0:
                return str(int(rounded))
            fmt = "{{:.{}f}}".format(decimal_places)
            return fmt.format(rounded)
        except (TypeError, ValueError):
            return str(value)

    def get_data(self):
        """
        brief 获取当前显示数据快照
        return dict 数据副本 {display_mode, temp, humid, lat, lon, alarm_type, backlight, valid, timestamp}
        """
        return {
            "display_mode": self._data["display_mode"],
            "temp": self._data["temp"],
            "humid": self._data["humid"],
            "lat": self._data["lat"],
            "lon": self._data["lon"],
            "alarm_type": self._data["alarm_type"],
            "backlight": self._data["backlight"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms()
        }

    def get_status(self):
        """
        brief 查询模块运行状态快照
        return dict 运行上下文 {is_init, is_busy, err_count, power_state}
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"]
        }
