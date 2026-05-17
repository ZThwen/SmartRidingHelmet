"""
brief 线程安全队列（生产者-消费者）
note 基于 _thread.allocate_lock + semaphore 实现
      参考 examples/thread.py 的 ProducerConsumer 模式
      主线程 put()，网络线程 get()，两者无锁竞争
      满队列时丢弃最旧数据，永不阻塞主线程
"""
import _thread


class ThreadSafeQueue:
    def __init__(self, max_size=100):
        """
        brief 初始化线程安全队列
        param max_size: 队列最大容量，超出时丢弃最旧元素
        """
        self._max_size = max_size
        self._items = []
        self._lock = _thread.allocate_lock()
        self._sem = _thread.allocate_semaphore(0)

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
        self._sem.release()

    def get(self, timeout_ms=500):
        """
        brief 出队（线程安全，支持超时等待）
        param timeout_ms: 最大等待时间（ms），默认 500ms
        return 队列元素，超时返回 None
        """
        try:
            acquired = self._sem.acquire(timeout_ms)
        except Exception:
            acquired = False
        if acquired:
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
