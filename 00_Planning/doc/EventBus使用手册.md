# EventBus API 使用手册

> 快速上手EventBus的订阅、发布和处理方法

---

## 1. 创建EventBus实例

### 1.1 基本创建

```python
from Event_Bus import EventBus

event_bus = EventBus()
```

### 1.2 开启调试模式

```python
event_bus = EventBus()
event_bus.debug = True  # 输出订阅日志
```

**调试输出示例**：

```
[订阅] TEMP_READY <- on_temp_ready
[订阅] COLLISION_DETECTED <- _on_collision
```

---

## 2. 订阅事件 - subscribe()

### 2.1 基本用法

```python
# 定义回调函数
def on_temp_ready(payload):
    print(f"温度: {payload['temp']}℃")

# 订阅事件
event_bus.subscribe("TEMP_READY", on_temp_ready)
```

### 2.2 使用类方法作为回调

```python
class AlarmService:
    def init(self, event_bus):
        # 订阅碰撞事件
        event_bus.subscribe("COLLISION_DETECTED", self._on_collision)
    
    def _on_collision(self, payload):
        self.start_alarm()

# 使用
alarm = AlarmService()
alarm.init(event_bus)
```

### 2.3 一个事件多个订阅者

```python
# 报警模块订阅碰撞事件
def on_collision_alarm(payload):
    start_alarm()

# 云端模块订阅碰撞事件
def on_collision_cloud(payload):
    send_to_cloud()

# 两个订阅者订阅同一事件
event_bus.subscribe("COLLISION_DETECTED", on_collision_alarm)
event_bus.subscribe("COLLISION_DETECTED", on_collision_cloud)
```

### 2.4 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `event_name` | 字符串 | 事件名称，建议使用config中的常量 |
| `callback` | 函数/方法 | 回调函数，接收一个参数payload |

**回调函数签名**：

```python
def callback(payload):
    """
    payload: dict类型，包含事件数据
    - payload["timestamp"]: 自动补充的时间戳
    - payload["source"]: 事件来源（需发布时设置）
    - 其他字段：发布时自定义
    """
    pass
```

---

## 3. 发布事件 - publish()

### 3.1 发布字典数据

```python
event_bus.publish("TEMP_READY", {
    "temp": 28.5,
    "humid": 65.2,
    "valid": True
})
```

### 3.2 发布简单值

```python
# 自动封装为 {"value": True}
event_bus.publish("BUTTON_PRESSED", True)

# 自动封装为 {"value": 123}
event_bus.publish("COUNT_UPDATE", 123)
```

### 3.3 不携带数据

```python
event_bus.publish("SYSTEM_READY")
```

### 3.4 发布时设置来源

```python
event_bus.publish("TEMP_READY", {
    "temp": 28.5,
    "source": "temp_humid"  # 标识事件来源
})
```

### 3.5 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `event_name` | 字符串 | 事件名称，建议使用config中的常量 |
| `data` | dict/任意 | 事件数据，可选，自动补充timestamp |

**自动补充字段**：

| 字段 | 说明 | 示例 |
|------|------|------|
| `timestamp` | 自动补充当前时间戳 | 12345 |
| `source` | 事件来源（需手动设置） | "temp_humid" |

---

## 4. 处理事件 - pump()

### 4.1 在主循环中调用

```python
# main.py
while True:
    # 1. 调度所有模块
    for mod in modules:
        mod.tick()
    
    # 2. 处理事件队列
    event_bus.pump()
    
    # 3. 主循环延时
    time.sleep_ms(10)
```

### 4.2 pump()的行为

- 处理队列中的所有事件后返回
- 队列为空时立即返回
- 不阻塞主循环（回调应快速返回）

---

## 5. 完整使用示例

### 5.1 温湿度传感器模块

```python
class TempHumidDriver:
    def __init__(self, event_bus):
        self.event_bus = event_bus
    
    def init(self):
        # 订阅配置更新事件
        self.event_bus.subscribe("CONFIG_UPDATE", self._on_config_update)
    
    def tick(self):
        # 读取传感器
        temp = self.sensor.temperature
        humid = self.sensor.humidity
        
        # 发布数据就绪事件
        self.event_bus.publish("TEMP_READY", {
            "temp": temp,
            "humid": humid,
            "valid": True,
            "source": "temp_humid"
        })
    
    def _on_config_update(self, payload):
        if payload.get("target") == "temp_humid":
            self.sample_interval = payload["sample_ms"]
```

### 5.2 碰撞检测服务

```python
class CollisionService:
    def __init__(self, event_bus):
        self.event_bus = event_bus
    
    def init(self):
        # 订阅加速度数据
        self.event_bus.subscribe("IMU_DATA_READY", self._on_imu_data)
    
    def _on_imu_data(self, payload):
        acc = payload["acc_total"]
        
        # 检测碰撞
        if acc > self.threshold:
            # 发布碰撞事件
            self.event_bus.publish("COLLISION_DETECTED", {
                "acc": acc,
                "confidence": 0.9,
                "source": "collision_service"
            })
```

### 5.3 报警联动服务

```python
class AlarmService:
    def __init__(self, event_bus):
        self.event_bus = event_bus
    
    def init(self):
        # 订阅碰撞事件
        self.event_bus.subscribe("COLLISION_DETECTED", self._on_collision)
        
        # 订阅SOS按键事件
        self.event_bus.subscribe("SOS_PRESSED", self._on_sos)
    
    def _on_collision(self, payload):
        print(f"检测到碰撞！加速度: {payload['acc']}")
        self.start_alarm()
    
    def _on_sos(self, payload):
        print("SOS按键按下！")
        self.start_alarm()
    
    def start_alarm(self):
        # 启动蜂鸣器、LED闪烁等
        pass
```

### 5.4 main.py集成

```python
from Event_Bus import EventBus
from Temp_Humid import TempHumidDriver
from CollisionService import CollisionService
from AlarmService import AlarmService

def main():
    # 1. 创建EventBus
    event_bus = EventBus()
    event_bus.debug = True
    
    # 2. 创建模块
    temp_humid = TempHumidDriver(event_bus)
    collision = CollisionService(event_bus)
    alarm = AlarmService(event_bus)
    
    # 3. 初始化模块
    temp_humid.init()
    collision.init()
    alarm.init()
    
    # 4. 主循环
    while True:
        temp_humid.tick()
        event_bus.pump()
        time.sleep_ms(10)

if __name__ == "__main__":
    main()
```

---

## 6. 常用事件类型

### 6.1 传感器事件

| 事件名 | 触发时机 | payload字段 |
|--------|----------|-------------|
| `TEMP_HUMID_READY` | 温湿度采集完成 | temp, humid, valid |
| `IMU_DATA_READY` | 加速度数据就绪 | acc_x, acc_y, acc_z, acc_total |
| `GNSS_DATA_READY` | 定位数据就绪 | lat, lon, valid |
| `SENSOR_ERROR` | 传感器故障 | source, error |

### 6.2 业务事件

| 事件名 | 触发时机 | payload字段 |
|--------|----------|-------------|
| `COLLISION_DETECTED` | 检测到碰撞 | acc, confidence |
| `SOS_BUTTON_PRESSED` | SOS按键按下 | timestamp |
| `ALARM_TRIGGERED` | 报警启动 | alarm_type |
| `ALARM_CANCELED` | 报警取消 | duration |

### 6.3 系统事件

| 事件名 | 触发时机 | payload字段 |
|--------|----------|-------------|
| `SYSTEM_READY` | 系统启动完成 | modules_count |
| `CONFIG_UPDATE` | 配置更新 | target, params |

---

## 7. 调试技巧

### 7.1 查看订阅关系

```python
event_bus.debug = True

# 订阅时会输出
# [订阅] TEMP_READY <- on_temp_ready
```

### 7.2 在回调中打印事件

```python
def on_temp_ready(payload):
    print(f"[事件] TEMP_READY")
    print(f"  温度: {payload['temp']}℃")
    print(f"  时间戳: {payload['timestamp']}")
    print(f"  来源: {payload.get('source', 'unknown')}")
```

### 7.3 查看队列状态

```python
# 在pump()前检查队列长度
print(f"队列事件数: {len(event_bus._queue)}")
event_bus.pump()
```

---

## 8. 注意事项

### 8.1 回调函数必须快速返回

```python
# ❌ 错误：回调中阻塞
def on_collision(payload):
    time.sleep(5)  # 阻塞5秒！
    send_alert()

# ✅ 正确：回调快速返回
def on_collision(payload):
    send_alert()  # 快速操作
```

### 8.2 使用config常量避免硬编码

```python
# ❌ 错误：硬编码事件名
event_bus.subscribe("TEMP_READY", callback)

# ✅ 正确：使用常量
from config import EVENT_TEMP_HUMID_READY
event_bus.subscribe(EVENT_TEMP_HUMID_READY, callback)
```

### 8.3 异常不会中断其他订阅者

```python
# 订阅者A出错不会影响订阅者B
def callback_a(payload):
    result = 1 / 0  # 出错！

def callback_b(payload):
    print("正常执行")  # 仍会执行

event_bus.subscribe("EVENT", callback_a)
event_bus.subscribe("EVENT", callback_b)
```

---

**文档版本**：v1.0  
**更新日期**：2026-05-05
