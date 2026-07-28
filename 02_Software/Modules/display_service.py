"""
brief 显示管理服务 - 洛天依主题开机动画、报警差异化显示（⚠️图标居中）、报警优先覆盖电源模式
note Service层业务服务，MicroPython环境，在真实硬件上运行

功能：
1. 开机画面：洛天依头像(100x100图片) + "队伍：锦依卫队"(160x20预渲染中文图片条)；TTS欢迎语延迟到SYSTEM_READY后播报
2. 正常画面：英文显示温度、湿度、定位、速度数据（font=8仅支持ASCII）
3. 光照自动调节背光：订阅Light传感器事件
4. 报警差异化显示（全部英文，font=8）：
   - collision：⚠️图标居中 + CRASH! + Lv + 经纬度 + 提示 + 文字闪烁
   - sos：⚠️图标居中 + EMERGENCY! + SOS + 背光闪烁
   - stealth：LCD保持不变，不改变任何显示
5. 报警优先覆盖电源模式：
   - 报警期间：不清屏、不关背光、LCD alarm_override=True
   - 唤醒恢复：报警时重新渲染报警画面而非正常画面
6. 功耗管理：休眠关闭背光（报警期间豁免）

画面布局（碰撞报警画面，160x128，font=8 ASCII）：
    第0-11行: Lat经纬度（绿色，左侧）
    第12-27行: Lon经纬度（绿色，左侧）
    第0-47行: ⚠️ 等腰三角形图标居中（48x48, x=56，覆盖经纬度右侧重叠）
    第52-67行: CRASH!（红色，居中x=56）
    第68-83行: Lv:X（黄色，居中x=64）
    第84-99行: Check Safety（白色，居中x=32）
    第100-115行: Cancel in 30s（灰色0x8410，居中x=24）

画面布局（SOS报警画面，160x128，font=8 ASCII）：
    第0-11行: Lat经纬度（绿色，左侧）
    第12-27行: Lon经纬度（绿色，左侧）
    第0-47行: ⚠️ 等腰三角形图标居中（48x48, x=56）
    第52-67行: EMERGENCY!（红色，居中x=40）
    第68-83行: SOS（红色，居中x=68）
    第84-99行: Help Sent（黄色，居中x=36）
    第100-115行: Press to Cancel（灰色0x8410，居中x=16）

画面布局（开机画面，160x128）：
    第0-99行: 洛天依头像（100x100图片, x=30）
    第108-127行: "队伍：锦依卫队"（160x20预渲染图片条, x=0）
    boot画面持续显示直到EVENT_SYSTEM_READY触发切换到normal

图片说明：
    - images2.py (LUOTIANYI_ICON_100x100): 洛天依头像，~20KB bytes，boot后释放
    - alarm_icon.py (ALARM_WARNING_ICON_48x48): ⚠️等腰三角形+感叹号，~4.6KB bytes，常驻
    - boot_text.py (BOOT_TEXT_160x20): 中文文字条，~6.4KB bytes，boot后释放
    EC200U show_string() 仅支持ASCII字体（font=8），不支持中文。
    中文文字通过预渲染为RGB565图片像素数据，用show_image()显示。
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
    EVENT_SYSTEM_READY,
    PRIORITY_NAV,
    POWER_STATE_ACTIVE,
    TTS_BOOT_WELCOME,
)


class DisplayService(BaseModule):
    """
    显示管理服务：洛天依主题开机动画 + 报警差异化 + 报警优先覆盖电源模式
    
    状态机：boot → normal → alarm → normal
    boot→normal 由 EVENT_SYSTEM_READY 触发（所有模块初始化完成后）
    报警优先原则：报警期间任何电源模式变化不影响报警画面和背光
    
    中文显示策略：
    - 开机画面中文文字预渲染为图片条，用show_image()显示
    - 正常/报警画面全部使用英文ASCII，用show_string()显示
    """
    
    def __init__(self, event_bus=None, lcd_driver=None, audio_driver=None):
        super().__init__()
        self.event_bus = event_bus
        self.name = "display"
        
        self.lcd_driver = lcd_driver
        self.audio_driver = audio_driver
        
        self.luotianyi_icon_data = None
        self.alarm_warning_icon_data = None  # ⚠️ 报警预警图标（常驻）
        self.boot_text_data = None           # 开机中文文字条（boot后释放）
        
        # SOS 背光闪烁状态（仅切换背光亮度，不重绘文字，<1ms）
        self._sos_flash_state = False
        self._last_flash_tick = 0
        
        self.cfg = {
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
            # 洛天依头像参数
            "luotianyi_width": 100, "luotianyi_height": 100,
            "luotianyi_x": 30, "luotianyi_y": 0,
            # 报警预警图标参数（等腰三角形+感叹号）
            "alarm_icon_width": 48, "alarm_icon_height": 48,
            "alarm_icon_x": 56, "alarm_icon_y": 0,  # 居中 x=(160-48)/2=56
            # 开机中文文字条参数
            "boot_text_width": 160, "boot_text_height": 20,
            "boot_text_x": 0, "boot_text_y": 108,
            # TTS 欢迎语
            "tts_welcome": TTS_BOOT_WELCOME,
            "sample_ms": 1000,
            # SOS 背光闪烁参数
            "sos_flash_interval_ms": 500,
            "sos_flash_low": 30,
            "sos_flash_high": 100,
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
            # 报警状态字段（用于恢复报警画面）
            "alarm_type": "",
            "alarm_level": 0,
            "alarm_start": 0,
        }
        
        # 脏标志
        self._dirty = False
        self._last_render_time = 0
        self._min_render_interval = 100
        
        # 报警画面延迟渲染标志（零阻塞回调架构）
        self._alarm_needs_render = False
        self._collision_flash_state = False
        self._collision_flash_last_tick = 0
        self._needs_clear = False  # 报警取消后需要清屏标志
        self._needs_switch_to_normal = False  # 新增: _on_system_ready 延迟标志
        
        self._data = {
            "temp": None,
            "humid": None,
            "lat": None,
            "lon": None,
            "speed": None,
            "light_intensity": None,
            "luotianyi_loaded": False,
            "alarm_icon_loaded": False,
            "boot_text_loaded": False,
        }
        
        # 导航文字、动作缓存与渲染状态
        self._nav_text = ""
        self._nav_action = ""
        self._rendered_nav_text = None
        self._rendered_nav_action = None
        self._nav_expire_time = 0
    
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
                self.event_bus.subscribe(EVENT_SYSTEM_READY, self._on_system_ready)
            
            self._show_boot_screen()
            
            self.ctx["is_init"] = True
            print("[{}] 初始化完成".format(self.name))
            
        except Exception as e:
            print("[{}] 初始化失败: {}".format(self.name, e))
            raise
    
    def tick(self):
        # ====== 1. 心跳更新（必须在所有状态守卫之前）======
        self.ctx["last_hb"] = time.ticks_ms()

        if not self.ctx["is_init"]:
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return
        
        # boot 模式：等待 EVENT_SYSTEM_READY 触发切换
        
        # SOS 背光闪烁（仅在 alarm + sos 模式下）
        if self.ctx["display_mode"] == "alarm" and self.ctx["alarm_type"] == "sos":
            self._tick_sos_flash(now)
        
        # 碰撞报警文字闪烁（零阻塞，仅翻转颜色）
        if self.ctx["display_mode"] == "alarm" and self.ctx["alarm_type"] == "collision":
            if not self._alarm_needs_render:
                if time.ticks_diff(now, self._collision_flash_last_tick) >= 500:
                    self._collision_flash_last_tick = now
                    self._collision_flash_state = not self._collision_flash_state
                    self._flash_collision_text()
        
        self.ctx["last_tick"] = now
        
        # --- 新增: SYSTEM_READY 延迟切换（从 pump 回调移到 tick，避免阻塞 pump）---
        if self._needs_switch_to_normal and self.ctx["display_mode"] == "boot":
            self._switch_to_normal()
            self._needs_switch_to_normal = False
        
        # 报警画面延迟渲染（从回调移到tick，避免阻塞EventBus）
        if self.ctx["display_mode"] == "alarm" and self._alarm_needs_render:
            self._render_alarm_screen()
            self._alarm_needs_render = False
        
        # 报警取消后清屏并重置导航渲染缓存
        if self._needs_clear and self.ctx["display_mode"] == "normal" and self.lcd_driver:
            try:
                self.lcd_driver.clear()
                self._rendered_nav_text = None
                self._rendered_nav_action = None
            except Exception as e:
                self.ctx["err_count"] += 1
                print("[{}] 报警取消清屏失败: {}".format(self.name, e))
            self._needs_clear = False
        
        # 导航到达/取消 10s 自动消隐检测
        if self._nav_expire_time > 0 and self.ctx["display_mode"] == "normal":
            if time.ticks_diff(now, self._nav_expire_time) >= 0:
                self._nav_text = ""
                self._nav_action = ""
                self._rendered_nav_text = None
                self._rendered_nav_action = None
                self._nav_expire_time = 0
                if self.lcd_driver and hasattr(self.lcd_driver, 'show_nav_line'):
                    try:
                        self.lcd_driver.show_nav_line(0, 104, "", bg=0x0000)
                    except Exception:
                        pass
        
        # 非 ACTIVE 模式跳过正常画面渲染
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return
        
        # 脏标志检查
        if self._dirty and self.ctx["display_mode"] == "normal":
            elapsed = time.ticks_diff(now, self._last_render_time)
            if elapsed >= self._min_render_interval:
                self._render_normal_screen()
                self._dirty = False
                self._last_render_time = now
    
    # ==================== 图片加载 ====================
    
    def _load_images(self):
        """加载所有图片数据（init时顺序加载）
        
        note 三个图片文件使用 bytes.fromhex() 紧凑格式：
        - images2.py: ~20KB bytes（洛天依100x100），峰值临时堆~59KB
        - alarm_icon.py: ~4.6KB bytes（⚠️等腰三角形48x48），峰值临时堆~27KB
        - boot_text.py: ~6.4KB bytes（中文文字条160x20），峰值临时堆~19KB
        加载顺序：images2(大) → alarm_icon(小) → boot_text(小)
        boot后释放洛天依+文字条(~26KB)，仅保留alarm_icon(~4.6KB)常驻。
        """
        # 1. 加载洛天依头像（开机时必须使用）
        try:
            from images2 import LUOTIANYI_ICON_100x100
            self.luotianyi_icon_data = LUOTIANYI_ICON_100x100
            self._data["luotianyi_loaded"] = True
            print("[{}] 洛天依头像加载成功 (100x100)".format(self.name))
        except ImportError as e:
            print("[{}] 洛天依头像加载失败: {}".format(self.name, e))
            self.luotianyi_icon_data = None
            self._data["luotianyi_loaded"] = False
        except Exception as e:
            print("[{}] 洛天依头像数据异常: {}".format(self.name, e))
            self.luotianyi_icon_data = None
            self._data["luotianyi_loaded"] = False
        
        # 2. 加载报警预警图标（常驻，报警时使用）
        try:
            from alarm_icon import ALARM_WARNING_ICON_48x48
            self.alarm_warning_icon_data = ALARM_WARNING_ICON_48x48
            self._data["alarm_icon_loaded"] = True
            print("[{}] 报警预警图标加载成功 (48x48)".format(self.name))
        except ImportError as e:
            print("[{}] 报警预警图标加载失败: {}".format(self.name, e))
            self.alarm_warning_icon_data = None
            self._data["alarm_icon_loaded"] = False
        except Exception as e:
            print("[{}] 报警预警图标数据异常: {}".format(self.name, e))
            self.alarm_warning_icon_data = None
            self._data["alarm_icon_loaded"] = False
        
        # 3. 加载开机中文文字条（boot后释放）
        try:
            from boot_text import BOOT_TEXT_160x20
            self.boot_text_data = BOOT_TEXT_160x20
            self._data["boot_text_loaded"] = True
            print("[{}] 开机文字条加载成功 (160x20)".format(self.name))
        except ImportError as e:
            print("[{}] 开机文字条加载失败: {}".format(self.name, e))
            self.boot_text_data = None
            self._data["boot_text_loaded"] = False
        except Exception as e:
            print("[{}] 开机文字条数据异常: {}".format(self.name, e))
            self.boot_text_data = None
            self._data["boot_text_loaded"] = False
    
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
    
    # ==================== 开机画面 ====================
    
    def _show_boot_screen(self):
        """显示开机画面：洛天依头像图片 + 中文文字条图片
        
        note 中文文字已预渲染为RGB565图片像素数据，不依赖show_string()字体。
        开机画面持续显示，直到 EVENT_SYSTEM_READY 触发切换到正常画面。
        note TTS 欢迎语延迟到 SYSTEM_READY 后播报（boot 时 audio_driver 尚未 init）
        """
        if not self.lcd_driver:
            print("[{}] LCD驱动未注入，跳过开机画面".format(self.name))
            return
        
        self.ctx["is_busy"] = True
        try:
            self.lcd_driver.clear()
            
            # 显示洛天依头像（100x100图片）
            if self._data["luotianyi_loaded"] and self.luotianyi_icon_data:
                if self._validate_image_data(
                    self.luotianyi_icon_data,
                    self.cfg["luotianyi_width"],
                    self.cfg["luotianyi_height"]
                ):
                    self.lcd_driver.show_image(
                        self.cfg["luotianyi_x"],
                        self.cfg["luotianyi_y"],
                        self.cfg["luotianyi_width"],
                        self.cfg["luotianyi_height"],
                        self.luotianyi_icon_data
                    )
                    print("[{}] 洛天依头像显示成功".format(self.name))
            
            # 显示"队伍：锦依卫队"中文文字条（160x20预渲染图片）
            if self._data["boot_text_loaded"] and self.boot_text_data:
                if self._validate_image_data(
                    self.boot_text_data,
                    self.cfg["boot_text_width"],
                    self.cfg["boot_text_height"]
                ):
                    self.lcd_driver.show_image(
                        self.cfg["boot_text_x"],
                        self.cfg["boot_text_y"],
                        self.cfg["boot_text_width"],
                        self.cfg["boot_text_height"],
                        self.boot_text_data
                    )
                    print("[{}] 开机文字条显示成功".format(self.name))
            
            # 背光
            if hasattr(self.lcd_driver, 'set_backlight'):
                self.lcd_driver.set_backlight(self.cfg["backlight_boot"])
                self.ctx["current_backlight"] = self.cfg["backlight_boot"]
            
            # TTS 欢迎语延迟到 SYSTEM_READY 后播报（boot 时 audio_driver 尚未 init）
            self.ctx["display_mode"] = "boot"
            self.ctx["boot_start_time"] = time.ticks_ms()
            print("[{}] 开机画面显示完成（洛天依主题，等待系统就绪）".format(self.name))
            
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 开机画面显示异常: {}".format(self.name, e))
        finally:
            self.ctx["is_busy"] = False
    
    def _on_system_ready(self, payload):
        """系统就绪回调：补发 TTS 欢迎语 + 切换到正常骑行画面
        
        note 替代原来的固定 boot_display_ms 定时器。
        EVENT_SYSTEM_READY 由 main.py 在所有模块 init() 完成后发布。
        note TTS 在 boot 阶段延迟（audio_driver 尚未 init），此处补发。
        """
        if not self.ctx["is_init"]:
            return
        if self.ctx["display_mode"] != "boot":
            return
        
        # 补发 TTS 欢迎语（此时 audio_driver 已 init）
        if self.event_bus:
            self.event_bus.publish(EVENT_TTS_REQUEST, {
                "text": self.cfg["tts_welcome"],
                "priority": PRIORITY_NAV,
            })
            print("[{}] TTS播报(延迟): {}".format(self.name, self.cfg['tts_welcome']))
        
        print("[{}] 收到系统就绪事件，延迟切换到正常画面".format(self.name))
        self._needs_switch_to_normal = True
    
    def _switch_to_normal(self):
        """切换到正常骑行画面"""
        if not self.lcd_driver:
            return
        self.ctx["is_busy"] = True
        try:
            self.lcd_driver.clear()
            self._rendered_nav_text = None
            self._rendered_nav_action = None
            self.ctx["display_mode"] = "normal"
            self.ctx["boot_displayed"] = True
            
            # 背光恢复
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
    
    # ==================== SOS 背光闪烁 ====================
    
    def _tick_sos_flash(self, now):
        """SOS 背光闪烁 tick 处理：仅切换背光亮度，不重绘文字 (<1ms)"""
        if self.ctx["is_busy"]:
            return
        
        if time.ticks_diff(now, self._last_flash_tick) < self.cfg["sos_flash_interval_ms"]:
            return
        
        if not self.lcd_driver or not hasattr(self.lcd_driver, 'set_backlight'):
            return
        
        self._sos_flash_state = not self._sos_flash_state
        self._last_flash_tick = now
        
        if self._sos_flash_state:
            self.lcd_driver.set_backlight(self.cfg["sos_flash_high"])
        else:
            self.lcd_driver.set_backlight(self.cfg["sos_flash_low"])
    
    # ==================== 正常画面 ====================
    
    def _format_temperature(self, temp):
        if temp is None:
            return "T:--.-C"
        if not isinstance(temp, (int, float)):
            return "T:--.-C"
        if temp < -40 or temp > 85:
            return "T:--.-C"
        return "T:{:.1f}C".format(temp)
    
    def _format_humidity(self, humid):
        if humid is None:
            return "H:--%"
        if not isinstance(humid, (int, float)):
            return "H:--%"
        if humid < 0 or humid > 100:
            return "H:--%"
        return "H:{:.0f}%".format(humid)
    
    def _format_location(self, lat, lon):
        if lat is None or lon is None:
            return "Lat:--.-- Lon:--.--"
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return "Lat:--.-- Lon:--.--"
        if lat < -90 or lat > 90 or lon < -180 or lon > 180:
            return "Lat:--.-- Lon:--.--"
        return "Lat:{:.2f} Lon:{:.2f}".format(lat, lon)
    
    def _format_speed(self, speed):
        if speed is None:
            return "V:--.-km/h"
        if not isinstance(speed, (int, float)):
            return "V:--.-km/h"
        if speed < 0 or speed > 200:
            return "V:--.-km/h"
        return "V:{:.1f}km/h".format(speed)
    
    def _render_normal_screen(self):
        """渲染正常骑行画面：英文显示温湿度、定位、速度数据（font=8）"""
        if not self.lcd_driver:
            return
        if self.ctx["display_mode"] != "normal":
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
                
                # 恢复导航高亮卡片（全宽高对比底栏，无频闪防抖缓存）
                if hasattr(self.lcd_driver, 'show_nav_line'):
                    if self._nav_text:
                        if (self._nav_text != self._rendered_nav_text or 
                            self._nav_action != self._rendered_nav_action):
                            try:
                                fg, bg = self._get_nav_colors(self._nav_action)
                                self.lcd_driver.show_nav_line(0, 104, self._nav_text, fg=fg, bg=bg)
                                self._rendered_nav_text = self._nav_text
                                self._rendered_nav_action = self._nav_action
                            except Exception as e:
                                print("[{}] 绘制导航卡片失败: {}".format(self.name, e))
                    else:
                        if self._rendered_nav_text is not None:
                            try:
                                self.lcd_driver.show_nav_line(0, 104, "", bg=0x0000)
                                self._rendered_nav_text = None
                                self._rendered_nav_action = None
                            except Exception:
                                pass
        
        except Exception as e:
            print("[{}] 正常画面渲染失败: {}".format(self.name, e))

    def _get_nav_colors(self, action):
        """根据导航动作返回 (fg, bg) 高对比色彩搭配"""
        if not self.lcd_driver or not hasattr(self.lcd_driver, 'lcd') or not self.lcd_driver.lcd:
            return 0x07E0, 0x0000
        lcd = self.lcd_driver.lcd

        if action in ("left", "slight_left"):
            return lcd.BLACK, lcd.GREEN       # 亮绿底 + 黑字
        elif action in ("right", "slight_right"):
            return lcd.BLACK, lcd.YELLOW      # 亮黄底 + 黑字
        elif action == "straight":
            return lcd.WHITE, lcd.BLUE        # 蓝底 + 白字
        elif action == "uturn":
            return lcd.WHITE, lcd.RED         # 红底 + 白字
        elif action == "arrive":
            cyan = getattr(lcd, 'CYAN', 0x07FF)
            return lcd.BLACK, cyan            # 青底 + 黑字
        elif action == "cancel":
            return lcd.WHITE, 0x4208          # 暗灰底 + 白字
        else:
            return lcd.BLACK, lcd.GREEN
    
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
    
    # ==================== 报警画面（差异化，英文） ====================
    
    def _show_collision_screen(self, level):
        """碰撞报警画面：⚠️图标居中 + CRASH! + Lv + 经纬度 + 提示
        
        画面布局（160x128，font=8 ASCII）：
            第0-11行: Lat经纬度（绿色，左侧）
            第12-27行: Lon经纬度（绿色，左侧）
            第0-47行: ⚠️ 等腰三角形图标居中（48x48, x=56）
            第52-67行: CRASH!（红色，居中x=56）
            第68-83行: Lv:X（黄色，居中x=64）
            第84-99行: Check Safety（白色，居中x=32）
            第100-115行: Cancel in 30s（灰色0x8410，居中x=24）
        """
        if not self.lcd_driver or not self.lcd_driver.lcd:
            return
        
        lcd = self.lcd_driver.lcd
        
        # 经纬度（顶部，font=8，左侧）
        lat = self._data.get("lat")
        lon = self._data.get("lon")
        if lat is not None and lon is not None:
            lcd.show_string(0, 0, "Lat:{:.2f}".format(lat), lcd.GREEN, lcd.BLACK)
            lcd.show_string(0, 12, "Lon:{:.2f}".format(lon), lcd.GREEN, lcd.BLACK)
        else:
            lcd.show_string(0, 0, "Lat:--.--", lcd.GREEN, lcd.BLACK)
            lcd.show_string(0, 12, "Lon:--.--", lcd.GREEN, lcd.BLACK)
        
        # ⚠️ 等腰三角形+感叹号图标居中显示
        if self._data["alarm_icon_loaded"] and self.alarm_warning_icon_data:
            if self._validate_image_data(
                self.alarm_warning_icon_data,
                self.cfg["alarm_icon_width"],
                self.cfg["alarm_icon_height"]
            ):
                self.lcd_driver.show_image(
                    self.cfg["alarm_icon_x"],
                    self.cfg["alarm_icon_y"],
                    self.cfg["alarm_icon_width"],
                    self.cfg["alarm_icon_height"],
                    self.alarm_warning_icon_data
                )
        
        # CRASH!（红色，font=8，双行偏移1px加粗）
        # "CRASH!" = 6×8=48px, 居中 x=(160-48)/2=56
        lcd.show_string(56, 52, "CRASH!", lcd.RED, lcd.BLACK)
        lcd.show_string(56, 53, "CRASH!", lcd.RED, lcd.BLACK)
        
        # Lv:X（黄色，font=8）
        # "Lv:X" = 4×8=32px, 居中 x=(160-32)/2=64
        lcd.show_string(64, 68, "Lv:{}".format(level), lcd.YELLOW, lcd.BLACK)
        
        # Check Safety（白色，font=8）
        # "Check Safety" = 12×8=96px, 居中 x=(160-96)/2=32
        lcd.show_string(32, 84, "Check Safety", lcd.WHITE, lcd.BLACK)
        
        # Cancel in 30s（灰色0x8410，font=8）
        # "Cancel in 30s" = 14×8=112px, 居中 x=(160-112)/2=24
        lcd.show_string(24, 100, "Cancel in 30s", 0x8410, lcd.BLACK)
        
        lcd.flush()
    
    def _show_sos_screen(self):
        """SOS 报警画面：⚠️图标居中 + EMERGENCY! + SOS + 经纬度 + 提示
        note 画面只绘制一次，后续 tick 仅切换背光亮度（不重绘，<1ms）
        
        画面布局（160x128，font=8 ASCII）：
            第0-11行: Lat经纬度（绿色，左侧）
            第12-27行: Lon经纬度（绿色，左侧）
            第0-47行: ⚠️ 等腰三角形图标居中（48x48, x=56）
            第52-67行: EMERGENCY!（红色，居中x=40）
            第68-83行: SOS（红色，居中x=68）
            第84-99行: Help Sent（黄色，居中x=36）
            第100-115行: Press to Cancel（灰色0x8410，居中x=16）
        """
        if not self.lcd_driver or not self.lcd_driver.lcd:
            return
        
        lcd = self.lcd_driver.lcd
        
        # 经纬度（顶部，font=8）
        lat = self._data.get("lat")
        lon = self._data.get("lon")
        if lat is not None and lon is not None:
            lcd.show_string(0, 0, "Lat:{:.2f}".format(lat), lcd.GREEN, lcd.BLACK)
            lcd.show_string(0, 12, "Lon:{:.2f}".format(lon), lcd.GREEN, lcd.BLACK)
        else:
            lcd.show_string(0, 0, "Lat:--.--", lcd.GREEN, lcd.BLACK)
            lcd.show_string(0, 12, "Lon:--.--", lcd.GREEN, lcd.BLACK)
        
        # ⚠️ 等腰三角形+感叹号图标居中显示
        if self._data["alarm_icon_loaded"] and self.alarm_warning_icon_data:
            if self._validate_image_data(
                self.alarm_warning_icon_data,
                self.cfg["alarm_icon_width"],
                self.cfg["alarm_icon_height"]
            ):
                self.lcd_driver.show_image(
                    self.cfg["alarm_icon_x"],
                    self.cfg["alarm_icon_y"],
                    self.cfg["alarm_icon_width"],
                    self.cfg["alarm_icon_height"],
                    self.alarm_warning_icon_data
                )
        
        # EMERGENCY!（红色，双行偏移1px加粗）
        # "EMERGENCY!" = 10×8=80px, 居中 x=(160-80)/2=40
        lcd.show_string(40, 52, "EMERGENCY!", lcd.RED, lcd.BLACK)
        lcd.show_string(40, 53, "EMERGENCY!", lcd.RED, lcd.BLACK)
        
        # SOS（红色，font=8）
        # "SOS" = 3×8=24px, 居中 x=(160-24)/2=68
        lcd.show_string(68, 68, "SOS", lcd.RED, lcd.BLACK)
        
        # Help Sent（黄色，font=8）
        # "Help Sent" = 9×8=72px, 居中 x=(160-72)/2=44
        lcd.show_string(44, 84, "Help Sent", lcd.YELLOW, lcd.BLACK)
        
        # Press to Cancel（灰色0x8410，font=8）
        # "Press to Cancel" = 16×8=128px, 居中 x=(160-128)/2=16
        lcd.show_string(16, 100, "Press to Cancel", 0x8410, lcd.BLACK)
        
        lcd.flush()
        
        # 初始化背光闪烁状态
        self._sos_flash_state = False
        self._last_flash_tick = time.ticks_ms()
    
    # ==================== 背光调节 ====================
    
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
    
    # ==================== 事件回调 ====================
    
    def _on_temp_humid_ready(self, payload):
        """温湿度数据回调：更新数据 + 设脏标志"""
        if not self.ctx["is_init"]:
            return
        temp = payload.get("temp")
        humid = payload.get("humid")
        if temp is not None:
            self._data["temp"] = temp
        if humid is not None:
            self._data["humid"] = humid
        self._dirty = True
    
    def _on_gnss_ready(self, payload):
        """GNSS数据回调：更新数据 + 设脏标志"""
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
        self._dirty = True
    
    def _on_light_ready(self, payload):
        """光照数据回调：自动调节背光（报警期间跳过）"""
        if not self.ctx["is_init"]:
            return
        light_intensity = payload.get("light_intensity", payload.get("value"))
        if light_intensity is None:
            return
        if not isinstance(light_intensity, (int, float)) or light_intensity < 0:
            return
        
        self._data["light_intensity"] = light_intensity
        
        # 报警期间跳过自动背光调节
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
        """报警触发回调：零阻塞，只设状态，LCD绘制延迟到tick()
        
        处理逻辑：
        - stealth: LCD保持不变，不改变任何显示
        - collision: 延迟渲染碰撞预警画面 + 背光100% + 后续闪烁
        - sos: 延迟渲染紧急求救画面 + 背光100% + 后续闪烁
        
        零阻塞原则：
        - 回调只设置状态和脏标志，不执行任何LCD操作
        - 所有LCD绘制延迟到tick()中执行，避免阻塞EventBus.pump()
        """
        if not self.ctx["is_init"]:
            return
        
        alarm_type = payload.get("alarm_type", "unknown")
        level = payload.get("level", 1)
        
        # 静默报警：LCD保持不变
        if alarm_type == "stealth":
            print("[{}] stealth报警: LCD保持不变".format(self.name))
            self.ctx["is_alarm_active"] = True
            self.ctx["alarm_type"] = "stealth"
            return
        
        now = time.ticks_ms()
        self.ctx["is_alarm_active"] = True
        self.ctx["alarm_type"] = alarm_type
        self.ctx["alarm_level"] = level
        self.ctx["alarm_start"] = now
        
        # 报警优先：设置 LCD alarm_override
        if self.lcd_driver:
            self.lcd_driver.ctx["alarm_override"] = True
        
        # 背光100%（<1ms，不阻塞）
        if self.lcd_driver and hasattr(self.lcd_driver, 'set_backlight'):
            try:
                self.lcd_driver.set_backlight(self.cfg["backlight_alarm"])
                self.ctx["current_backlight"] = self.cfg["backlight_alarm"]
            except Exception as e:
                print("[{}] 报警背光设置失败: {}".format(self.name, e))
        
        # 设置延迟渲染标志
        self.ctx["display_mode"] = "alarm"
        self._alarm_needs_render = True
        self._collision_flash_state = True
        self._collision_flash_last_tick = now
        self._needs_clear = False
        
        print("[{}] 报警触发({}), level={}, 画面延迟渲染".format(self.name, alarm_type, level))
    
    def _on_alarm_canceled(self, payload):
        """报警取消回调：零阻塞，状态恢复延迟到tick()
        
        清除 LCDDriver.ctx["alarm_override"] = False → 电源模式恢复控制背光
        """
        if not self.ctx["is_init"]:
            return
        
        self.ctx["is_alarm_active"] = False
        
        # 清除报警覆盖标志
        if self.lcd_driver:
            self.lcd_driver.ctx["alarm_override"] = False
        
        # 背光恢复（<1ms，不阻塞）
        if self.lcd_driver and hasattr(self.lcd_driver, 'set_backlight'):
            try:
                backlight = self.cfg["backlight_normal"]
                if self._data["light_intensity"] is not None:
                    backlight = self._get_backlight_by_light(self._data["light_intensity"])
                self.lcd_driver.set_backlight(backlight)
                self.ctx["current_backlight"] = backlight
            except Exception as e:
                print("[{}] 报警取消背光恢复失败: {}".format(self.name, e))
        
        # 状态恢复，LCD清屏和画面渲染延迟到tick()
        self.ctx["display_mode"] = "normal"
        self.ctx["alarm_type"] = ""
        self.ctx["alarm_level"] = 0
        self.ctx["alarm_start"] = 0
        self._dirty = True
        self._alarm_needs_render = False
        self._needs_clear = True
        
        print("[{}] 报警取消，恢复正常画面".format(self.name))
    
    def _on_power_state_change(self, payload):
        """功耗状态变化回调 — 报警优先覆盖
        
        报警优先原则：
        - 报警期间进入休眠：不清屏、不关背光
        - 报警期间唤醒恢复：重新渲染报警画面
        - 非报警期间：正常省电逻辑（清屏+关背光）
        """
        if not self.ctx["is_init"]:
            return
        old_state = self.ctx["power_state"]
        new_state = payload.get("power_state", POWER_STATE_ACTIVE)
        self.ctx["power_state"] = new_state
        
        if new_state != POWER_STATE_ACTIVE:
            if self.ctx["is_alarm_active"]:
                # 报警优先：不清屏、不关背光
                print("[{}] 报警期间进入休眠: 保持报警画面(alarm_override=True)".format(self.name))
            else:
                # 正常省电逻辑
                if self.lcd_driver:
                    self.lcd_driver.clear()
                if self.lcd_driver and hasattr(self.lcd_driver, 'set_backlight'):
                    self.lcd_driver.set_backlight(0)
                    self.ctx["current_backlight"] = 0
                print("[{}] 进入休眠，清屏+关闭背光".format(self.name))
        
        elif old_state != POWER_STATE_ACTIVE:
            # 唤醒恢复
            if self.ctx["is_alarm_active"]:
                # 报警期间唤醒：延迟渲染报警画面
                self._alarm_needs_render = True
                self.ctx["display_mode"] = "alarm"
                if self.lcd_driver and hasattr(self.lcd_driver, 'set_backlight'):
                    self.lcd_driver.set_backlight(self.cfg["backlight_alarm"])
                    self.ctx["current_backlight"] = self.cfg["backlight_alarm"]
                print("[{}] 报警期间唤醒: 延迟渲染报警画面".format(self.name))
            else:
                # 正常唤醒
                if self.lcd_driver and hasattr(self.lcd_driver, 'set_backlight'):
                    backlight = self.ctx.get("current_backlight", self.cfg["backlight_normal"])
                    if backlight == 0:
                        backlight = self.cfg["backlight_normal"]
                    self.lcd_driver.set_backlight(backlight)
                    self.ctx["current_backlight"] = backlight
                self._dirty = True
                print("[{}] 唤醒，恢复背光+正常画面".format(self.name))
    
    def _on_config_update(self, payload):
        """配置更新回调"""
        if payload.get("target") == self.name:
            if "backlight_normal" in payload:
                self.cfg["backlight_normal"] = int(payload["backlight_normal"])
        if "power_state" in payload:
            self.ctx["power_state"] = payload["power_state"]
    
    def _on_nav_display(self, payload):
        """导航显示内容变更回调"""
        self._nav_text = payload.get("text", "")
        self._nav_action = payload.get("action", "")
        if self._nav_action in ("arrive", "cancel"):
            self._nav_expire_time = time.ticks_ms() + 10000  # 10秒后消隐
        else:
            self._nav_expire_time = 0
        self._dirty = True
    
    # ==================== 数据接口 ====================
    
    def get_data(self):
        """获取当前显示数据"""
        return {
            "temp": self._data["temp"],
            "humid": self._data["humid"],
            "lat": self._data["lat"],
            "lon": self._data["lon"],
            "speed": self._data["speed"],
            "light_intensity": self._data["light_intensity"],
            "luotianyi_loaded": self._data["luotianyi_loaded"],
            "alarm_icon_loaded": self._data["alarm_icon_loaded"],
            "boot_text_loaded": self._data["boot_text_loaded"],
            "timestamp": time.ticks_ms()
        }
    
    def get_status(self):
        """获取模块运行状态"""
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "display_mode": self.ctx["display_mode"],
            "is_alarm_active": self.ctx["is_alarm_active"],
            "alarm_type": self.ctx["alarm_type"],
            "alarm_level": self.ctx["alarm_level"],
            "boot_displayed": self.ctx["boot_displayed"],
            "power_state": self.ctx["power_state"],
            "current_backlight": self.ctx["current_backlight"],
            "err_count": self.ctx["err_count"]
        }
    
    # ==================== 报警画面渲染（延迟执行） ====================
    
    def _render_alarm_screen(self):
        """渲染报警画面（延迟到tick执行，避免阻塞EventBus回调）"""
        if not self.lcd_driver:
            return
        self.ctx["is_busy"] = True
        try:
            self.lcd_driver.clear()
            alarm_type = self.ctx["alarm_type"]
            level = self.ctx["alarm_level"]
            if alarm_type == "sos":
                self._show_sos_screen()
            elif alarm_type == "collision":
                self._show_collision_screen(level)
            else:
                self._show_collision_screen(level)
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[{}] 报警画面渲染失败: {}".format(self.name, e))
        finally:
            self.ctx["is_busy"] = False
    
    def _flash_collision_text(self):
        """碰撞报警闪烁：翻转⚠️图标+CRASH!文字
        
        闪烁策略：隐藏时（黑色）填充覆盖图标和文字区域，
        显示时（红色）重新绘制图标和红色文字
        
        note 使用 font=8 显示英文ASCII文字
        """
        if not self.lcd_driver or not self.lcd_driver.lcd:
            return
        try:
            lcd = self.lcd_driver.lcd
            if self._collision_flash_state:
                # 显示状态：重绘⚠️图标 + 红色CRASH!文字
                if self._data["alarm_icon_loaded"] and self.alarm_warning_icon_data:
                    self.lcd_driver.show_image(
                        self.cfg["alarm_icon_x"],
                        self.cfg["alarm_icon_y"],
                        self.cfg["alarm_icon_width"],
                        self.cfg["alarm_icon_height"],
                        self.alarm_warning_icon_data
                    )
                # 红色CRASH!文字（双行偏移1px加粗）
                lcd.show_string(56, 52, "CRASH!", lcd.RED, lcd.BLACK)
                lcd.show_string(56, 53, "CRASH!", lcd.RED, lcd.BLACK)
            else:
                # 隐藏状态：用黑色填充覆盖图标和文字区域（y=0~68）
                lcd.fill_rectangle(0, 0, 160, 68, lcd.BLACK)
            lcd.flush()
        except Exception as e:
            print("[{}] 碰撞闪烁失败: {}".format(self.name, e))
