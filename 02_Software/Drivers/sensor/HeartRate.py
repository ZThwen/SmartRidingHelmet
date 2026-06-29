"""
brief 心率血氧传感器驱动 (MKS SPO2-ZS-BLE)
note 严格遵循四元组架构规范，适配UART5通信
      Device层纯硬件控制，不包含业务逻辑
      硬件：UART5 (TX=PC12, RX=PD2)
      核心功能：读取心率、血氧数据，发布事件
      
数据包格式（50字节）：
- 第1字节：0xFF（数据包头）
- 第2-40字节：波形数据（不使用）
- 第41字节：心率（bpm）
- 第42字节：血氧（%）
- 第43字节：待定
- 第46字节：呼吸率
- 第47字节：RR间期
- 第48字节：RMSSD（疲劳值）

重要说明：
- 模块默认工作在SPO2模式（红/红外光）
- SPO2模式下可同时测量心率和血氧
- 第41字节 = 心率，第42字节 = 血氧
"""
import time
from machine import UART

from core.Base_Module import BaseModule
from core.config import (
    EVENT_HEARTRATE_READY, EVENT_SENSOR_ERROR, EVENT_CONFIG_UPDATE,
    EVENT_POWER_STATE_CHANGE, POWER_STATE_ACTIVE, POWER_STATE_SUSPENDED,
    POWER_STATE_EMERGENCY,
    HEARTRATE_SAMPLE_MS, HEARTRATE_SUSPENDED_MS, HEARTRATE_WARMUP_MS,
    HEARTRATE_UART_ID, HEARTRATE_UART_BAUDRATE,
    HEARTRATE_DATA_LEN, HEARTRATE_HEADER,
    HEARTRATE_CMD_START, HEARTRATE_CMD_STOP,
    HEARTRATE_HR_MIN, HEARTRATE_HR_MAX,
    HEARTRATE_SPO2_MIN, HEARTRATE_SPO2_MAX,
)


class HeartRateDriver(BaseModule):

    def __init__(self, event_bus=None):
        """
        brief 初始化心率血氧驱动实例
        param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus
        self.name = "heartrate"

        self.cfg = {
            "uart_id": HEARTRATE_UART_ID,
            "baudrate": HEARTRATE_UART_BAUDRATE,
            "sample_ms": HEARTRATE_SAMPLE_MS,
            "suspended_ms": HEARTRATE_SUSPENDED_MS,
            "data_len": HEARTRATE_DATA_LEN,
            "header": HEARTRATE_HEADER,
            "cmd_start": HEARTRATE_CMD_START,
            "cmd_stop": HEARTRATE_CMD_STOP,
            "max_retry": 3,
            "warmup_ms": HEARTRATE_WARMUP_MS,
            "hr_min": HEARTRATE_HR_MIN,
            "hr_max": HEARTRATE_HR_MAX,
            "spo2_min": HEARTRATE_SPO2_MIN,
            "spo2_max": HEARTRATE_SPO2_MAX,
        }

        self.ctx = {
            "is_init": False,
            "is_busy": False,
            "last_tick": 0,
            "err_count": 0,
            "power_state": POWER_STATE_ACTIVE,
            "is_collecting": False,
            "start_time": 0,
            "packet_count": 0,
        }

        self._data = {
            "heart_rate": 0,
            "spo2": 0,
            "valid": False,
        }

        self.uart = None

    def init(self):
        """
        brief 初始化模块：硬件配置 + 订阅事件 + 发送采集开指令
        note 失败时直接 raise，main.py会捕获并停止启动
        """
        try:
            print("[%s] Step1: 初始化串口..." % self.name)
            self.uart = UART(
                self.cfg["uart_id"],
                self.cfg["baudrate"]
            )
            print("[%s] OK: UART%d 初始化成功，波特率=%d" % (
                self.name, self.cfg["uart_id"], self.cfg["baudrate"]
            ))

            print("[%s] Step2: 清空缓冲区..." % self.name)
            while self.uart.any() > 0:
                self.uart.read(self.uart.any())

            print("[%s] Step3: 发送采集开指令 0x%02X..." % (self.name, self.cfg["cmd_start"]))
            self._send_cmd(self.cfg["cmd_start"])

            print("[%s] Step4: 检查模块响应..." % self.name)
            if self.uart.any() >= self.cfg["data_len"]:
                print("[%s] OK: 模块已响应，收到 %d 字节" % (self.name, self.uart.any()))
            else:
                print("[%s] WARN: 模块未响应（%d 字节），请检查硬件连接" % (self.name, self.uart.any()))

            self.ctx["is_collecting"] = True
            self.ctx["start_time"] = time.ticks_ms()

            if self.event_bus:
                self.event_bus.subscribe(EVENT_POWER_STATE_CHANGE, self._on_config_update)

            self.ctx["is_init"] = True
            print("[%s] 初始化完成，预热%d秒..." % (self.name, self.cfg["warmup_ms"] // 1000))

        except Exception as e:
            print("[%s] FAIL init: %s" % (self.name, e))
            raise

    def tick(self):
        """
        brief 周期调度：读取串口数据 + 解析 + 发布事件
        note 主循环每轮调用，必须快速返回（<5ms）
        """
        if not self.ctx["is_init"]:
            return

        if self.ctx["power_state"] == POWER_STATE_EMERGENCY:
            return

        if not self.ctx["is_collecting"]:
            return

        self.ctx["last_hb"] = time.ticks_ms()
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["sample_ms"]:
            return

        self.ctx["last_tick"] = now

        try:
            self._read_uart()
        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] tick err: %s" % (self.name, e))
            if self.ctx["err_count"] > 10:
                print("[%s] too many errors, stopping" % self.name)
                self.ctx["is_collecting"] = False

    def _read_uart(self):
        """
        brief 读取串口数据，解析数据包
        note 限制每次读取字节数 + 帧扫描上限，防止阻塞主循环
        """
        try:
            if not self.uart:
                return

            available = self.uart.any()
            if available < self.cfg["data_len"]:
                return

            self.ctx["is_busy"] = True

            # 限制读取量，防止阻塞（最多 200 字节 ≈ 4 帧）
            max_read = min(available, 200)
            buf = self.uart.read(max_read)
            if not buf:
                return

            # 扫描帧头，最多处理 4 帧
            frames_processed = 0
            for i in range(len(buf)):
                if frames_processed >= 4:
                    break
                if buf[i] == self.cfg["header"]:
                    # 检查是否有足够字节组成完整帧
                    if i + self.cfg["data_len"] <= len(buf):
                        frame = buf[i:i + self.cfg["data_len"]]
                        result = self._parse_packet(frame)
                        if result:
                            self._data["heart_rate"] = result["heart_rate"]
                            self._data["spo2"] = result["spo2"]
                            self._data["valid"] = True
                            self._data["timestamp"] = time.ticks_ms()
                            self.ctx["err_count"] = 0
                            self.ctx["packet_count"] += 1
                            if self.event_bus:
                                self.event_bus.publish(EVENT_HEARTRATE_READY, self.get_data())
                            frames_processed += 1

        except Exception as e:
            self.ctx["err_count"] += 1
            print("[%s] uart read err: %s" % (self.name, e))
        finally:
            self.ctx["is_busy"] = False

    def _parse_packet(self, data_bytes):
        """
        brief 解析50字节数据包，多重验证确保有效数据
        param data_bytes: 数据字节（bytes对象）
        return dict|None 解析结果 {"heart_rate", "spo2", "valid"} 或 None（无效帧）
        """
        # 检查 1: 长度必须正好等于配置长度
        if len(data_bytes) != self.cfg["data_len"]:
            return None

        # 检查 2: 帧头必须是配置头字节
        if data_bytes[0] != self.cfg["header"]:
            return None

        # 检查 3: 心率值范围验证
        raw_hr = data_bytes[40]
        if not (self.cfg["hr_min"] <= raw_hr <= self.cfg["hr_max"]):
            return None

        # 检查 4: 血氧值范围验证
        raw_spo2 = data_bytes[41]
        if not (self.cfg["spo2_min"] <= raw_spo2 <= self.cfg["spo2_max"]):
            return None

        # 检查 5: 预热期检查
        if not self._check_warmup():
            return None

        return {
            "heart_rate": raw_hr,
            "spo2": raw_spo2,
            "valid": True,
        }

    def _check_warmup(self):
        """
        brief 检查传感器预热是否完成
        return bool 预热完成返回True
        """
        elapsed = time.ticks_diff(time.ticks_ms(), self.ctx["start_time"])
        return elapsed >= self.cfg["warmup_ms"]

    def force_read(self):
        """
        brief 强制读取传感器（返回缓存数据，非阻塞）
        note tick() 每2秒更新缓存，此方法直接返回最新缓存值
        return dict 数据副本
        """
        return self.get_data()

    def start_collect(self):
        """
        brief 发送采集开指令
        note 供Service层调用
        """
        if not self.ctx["is_init"]:
            return

        self._send_cmd(self.cfg["cmd_start"])
        self.ctx["is_collecting"] = True
        self.ctx["start_time"] = time.ticks_ms()
        self.ctx["packet_count"] = 0
        self._data["valid"] = False
        print("[%s] start collect" % self.name)

    def stop_collect(self):
        """
        brief 发送采集关指令
        note 供Service层调用
        """
        if not self.ctx["is_init"]:
            return

        self._send_cmd(self.cfg["cmd_stop"])
        self.ctx["is_collecting"] = False
        print("[%s] stop collect" % self.name)

    def _send_cmd(self, cmd):
        """
        brief 发送指令到模块
        param cmd: 指令字节
        """
        try:
            self.uart.write(bytes([cmd]))
        except Exception as e:
            print("[%s] send cmd err: %s" % (self.name, e))

    def _on_config_update(self, payload):
        """
        brief 配置更新回调处理
        param payload: 配置事件负载
        """
        if payload.get("target") == self.name and "sample_ms" in payload:
            self.cfg["sample_ms"] = int(payload["sample_ms"])
            print("[%s] sample_ms update to %dms" % (self.name, self.cfg["sample_ms"]))

        if "power_state" in payload:
            old_state = self.ctx["power_state"]
            self.ctx["power_state"] = payload["power_state"]
            if payload["power_state"] == POWER_STATE_SUSPENDED:
                self.cfg["sample_ms"] = self.cfg["suspended_ms"]
            elif payload["power_state"] == POWER_STATE_EMERGENCY:
                if self.ctx["is_collecting"]:
                    self.stop_collect()
            elif payload["power_state"] == POWER_STATE_ACTIVE:
                self.cfg["sample_ms"] = HEARTRATE_SAMPLE_MS
                if not self.ctx["is_collecting"]:
                    self.start_collect()
            print("[%s] power: %s -> %s" % (self.name, old_state, payload["power_state"]))

    def get_data(self):
        """
        brief 获取当前心率血氧数据快照
        return dict 数据副本 {heart_rate, spo2, valid, timestamp}
        """
        return {
            "heart_rate": self._data["heart_rate"],
            "spo2": self._data["spo2"],
            "valid": self._data["valid"],
            "timestamp": time.ticks_ms(),
        }

    def get_status(self):
        """
        brief 查询模块运行状态快照
        return dict 运行上下文
        """
        return {
            "is_init": self.ctx["is_init"],
            "is_busy": self.ctx["is_busy"],
            "err_count": self.ctx["err_count"],
            "power_state": self.ctx["power_state"],
            "is_collecting": self.ctx["is_collecting"],
            "packet_count": self.ctx["packet_count"],
        }

    def deinit(self):
        """
        brief 反初始化：停止采集，释放串口资源
        """
        try:
            if self.ctx["is_collecting"]:
                self.stop_collect()

            if self.uart:
                self.uart.deinit()

            self.uart = None
            self.ctx["is_init"] = False
            print("[%s] deinit OK" % self.name)

        except Exception as e:
            print("[%s] deinit err: %s" % (self.name, e))
