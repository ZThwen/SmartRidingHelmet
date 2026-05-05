"""
brief 模块基类：定义四元组规范和生命周期接口
note 所有业务模块继承此类，实现统一的生命周期接口
"""

class BaseModule:
    def __init__(self):
        # 架构元数据
        self.name = "base_module"      # 模块标识符
        
        # 四元组占位声明（子类必须初始化）
        # self.cfg   = {}  # 静态配置
        # self.ctx   = {}  # 运行时上下文
        # self._data = {}  # 当前数据
    
    # ================= 核心生命周期接口（子类必须实现） =================
    def init(self):
        """
        brief 初始化模块（硬件配置 + 订阅事件）
        note 上电配置硬件、验证设备在线、订阅事件。失败请 raise 异常
        """
        raise NotImplementedError("子类必须实现 init()")
    
    def tick(self):
        """
        brief 周期调度（数据采集 + 事件发布）
        note 主循环每轮调用，必须快速返回（<5ms），不能阻塞
        """
        raise NotImplementedError("子类必须实现 tick()")
    
    # ================= 辅助方法（可选实现） =================
    def get_data(self):
        """
        brief 获取数据快照
        return dict 数据副本
        """
        return dict(self._data) if hasattr(self, '_data') else {}
    
    def get_status(self):
        """
        brief 获取运行状态
        return dict 状态快照
        """
        return dict(self.ctx) if hasattr(self, 'ctx') else {}
