"""
brief 显示管理服务 - 管理LCD显示、背光调节、画面切换
note Service层业务服务，MicroPython环境，在真实硬件上运行

功能：
1. 开机画面：显示Logo(QQ图标) + 播放TTS
2. 正常画面：显示温度、湿度、定位、速度数据
3. 光照自动调节背光：订阅Light传感器事件
4. 报警联动：碰撞显示文字，SOS显示预警图标(移远图标)
5. 功耗管理：休眠关闭背光，唤醒恢复背光

画面布局（正常骑行画面，紧凑布局）：
    第1行 (y=10): T:25.5°C      (温度)
    第2行 (y=35): H:65%         (湿度)
    第3行 (y=60): Lat:31.23 Lon:121.47  (定位)
    第4行 (y=85): V:18.5km/h   (速度)
    第5行 (y=110): [导航行]     (由 NavigationService 写入)

图片说明：
    - images.py (QQ_ICON_40x40): 开机Logo，只显示一次
    - images1.py (Quectel_Icon_160x20): SOS预警图标，SOS报警时显示
"""
import time

from core.Base_Module import BaseModule
from core.config import (
    EVENT_TEMP_HUMID_READY,
    EVENT_GNSS_READY,
    EVENT_LIGHT_READY,
    EVENT_ALARM_TRIGGERED,
    EVENT_ALARM_CANCELED,
    EVENT_POWER_STATE_CHANGE,
    EVENT_CONFIG_UPDATE,
    EVENT_NAV_DISPLAY,
    EVENT_TTS_REQUEST,
    PRIORITY_NAV,
    POWER_STATE_ACTIVE,
)


class DisplayService(BaseModule):
    """
    显示管理服务：管理LCD显示、背光调节、画面切换
    
    功能：
    1. 开机画面：显示Logo(QQ图标) + 播放TTS
    2. 正常画面：显示温度、湿度、定位、速度数据
    3. 光照自动调节背光：订阅Light传感器事件
    4. 报警联动：碰撞显示文字，SOS显示预警图标(移远图标)
    5. 功耗管理：休眠关闭背光，唤醒恢复背光
    """
    
    def __init__(self, event_bus=None, lcd_driver=None, audio_driver=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "display"
        
        self.lcd_driver = lcd_driver
        self.audio_driver = audio_driver
        
        self.logo_data = None
        self.sos_icon_data = None
        
        self.cfg = {
            "boot_display_ms": 2500,
            "backlight_boot": 80,
            "backlight_normal": 60,
            "backlight_alarm": 100,
            "light_level_1": 100,
            "light_level_2": 500,
            "light_level_3": 1000,
            "backlight_level_1": 20,
            "backlight_level_2": 50,
            "backlight_level_3": 80,
            "backlight_level_4": 100,
            "logo_width": 40,
            "logo_height": 40,
            "logo_x": 60,
            "logo_y": 60,
            "sos_icon_width": 160,
            "sos_icon_height": 20,
            "sos_icon_x": 0,
            "sos_icon_y": 50,
            "tts_welcome": "智能骑行头盔已就绪",
            "sample_ms": 1000,
        }
        
        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "last_tick": 0,
            "display_mode": "blank",
            "is_alarm_active": False,
            "boot_displayed": False,
            "boot_start_time": 0,
            "power_state": POWER_STATE_ACTIVE,
            "current_backlight": 60,
            "err_count": 0,
        }
        
        self._data = {
            "temp": None,
            "humid": None,
            "lat": None,
            "lon": None,
            "speed": None,
            "light_intensity": None,
            "logo_loaded": False,
            "sos_icon_loaded": False,
        }

        # 导航文字缓存（由 EVENT_NAV_DISPLAY 更新，渲染时恢复）
        self._nav_text = ""
    
    def init(self):
        try:
            self._load_images()
            
            if self.event_bus:
                self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid_ready)
                self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss_ready)
                self.event_bus.subscribe(EVENT_LIGHT_READY, self._on_light_ready)
                self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm_triggered)
                self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_power_state_change)
                self.event_bus.subscribe(EVENT_CONFIG_UPDATE, self._on_config_update)
                self.event_bus.subscribe(EVENT_NAV_DISPLAY, self._on_nav_display)
            
            self._show_boot_screen()
            
            self.ctx["is_init"] = True
            print("[{}] 初始化完成".format(self.name))
            
        except Exception as e:
            print("[{}] 初始化失败: {}".format(self.name, e))
            raise
    
    def tick(self):
        if not self.ctx["is_init"]:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return
        # boot→normal 切换不受电源状态影响
        if self.ctx["display_mode"] == "boot":
            elapsed = time.ticks_diff(now, self.ctx["boot_start_time"])
            if elapsed >= self.cfg["boot_display_ms"]:
                self._switch_to_normal()
        self.ctx["last_tick"] = now
        # 非 ACTIVE 模式跳过正常画面渲染
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
    
    def _load_images(self):
        """加载两个图片"""
        try:
            from images import QQ_ICON_40x40
            self.logo_data = QQ_ICON_40x40
            self._data["logo_loaded"] = True
            print("[{}] 开机Logo加载成功 (40x40)".format(self.name))
        except ImportError as e:
            print("[{}] 开机Logo加载失败: {}".format(self.name, e))
            self.logo_data = None
            self._data["logo_loaded"] = False
        except Exception as e:
            print("[{}] 开机Logo数据异常: {}".format(self.name, e))
            self.logo_data = None
            self._data["logo_loaded"] = False
        
        try:
            from images1 import Quectel_Icon_160x20
            self.sos_icon_data = Quectel_Icon_160x20
            self._data["sos_icon_loaded"] = True
            print("[{}] SOS预警图标加载成功 (160x20)".format(self.name))
        except ImportError as e:
            print("[{}] SOS预警图标加载失败: {}".format(self.name, e))
            self.sos_icon_data = None
            self._data["sos_icon_loaded"] = False
        except Exception as e:
            print("[{}] SOS预警图标数据异常: {}".format(self.name, e))
            self.sos_icon_data = None
            self._data["sos_icon_loaded"] = False
    
    def _validate_image_data(self, data, width, height):
        if data is None:
            return False
        if not isinstance(data, (bytes, bytearray)):
            return False
        if width <= 0 or height <= 0:
            return False
        expected_size = width * height * 2
        if len(data) < expected_size:
            print("[{}] 图片数据长度不足: {} < {}".format(self.name, len(data), expected_size))
            return False
        return True
    
    def _show_boot_screen(self):
        """显示开机画面：只显示Logo(QQ图标)"""
        if not self.lcd_driver:
            print("[{}] LCD驱动未注入，跳过开机画面".format(self.name))
            return
        
        self.ctx["is_busy"] = True
        try:
            self.lcd_driver.clear()
            
            if self._data["logo_loaded"] and self.logo_data:
                if self._validate_image_data(self.logo_data, self.cfg["logo_width"], self.cfg["logo_height"]):
                    self.lcd_driver.show_image(
                        self.cfg["logo_x"],
                        self.cfg["logo_y"],
                        self.cfg["logo_width"],
                        self.cfg["logo_height"],
                        self.logo_data
                    )
                    print("[{}] 开机Logo显示成功".format(self.name))
            
            if hasattr(self.lcd_driver, 'set_backlight'):
                self.lcd_driver.set_backlight(self.cfg["backlight_boot"])
                self.ctx["current_backlight"] = self.cfg["backlight_boot"]
            
            if self.event_bus:
                self.event_bus.publish(EVENT_TTS_REQUEST, {
                    "text": self.cfg["tts_welcome"],
                    "priority": PRIORITY_NAV,
                })
                print("[{}] TTS播报: {}".format(self.name, self.cfg['tts_welcome']))
            
            self.ctx["display_mode"] = "boot"
            self.ctx["boot_start_time"] = time.ticks_ms()
            print("[{}] 开机画面显示完成".format(self.name))
            
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 开机画面显示异常: {}".format(self.name, e))
        finally:
            self.ctx["is_busy"] = False
    
    def _switch_to_normal(self):
        """切换到正常骑行画面"""
        if not self.lcd_driver:
            return
        self.ctx["is_busy"] = True
        try:
            self.lcd_driver.clear()
            self.ctx["display_mode"] = "normal"
            self.ctx["boot_displayed"] = True
            
            if self._data["light_intensity"] is not None:
                backlight = self._get_backlight_by_light(self._data["light_intensity"])
            else:
                backlight = self.cfg["backlight_normal"]
            if hasattr(self.lcd_driver, 'set_backlight'):
                self.lcd_driver.set_backlight(backlight)
                self.ctx["current_backlight"] = backlight
            
            self._render_normal_screen()
            print("[{}] 切换到正常骑行画面".format(self.name))
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 切换画面异常: {}".format(self.name, e))
        finally:
            self.ctx["is_busy"] = False
    
    def _format_temperature(self, temp):
        """格式化温度数据：T:25.5°C 或 T:--.-°C"""
        if temp is None:
            return "T:--.-C"
        if not isinstance(temp, (int, float)):
            return "T:--.-C"
        if temp < -40 or temp > 85:
            return "T:--.-C"
        return "T:{:.1f}C".format(temp)
    
    def _format_humidity(self, humid):
        """格式化湿度数据：H:65% 或 H:--%"""
        if humid is None:
            return "H:--%"
        if not isinstance(humid, (int, float)):
            return "H:--%"
        if humid < 0 or humid > 100:
            return "H:--%"
        return "H:{:.0f}%".format(humid)
    
    def _format_location(self, lat, lon):
        """格式化定位数据：Lat:31.23 Lon:121.47"""
        if lat is None or lon is None:
            return "Lat:--.-- Lon:--.--"
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return "Lat:--.-- Lon:--.--"
        if lat < -90 or lat > 90 or lon < -180 or lon > 180:
            return "Lat:--.-- Lon:--.--"
        return "Lat:{:.2f} Lon:{:.2f}".format(lat, lon)
    
    def _format_speed(self, speed):
        """格式化速度数据：V:18.5km/h 或 V:--.-km/h"""
        if speed is None:
            return "V:--.-km/h"
        if not isinstance(speed, (int, float)):
            return "V:--.-km/h"
        if speed < 0 or speed > 200:
            return "V:--.-km/h"
        return "V:{:.1f}km/h".format(speed)
    
    def _render_normal_screen(self):
        """渲染正常骑行画面：显示温湿度、定位、速度数据"""
        if not self.lcd_driver:
            return
        
        try:
            if hasattr(self.lcd_driver, 'lcd') and hasattr(self.lcd_driver.lcd, 'show_string'):
                lcd = self.lcd_driver.lcd
                
                temp_str = self._format_temperature(self._data["temp"])
                humid_str = self._format_humidity(self._data["humid"])
                location_str = self._format_location(self._data["lat"], self._data["lon"])
                speed_str = self._format_speed(self._data["speed"])
                
                lcd.show_string(10, 10, temp_str, lcd.WHITE, lcd.BLACK)
                lcd.show_string(10, 35, humid_str, lcd.WHITE, lcd.BLACK)
                lcd.show_string(10, 60, location_str, lcd.WHITE, lcd.BLACK)
                lcd.show_string(10, 85, speed_str, lcd.WHITE, lcd.BLACK)
                
                print("[{}] 正常画面渲染: {} {} {} {}".format(
                    self.name, temp_str, humid_str, location_str, speed_str))

                # 恢复导航文字（如果有）
                if self._nav_text and hasattr(self.lcd_driver, 'show_nav_line'):
                    try:
                        self.lcd_driver.show_nav_line(10, 110, self._nav_text)
                    except Exception:
                        pass
        
        except Exception as e:
            print("[{}] 正常画面渲染失败: {}".format(self.name, e))
    
    def _update_normal_display(self):
        """更新正常画面显示"""
        if not self.ctx["is_init"]:
            return
        if self.ctx["display_mode"] != "normal":
            return
        if self.ctx["is_alarm_active"]:
            return
        if self.ctx["is_busy"]:
            return
        
        self._render_normal_screen()
    
    def _get_backlight_by_light(self, light_intensity):
        """根据光照强度计算背光亮度（自动）"""
        if light_intensity < self.cfg["light_level_1"]:
            return self.cfg["backlight_level_1"]
        elif light_intensity < self.cfg["light_level_2"]:
            return self.cfg["backlight_level_2"]
        elif light_intensity < self.cfg["light_level_3"]:
            return self.cfg["backlight_level_3"]
        else:
            return self.cfg["backlight_level_4"]
    
    def _on_temp_humid_ready(self, payload):
        """温湿度数据回调：更新数据并刷新画面"""
        if not self.ctx["is_init"]:
            return
        temp = payload.get("temp")
        humid = payload.get("humid")
        if temp is not None:
            self._data["temp"] = temp
        if humid is not None:
            self._data["humid"] = humid
        self._update_normal_display()
    
    def _on_gnss_ready(self, payload):
        """GNSS数据回调：更新数据并刷新画面"""
        if not self.ctx["is_init"]:
            return
        lat = payload.get("latitude")
        lon = payload.get("longitude")
        speed = payload.get("speed_kmh")
        if lat is not None:
            self._data["lat"] = lat
        if lon is not None:
            self._data["lon"] = lon
        if speed is not None:
            self._data["speed"] = speed
        self._update_normal_display()
    
    def _on_light_ready(self, payload):
        """光照数据回调：自动调节背光"""
        if not self.ctx["is_init"]:
            return
        light_intensity = payload.get("light_intensity", payload.get("value"))
        if light_intensity is None:
            return
        if not isinstance(light_intensity, (int, float)) or light_intensity < 0:
            return
        
        self._data["light_intensity"] = light_intensity
        
        if self.ctx["is_alarm_active"]:
            return
        
        backlight = self._get_backlight_by_light(light_intensity)
        if self.lcd_driver and hasattr(self.lcd_driver, 'set_backlight'):
            try:
                self.lcd_driver.set_backlight(backlight)
                self.ctx["current_backlight"] = backlight
            except Exception as e:
                print("[{}] 背光调节失败: {}".format(self.name, e))
    
    def _on_alarm_triggered(self, payload):
        """报警触发回调：碰撞显示文字，SOS显示预警图标"""
        if not self.ctx["is_init"]:
            return
        
        self.ctx["is_alarm_active"] = True
        alarm_type = payload.get("alarm_type", "unknown")
        
        if not self.lcd_driver:
            return
        
        self.ctx["is_busy"] = True
        try:
            self.lcd_driver.clear()
            
            if alarm_type == "sos":
                print("[{}] SOS报警：显示预警图标".format(self.name))
                
                if self._data["sos_icon_loaded"] and self.sos_icon_data:
                    if self._validate_image_data(
                        self.sos_icon_data,
                        self.cfg["sos_icon_width"],
                        self.cfg["sos_icon_height"]
                    ):
                        self.lcd_driver.show_image(
                            self.cfg["sos_icon_x"],
                            self.cfg["sos_icon_y"],
                            self.cfg["sos_icon_width"],
                            self.cfg["sos_icon_height"],
                            self.sos_icon_data
                        )
                        print("[{}] SOS预警图标显示成功".format(self.name))
                
                if hasattr(self.lcd_driver, 'lcd') and hasattr(self.lcd_driver.lcd, 'show_string'):
                    self.lcd_driver.lcd.show_string(10, 80, "SOS!", 
                        self.lcd_driver.lcd.RED, self.lcd_driver.lcd.BLACK)
                
                self.ctx["display_mode"] = "alarm"
                
            elif alarm_type == "collision":
                print("[{}] 碰撞报警：显示文字".format(self.name))
                if hasattr(self.lcd_driver, 'show_alarm'):
                    self.lcd_driver.show_alarm(alarm_type)
                self.ctx["display_mode"] = "alarm"
            
            else:
                print("[{}] 其他报警: {}".format(self.name, alarm_type))
                if hasattr(self.lcd_driver, 'show_alarm'):
                    self.lcd_driver.show_alarm(alarm_type)
                self.ctx["display_mode"] = "alarm"
            
            if hasattr(self.lcd_driver, 'set_backlight'):
                self.lcd_driver.set_backlight(self.cfg["backlight_alarm"])
                self.ctx["current_backlight"] = self.cfg["backlight_alarm"]
            
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 报警画面显示失败: {}".format(self.name, e))
        finally:
            self.ctx["is_busy"] = False
    
    def _on_alarm_canceled(self, payload):
        """报警取消回调：恢复正常画面"""
        if not self.ctx["is_init"]:
            return
        
        self.ctx["is_alarm_active"] = False
        
        if not self.lcd_driver:
            return
        
        self.ctx["is_busy"] = True
        try:
            self.lcd_driver.clear()
            
            if hasattr(self.lcd_driver, 'set_backlight'):
                backlight = self.cfg["backlight_normal"]
                if self._data["light_intensity"] is not None:
                    backlight = self._get_backlight_by_light(self._data["light_intensity"])
                self.lcd_driver.set_backlight(backlight)
                self.ctx["current_backlight"] = backlight
            
            self.ctx["display_mode"] = "normal"
            self._render_normal_screen()
            print("[{}] 报警取消，恢复正常画面".format(self.name))
            
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 恢复正常画面失败: {}".format(self.name, e))
        finally:
            self.ctx["is_busy"] = False
    
    def _on_power_state_change(self, payload):
        """功耗状态变化回调"""
        if not self.ctx["is_init"]:
            return
        old_state = self.ctx["power_state"]
        new_state = payload.get("power_state", POWER_STATE_ACTIVE)
        self.ctx["power_state"] = new_state
        
        if new_state != POWER_STATE_ACTIVE:
            if self.lcd_driver and hasattr(self.lcd_driver, 'set_backlight'):
                self.lcd_driver.set_backlight(0)
                self.ctx["current_backlight"] = 0
            print("[{}] 进入休眠，关闭背光".format(self.name))
        elif old_state != POWER_STATE_ACTIVE:
            if self.lcd_driver and hasattr(self.lcd_driver, 'set_backlight'):
                backlight = self.ctx.get("current_backlight", self.cfg["backlight_normal"])
                if backlight == 0:
                    backlight = self.cfg["backlight_normal"]
                self.lcd_driver.set_backlight(backlight)
                self.ctx["current_backlight"] = backlight
            print("[{}] 唤醒，恢复背光".format(self.name))
    
    def _on_config_update(self, payload):
        """配置更新回调"""
        if payload.get("target") == self.name:
            if "boot_display_ms" in payload:
                self.cfg["boot_display_ms"] = int(payload["boot_display_ms"])
            if "backlight_normal" in payload:
                self.cfg["backlight_normal"] = int(payload["backlight_normal"])
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]

    def _on_nav_display(self, payload):
        """
        brief 导航显示内容变更回调
        param payload: {"text": str} — 空字符串表示清除导航文字
        """
        self._nav_text = payload.get("text", "")
    
    def get_data(self):
        """获取当前显示数据"""
        return {
            "temp": self._data["temp"],
            "humid": self._data["humid"],
            "lat": self._data["lat"],
            "lon": self._data["lon"],
            "speed": self._data["speed"],
            "light_intensity": self._data["light_intensity"],
            "logo_loaded": self._data["logo_loaded"],
            "sos_icon_loaded": self._data["sos_icon_loaded"],
            "timestamp": time.ticks_ms()
        }
    
    def get_status(self):
        """获取模块运行状态"""
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "display_mode": self.ctx["display_mode"],
            "is_alarm_active": self.ctx["is_alarm_active"],
            "boot_displayed": self.ctx["boot_displayed"],
            "power_state": self.ctx["power_state"],
            "current_backlight": self.ctx["current_backlight"],
            "err_count": self.ctx["err_count"]
        }
