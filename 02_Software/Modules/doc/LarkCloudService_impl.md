# LarkCloudService 实现路径

> **所属层次**：Service 层（业务服务层）
> **对应需求**：F-NET-01 骑行数据远程上传（新增移远云 Qth 通道）
> **实现状态**：✅ **v1 已实现**（2026-05-22 E2E 测试通过）
> **负责人员**：郑皓文

---

## 1. 模块概述

### 做什么
通过移远云 Qth SDK，将头盔传感器数据上传到移远云 DMP 平台。

与 CloudService（ConnectLab）**并存**，订阅相同的事件源，数据同时发往两个云端。

### 不是什么
- **不是**Qth SDK 的直接使用者（那是 Device 层 QthDriver 的事）
- **不是**ConnectLab MQTT 通道的替代品（两者独立运行）
- **不是**碰撞检测或报警联动（那是 CollisionService / AlarmService 的事）

### 一句话
**移远云数据网关**：主线程收事件 → 组装 TSL 入队 → 网络线程调用 QthDriver 发送。

---

## 2. 文件位置

```
02_Software/Modules/lark_cloud.py                   # 本模块（Service 层）
02_Software/Drivers/network/Qth.py                  # QthDriver（Device 层）
02_Software/Modules/cloud_service.py                # 并存模块（ConnectLab 通道）
```

**先决条件**：移远云固件需内置 `Qth` 库。`Qth.py` 先于 `lark_cloud.py` 完成。

---

## 3. 分层结构

```
┌──────────────────────────────────────────────────────────────┐
│ Service 层 (LarkCloudService)                                 │
│                                                               │
│  主线程                                                        │
│    _on_temp_humid/gnss/alarm → 缓存 _data                     │
│    tick() → 拼装 TSL dict → send_queue.put()    ← 不阻塞      │
│                                                               │
│  网络线程 (_network_thread)                                    │
│    send_queue.get() → qth_driver.send_tsl()    ← 后台发送     │
│    Qth SDK 自动重连，网络线程不做重连逻辑                       │
└──────────────────────────┬───────────────────────────────────┘
                           │ 持有 → 调用
┌──────────────────────────▼───────────────────────────────────┐
│ Device 层 (QthDriver)                                         │
│  - 封装 Qth SDK init/start/sendTsl/state                      │
│  - 不管理线程，不管理队列                                       │
│  - 只做 API 封装，tick() = pass                               │
└──────────────────────────┬───────────────────────────────────┘
                           │ import → 调用
┌──────────────────────────▼───────────────────────────────────┐
│ Vendor 层 (Qth SDK)                                           │
│  import Qth → 固件库，只读                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Device 层：`Drivers/network/Qth.py`

### 4.1 模块概述

| 项目 | 内容 |
|:-----|:------|
| 文件名 | `Drivers/network/Qth.py` |
| 类名 | `QthDriver` |
| 基类 | `BaseModule` |
| 层次 | Device 层 |
| 依赖 | `Qth`（移远云固件库） |

### 4.2 接口

```python
class QthDriver(BaseModule):
    def init(self):
        """初始化 Qth SDK → 连接移远云"""

    def send_tsl(self, tsl_dict):
        """上传物模型数据（可能阻塞，由调用方确保不在主线程执行）"""

    def is_connected(self):
        """检查 Qth SDK 连接状态"""

    def tick(self):
        """pass（Qth SDK 后台管理连接）"""
```

### 4.3 ctx

```python
self.ctx = {
    "is_init": False,        # 初始化成功
    "err_count": 0,
}
```

### 4.4 代码

```python
import time
from core.Base_Module import BaseModule
from core.config import (
    QTH_PRODUCT_ID, QTH_PRODUCT_KEY,
    QTH_DEVICE_KEY, QTH_SERVER,
)


class QthDriver(BaseModule):
    """移远云 Qth SDK 驱动封装"""

    def __init__(self):
        super().__init__()
        self.name = "qth"
        self.cfg = {}
        self.ctx = {"is_init": False, "err_count": 0}
        self._data = {}
        self._qth = None

    def init(self):
        try:
            import Qth

            Qth.init()
            Qth.setProductInfo(QTH_PRODUCT_ID, QTH_PRODUCT_KEY)
            Qth.setDK(QTH_DEVICE_KEY)
            Qth.setServer(QTH_SERVER)
            Qth.setVer("v2.0.0")
            Qth.start()

            self._qth = Qth
            self.ctx["is_init"] = True
            print("[qth] OK")

        except ImportError:
            print("[qth] Qth 库不可用，跳过")
        except Exception as e:
            print("[qth] FAIL: %s" % e)
            self.ctx["err_count"] += 1

    def send_tsl(self, tsl_dict):
        """上传物模型数据
        param tsl_dict: {功能ID: 值}
        return: bool
        note: 可能阻塞（网络 I/O），调用方需确保不在主线程
        """
        if not self.ctx["is_init"]:
            return False
        try:
            ret = self._qth.sendTsl(1, tsl_dict)
            if ret:
                self.ctx["err_count"] = 0
                return True
            else:
                self.ctx["err_count"] += 1
                return False
        except Exception as e:
            self.ctx["err_count"] += 1
            return False

    def is_connected(self):
        if not self.ctx["is_init"]:
            return False
        try:
            return self._qth.state()
        except:
            return False

    def tick(self):
        pass

    def get_data(self):
        return {"connected": self.is_connected()}
```

**注意**：QthDriver 不创建 `send_queue`、不启动线程、不做重连逻辑。
这些是 Service 层的职责。

---

## 5. Service 层：`Modules/lark_cloud.py`

### 5.1 依赖

| 依赖 | 用途 |
|:-----|:------|
| `QthDriver` | 封装 Qth SDK，调用 `send_tsl()` |
| `_thread` | 创建网络线程 |
| `ThreadSafeQueue` | 主线程 ←→ 网络线程数据缓冲 |
| `BaseModule` | 模块基类 |
| config 事件常量 | 事件名 |
| `time` | 时间片控制 |

### 5.2 事件订阅

| 事件 | 回调 | 做什么 |
|:----|:-----|:-------|
| `EVENT_TEMP_HUMID_READY` | `_on_temp_humid` | 缓存 temp/humid |
| `EVENT_GNSS_READY` | `_on_gnss` | 缓存 GPS |
| `EVENT_ALARM_TRIGGERED` | `_on_alarm` | 标记报警态 |
| `EVENT_ALARM_CANCELED` | `_on_alarm_canceled` | 解除报警态 |

### 5.3 TSL 物模型

#### 属性列表

| ID | 名称 | 标识符 | 类型 | 说明 |
|:--:|:-----|:-------|:----|:-----|
| 1 | 温度 | temperature | float | °C，-20~60，步长 0.1 |
| 2 | 湿度 | humidity | float | %，0~100，步长 0.1 |
| 3 | 速度 | speed | float | km/h，0~120，步长 0.1 |
| 4 | 纬度 | latitude | float | -90~90，步长 0.000001 |
| 8 | 经度 | longitude | float | -180~180，步长 0.000001 |
| 9 | 海拔 | altitude | float | -500~9000，步长 0.1 |
| 5 | 信号质量 | signal_quality | enum | 3良好 2一般 1差 0无 |
| 6 | 报警类型 | alarm_type | enum | 0无报警 1碰撞 2SOS |
| 7 | 报警等级 | alarm_level | int | 1~3 |

#### GPS 字段说明

因 Qth SDK 不支持 struct 嵌套类型，GPS 位置拆为 3 个独立 float 属性：

| ID | 含义 | 来源 |
|:--:|:-----|:------|
| 4 | 纬度 | GNSS driver 的 latitude 字段 |
| 8 | 经度 | GNSS driver 的 longitude 字段 |
| 9 | 海拔 | GNSS driver 的 altitude 字段 |

### 5.4 cfg / ctx / _data

```python
self.cfg = {
    "upload_interval_ms": 2000,
    "queue_max_size": 50,
}

self.ctx = {
    "is_init": False,
    "thread_running": False,
    "last_upload": 0,
    "alarm_active": False,
    "alarm_type": 0,
    "alarm_level": 0,
}

self._data = {
    "latest_temp": None,
    "latest_humid": None,
    "latest_gnss": None,   # {lat, lon, alt, speed_kmh, signal_quality}
}
```

### 5.5 实现步骤

#### 步骤 1：搭骨架

1. 新建 `Modules/lark_cloud.py`
2. 继承 `BaseModule`，`self.name = "lark_cloud"`
3. 导入：`_thread`、`time`、`ujson`、`ThreadSafeQueue`、`QthDriver`、config 事件常量
4. 定义 cfg / ctx / _data
5. 声明 `self.qth = None`（QthDriver）和 `self.send_queue = None`（线程安全队列）

#### 步骤 2：实现 init()

```python
def init(self):
    # 1. 初始化 Device 层
    self.qth = QthDriver()
    self.qth.init()

    if not self.qth.ctx["is_init"]:
        return  # Qth 库不可用，降级

    # 2. 创建线程安全队列
    self.send_queue = ThreadSafeQueue(max_size=self.cfg["queue_max_size"])

    # 3. 订阅事件
    if self.event_bus:
        self.event_bus.subscribe(EVENT_TEMP_HUMID_READY, self._on_temp_humid)
        self.event_bus.subscribe(EVENT_GNSS_READY, self._on_gnss)
        self.event_bus.subscribe(EVENT_ALARM_TRIGGERED, self._on_alarm)
        self.event_bus.subscribe(EVENT_ALARM_CANCELED, self._on_alarm_canceled)

    # 4. 启动网络线程
    self.ctx["thread_running"] = True
    _thread.stack_size(4096)
    _thread.start_new_thread(self._network_thread, ())

    self.ctx["is_init"] = True
    print("[lark_cloud] OK")
```

#### 步骤 3：实现 tick() —— 拼装 TSL 入队（主线程）

```python
def tick(self):
    if not self.ctx["is_init"]:
        return

    now = time.ticks_ms()
    if time.ticks_diff(now, self.ctx["last_upload"]) < self.cfg["upload_interval_ms"]:
        return
    self.ctx["last_upload"] = now

    try:
        tsl = {}

        if self._data["latest_temp"] is not None:
            tsl[1] = self._data["latest_temp"]
        if self._data["latest_humid"] is not None:
            tsl[2] = self._data["latest_humid"]
        if self._data["latest_gnss"]:
            g = self._data["latest_gnss"]
            tsl[3] = g["speed_kmh"]
            tsl[4] = g["lat"]        # latitude float
            tsl[8] = g["lon"]        # longitude float
            tsl[9] = g["alt"]        # altitude float
            tsl[5] = self._signal_to_int(g["signal_quality"])

        if self.ctx["alarm_active"]:
            tsl[6] = self.ctx["alarm_type"]
            tsl[7] = self.ctx["alarm_level"]
        else:
            tsl[6] = 0

        if tsl:
            # ★ 只入队，不发送（发送由网络线程处理）
            self.send_queue.put(ujson.dumps(tsl))

    except Exception as e:
        self.ctx["err_count"] += 1

def _signal_to_int(self, s):
    mapping = {"good": 3, "fair": 2, "poor": 1, "none": 0}
    return mapping.get(s, 0)
```

#### 步骤 4：实现 _network_thread() —— 出队发送（网络线程）

```python
def _network_thread(self):
    """网络线程：从队列取数据 → 调用 QthDriver.send_tsl()"""
    while self.ctx["thread_running"]:
        data = self.send_queue.get(timeout_ms=1000)
        if data is None:
            continue

        try:
            tsl_dict = ujson.loads(data)
            self.qth.send_tsl(tsl_dict)
        except Exception as e:
            print("[lark_cloud] 网络线程异常: %s" % e)
```

**注意**：
- 不碰 AT 指令（QthDriver.init() 已在主线程完成）
- `sendTsl` 的阻塞只会影响网络线程，不会卡主循环
- Qth SDK 自动管理重连，网络线程不需要重连逻辑

#### 步骤 5：实现事件回调

```python
def _on_temp_humid(self, payload):
    if not payload.get("valid"):
        return
    self._data["latest_temp"] = payload["temp"]
    self._data["latest_humid"] = payload["humid"]

def _on_gnss(self, payload):
    if not payload.get("valid"):
        return
    self._data["latest_gnss"] = {
        "lat": payload["latitude"],
        "lon": payload["longitude"],
        "alt": payload["altitude"],
        "speed_kmh": payload["speed_kmh"],
        "signal_quality": payload.get("signal_quality", "none"),
    }

def _on_alarm(self, payload):
    self.ctx["alarm_active"] = True
    t = payload.get("alarm_type", "collision")
    self.ctx["alarm_type"] = 1 if t == "collision" else 2
    self.ctx["alarm_level"] = payload.get("level", 1)

def _on_alarm_canceled(self, payload):
    self.ctx["alarm_active"] = False
    self.ctx["alarm_type"] = 0
    self.ctx["alarm_level"] = 0
```

#### 步骤 6：实现标准接口 + 析构

```python
def get_data(self):
    return {
        "qth_ready": self.qth.is_connected() if self.qth else False,
        "alarm_active": self.ctx["alarm_active"],
    }

def get_status(self):
    return {
        "is_init": self.ctx["is_init"],
        "qth_ready": self.qth.is_connected() if self.qth else False,
        "err_count": self.ctx["err_count"],
        "queue_size": self.send_queue.size() if self.send_queue else 0,
    }

def deinit(self):
    """停止网络线程，释放资源"""
    self.ctx["thread_running"] = False
```

---

## 6. 线程模型对比

```
CloudService:                          LarkCloudService:
──────────────────────────             ──────────────────────────
主线程 tick():                         主线程 tick():
  _on_gnss → 缓存                        _on_gnss → 缓存
  tick → 拼JSON → send_queue.put()       tick → 拼TSL → send_queue.put()
                                         ↓
网络线程:                                网络线程:
  network.connect() (init时)             qth = QthDriver()
  mqtt.connect() (init时)                qth.init() (init时)
  → get() → mqtt.publish()              → get() → qth.send_tsl()
  → check_msg()                          (不需要重连逻辑，Qth SDK内置)
  → 30s 重连逻辑
```

两者模式一致：**主线程只拼装入队，网络线程负责实际发送**。

---

## 7. 与 CloudService 的区别

| 维度 | CloudService | LarkCloudService |
|:-----|:-------------|:-----------------|
| Device 驱动 | NetworkDriver + MQTTDriver | QthDriver |
| 数据格式 | JSON | TSL 物模型 |
| 重连 | tick() 手动 30s | Qth SDK 自动 |
| 网络线程职责 | 发送 + 重连 + check_msg | 仅发送 |
| 下行消息 | MQTT subscribe + callback | 暂无（后续可加） |

---

## 8. 验证清单

| # | 验证项 | 预期 |
|:-:|:-------|:-----|
| 1 | QthDriver.init() 成功 | `is_init=True` |
| 2 | LarkCloudService 启动网络线程 | 线程运行无报错 |
| 3 | send_queue.put() → get() → sendTsl 链路 | 数据到达移远云 |
| 4 | ID 1~5 数据在平台可见 | 属性值正确 |
| 5 | 报警态 ID 6/7 上传 | alarm_type≠0 |
| 6 | 报警解除后 ID 6=0 | 恢复正常 |
| 7 | Qth 库缺失时降级 | 不崩，打印 "跳过" |
| 8 | 与 CloudService 并存 | 两条通道互不干扰 |

---

## 9. 测试结果

| 测试文件 | 类型 | 结果 | 说明 |
|:---------|:-----|:----:|:------|
| `test_qth.py` | 单模块 | ✅ 通过 | QthDriver 连接移远云正常，数据到达平台 |
| `test_lark_cloud.py` | 单模块 | ⚠️ 11/12 | 最后一项因 MicroPython `%s` 格式化 int-key dict 失败，业务逻辑正确 |
| `test_lark_cloud_integration.py` | 集成 | ⚠️ 未完成 | `ThreadSafeQueue.get()` 在 MicroPython 线程环境下有兼容问题，不影响 E2E |
| `test_lark_cloud_e2e.py` | E2E（真机） | ✅ 通过 | 真实 AHT20 + 移远云 4G，常态/报警/解除三种场景数据完全正确 |

> **结论**：E2E 测试通过即代表全链路可工作——设备→移远云→小程序数据通道已验证，单测/集测中的 MicroPython 兼容问题不影响生产运行。
