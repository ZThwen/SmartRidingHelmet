"""
================================================================================
业务服务层开发模板 - 快速开发指南
================================================================================

适用场景：
- 数据处理服务（如：碰撞检测、数据聚合、阈值判断）
- 业务联动服务（如：报警联动、云端通信）
- 状态管理服务（如：功耗管理、状态机）

特点：
- 不直接操作硬件
- 通过订阅事件接收数据
- 执行业务逻辑（算法、判断、联动）
- 发布处理结果事件

使用方法：
1. 复制此模板到 Modules/ 目录
2. 重命名为具体服务名（如 collision_service.py、alarm_service.py）
3. 根据注释提示填写具体实现
4. 在 config.py 中定义事件常量
5. 在 main.py 中导入并添加到 modules 列表

================================================================================
"""

import time

from Base_Module import BaseModule
from config import EVENT_XXX_DATA, EVENT_XXX_RESULT, POWER_STATE_ACTIVE


class YourService(BaseModule):
    """
    服务说明：[一句话描述服务功能]
    
    例如：
    - 碰撞检测服务：订阅IMU数据，判断是否发生碰撞
    - 报警联动服务：订阅碰撞/SOS事件，触发报警动作
    - 云端通信服务：订阅传感器数据，上传到云端
    """
    
    def __init__(self, event_bus=None):
        """
        \brief 初始化服务实例
        \param event_bus: 事件总线实例引用
        """
        super().__init__()
        self.event_bus = event_bus  # 保存事件总线引用
        self.name = "your_service"  # 服务标识符（必须唯一）
        
        # ===================== 四元组：静态配置 =====================
        self.cfg = {
            # 业务参数
            "threshold": 2.5,         # 阈值（示例）
            "window_size": 10,        # 滑动窗口大小
            "check_interval_ms": 100, # 检查间隔
            
            # 重试参数
            "max_retry": 3,           # 最大重试次数
        }

        # ===================== 四元组：运行时上下文 =====================
        self.ctx = {
            "is_init": False,         # 初始化完成标志
            "last_tick": 0,           # 上次执行时间戳
            "power_state": POWER_STATE_ACTIVE,  # 功耗状态
            
            # 业务状态
            "data_buffer": [],        # 数据缓存（滑动窗口）
            "alarm_count": 0,         # 报警计数（示例）
        }

        # ===================== 四元组：当前数据 =====================
        self._data = {
            "result": None,           # 处理结果
            "status": "normal",       # 状态（normal/warning/alarm）
        }

    def init(self):
        """
        \brief 初始化服务：订阅事件 + 初始化业务状态
        
        实现步骤：
        1. 订阅数据事件（订阅需要处理的数据源）
        2. 初始化业务状态（算法参数、缓存等）
        3. 设置 is_init 标志
        """
        try:
            # ====== 1. 订阅数据事件 ======
            if self.event_bus:
                # 订阅传感器数据事件
                self.event_bus.subscribe(EVENT_XXX_DATA, self._on_data_received)
                # 订阅配置更新事件
                self.event_bus.subscribe("CONFIG_UPDATE", self._on_config_update)
            
            # ====== 2. 初始化业务状态 ======
            # 示例：初始化滑动窗口
            self.ctx["data_buffer"] = []
            
            # ====== 3. 设置初始化标志 ======
            self.ctx["is_init"] = True
            print(f"[{self.name}] ✓ 初始化完成")
            
        except Exception as e:
            print(f"[{self.name}] ✗ 初始化失败: {e}")
            raise

    def tick(self):
        """
        \brief 周期调度：执行业务逻辑
        
        实现步骤：
        1. 状态守卫（功耗模式检查）
        2. 时间片校验（检查间隔）
        3. 执行业务逻辑（数据聚合、状态判断等）
        4. 发布结果事件
        """
        # ====== 1. 状态守卫 ======
        if self.ctx["power_state"] != POWER_STATE_ACTIVE:
            return

        # ====== 2. 时间片校验 ======
        now = time.ticks_ms()
        if time.ticks_diff(now, self.ctx["last_tick"]) < self.cfg["check_interval_ms"]:
            return

        # ====== 3. 执行业务逻辑 ======
        try:
            # 示例：检查数据缓存是否满足条件
            if len(self.ctx["data_buffer"]) >= self.cfg["window_size"]:
                # 执行算法处理
                result = self._process_algorithm()
                
                # 更新内部数据
                self._data["result"] = result
                
                # ====== 4. 发布结果事件 ======
                if self.event_bus:
                    self.event_bus.publish(EVENT_XXX_RESULT, {
                        "result": result,
                        "source": self.name
                    })
            
        except Exception as e:
            print(f"[{self.name}] 处理异常: {e}")
        
        finally:
            self.ctx["last_tick"] = now

    # ==================== 事件回调 ====================
    def _on_data_received(self, payload):
        """
        \brief 数据接收回调（订阅传感器数据）
        \param payload: 数据事件负载
        
        示例负载：
        {
            "temp": 25.5,
            "humid": 60.2,
            "valid": True,
            "timestamp": 12345678
        }
        """
        # 数据校验
        if not payload.get("valid", False):
            return
        
        # 示例：将数据加入滑动窗口
        data_value = payload.get("value", 0)
        self.ctx["data_buffer"].append(data_value)
        
        # 保持窗口大小
        if len(self.ctx["data_buffer"]) > self.cfg["window_size"]:
            self.ctx["data_buffer"].pop(0)
        
        # 可选：立即判断并发布事件
        # if self._check_threshold(data_value):
        #     self.event_bus.publish(EVENT_ALARM, {...})

    def _on_config_update(self, payload):
        """
        \brief 配置更新回调
        \param payload: {"target": module_name, "key": value}
        """
        if payload.get("target") == self.name:
            if "threshold" in payload:
                self.cfg["threshold"] = float(payload["threshold"])
                print(f"[{self.name}] 阈值更新为 {self.cfg['threshold']}")

    # ==================== 业务逻辑 ====================
    def _process_algorithm(self):
        """
        \brief 执行业务算法（私有方法）
        \return 处理结果
        
        示例算法：
        - 碰撞检测：计算加速度总和，判断是否超过阈值
        - 数据聚合：计算平均值、最大值、最小值
        - 阈值判断：判断数据是否超过阈值
        """
        # 示例：计算平均值
        if not self.ctx["data_buffer"]:
            return None
        
        avg = sum(self.ctx["data_buffer"]) / len(self.ctx["data_buffer"])
        return avg
    
    def _check_threshold(self, value):
        """
        \brief 阈值判断（私有方法）
        \param value: 待判断值
        \return bool 是否超过阈值
        """
        return abs(value) > self.cfg["threshold"]

    # ==================== 辅助方法 ====================
    def get_data(self):
        """
        \brief 获取当前处理结果
        \return dict 数据副本
        """
        return {
            "result": self._data["result"],
            "status": self._data["status"],
            "timestamp": time.ticks_ms()
        }

    def get_status(self):
        """
        \brief 获取运行状态
        \return dict 状态快照
        """
        return {
            "is_init": self.ctx["is_init"],
            "power_state": self.ctx["power_state"],
            "buffer_size": len(self.ctx["data_buffer"])
        }


# ================================================================================
# 快速开发检查清单（业务服务层）
# ================================================================================
"""
□ 修改类名和 self.name
□ 在 config.py 中定义事件常量（EVENT_XXX_DATA、EVENT_XXX_RESULT）
□ 在 init() 中订阅数据事件
□ 在 _on_data_received() 中实现数据接收逻辑
□ 在 tick() 中实现周期性业务逻辑（如果有）
□ 在 _process_algorithm() 中实现核心算法
□ 根据需要发布结果事件
□ 在 main.py 中导入服务类
□ 在 main.py 的 modules 列表中添加实例
□ 测试验证功能正常
"""

# ================================================================================
# 业务服务示例
# ================================================================================
"""
【碰撞检测服务】
- 订阅：IMU数据事件（EVENT_IMU_READY）
- 处理：计算加速度总和，判断是否超过阈值
- 发布：碰撞事件（EVENT_COLLISION_DETECTED）

【报警联动服务】
- 订阅：碰撞事件（EVENT_COLLISION_DETECTED）、SOS按键事件（EVENT_SOS_PRESSED）
- 处理：触发本地报警（LED闪烁、蜂鸣器、播放报警音）
- 发布：报警事件（EVENT_ALARM_TRIGGERED）

【云端通信服务】
- 订阅：传感器数据事件（EVENT_TEMP_HUMID_READY、EVENT_IMU_READY等）
- 处理：打包数据，上传到云端
- 发布：上传结果事件（EVENT_DATA_UPLOAD_SUCCESS/FAILED）

【数据聚合服务】
- 订阅：多个传感器数据事件
- 处理：聚合数据（平均、最大、最小）
- 发布：聚合结果事件
"""

# ================================================================================
# 事件订阅示例
# ================================================================================
"""
【订阅单个事件】
self.event_bus.subscribe(EVENT_IMU_READY, self._on_imu_data)

【订阅多个事件】
self.event_bus.subscribe(EVENT_IMU_READY, self._on_imu_data)
self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid_data)
self.event_bus.subscribe(EVENT_SOS_PRESSED, self._on_sos_pressed)

【事件处理流程】
传感器模块 → 发布数据事件 → 服务订阅 → 接收数据 → 执行算法 → 发布结果事件
"""
