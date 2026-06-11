class BaseModule:
    def __init__(self):
        self.name = "base_module"
    def init(self):
        raise NotImplementedError("子类必须实现 init()")
    def tick(self):
        raise NotImplementedError("子类必须实现 tick()")
    def get_data(self):
        return dict(self._data) if hasattr(self, '_data') else {}
    def get_status(self):
        return dict(self.ctx) if hasattr(self, 'ctx') else {}
    def get_error_data(self, error):
        import time
        return {
            "source": self.name,
            "code": self.ctx.get("err_count", 0) if hasattr(self, 'ctx') else 0,
            "error": str(error),
            "timestamp": time.ticks_ms(),
            "is_init": self.ctx.get("is_init", False) if hasattr(self, 'ctx') else False
        }