"""
brief 线程安全队列（生产者-消费者）
note 基于 _thread.allocate_lock + semaphore 实现
      参考 examples/thread.py 的 ProducerConsumer 模式
      主线程 put()，网络线程 get()，两者无锁竞争
      满队列时丢弃最旧数据，永不阻塞主线程
"""
import _thread
import time


class ThreadSafeQueue:
    def __init__(self, max_size=100):
        """
        brief 初始化线程安全队列
        param max_size: 队列最大容量，超出时丢弃最旧元素
        """
        self._max_size = max_size
        self._items = []
        self._lock = _thread.allocate_lock()

    def put(self, item):
        """
        brief 入队（线程安全）
        param item: 任意类型数据
        note 队列满时自动丢弃最旧元素，永不阻塞
        """
        with self._lock:
            if len(self._items) >= self._max_size:
                self._items.pop(0)
            self._items.append(item)

    def get(self, timeout_ms=500):
        """
        brief 出队（线程安全）
        param timeout_ms: 保留参数，暂不使用
        return 队列元素，队列为空返回 None
        note 极简实现：有数据就取，没数据直接返回 None
             不使用 sleep/轮询，避免 MicroPython 兼容问题
             网络线程依赖此方法，确保不崩
        """
        with self._lock:
            if self._items:
                return self._items.pop(0)
        return None

    def size(self):
        """
        brief 获取当前队列长度
        return int 队列中元素个数
        """
        with self._lock:
            return len(self._items)

    def clear(self):
        """
        brief 清空队列
        """
        with self._lock:
            self._items.clear()
