"""
brief 线程安全队列单元测试
note 验证 ThreadSafeQueue 的 put/get/size/clear 正确性
执行: 上传到板子运行 python test_thread_queue.py
"""
import sys
sys.path.append("..")

from Drivers.network.thread_queue import ThreadSafeQueue


def test_basic_put_get():
    """put 一条，get 返回同一条"""
    q = ThreadSafeQueue(max_size=10)
    q.put(42)
    result = q.get(timeout_ms=100)
    assert result == 42, "期望 42，实际 %s" % str(result)
    print("  OK 基本入出队")


def test_fifo_order():
    """先进先出顺序"""
    q = ThreadSafeQueue(max_size=10)
    for i in range(1, 6):
        q.put(i)
    for i in range(1, 6):
        v = q.get(timeout_ms=100)
        assert v == i, "期望 %s，实际 %s" % (i, v)
    print("  OK FIFO 顺序")


def test_empty_queue_timeout():
    """空队列超时返回 None"""
    q = ThreadSafeQueue(max_size=10)
    result = q.get(timeout_ms=50)
    assert result is None, "空队列应返回 None，实际 %s" % str(result)
    print("  OK 空队列超时")


def test_max_size_drop_oldest():
    """满队列丢弃最旧元素"""
    q = ThreadSafeQueue(max_size=3)
    q.put(1)
    q.put(2)
    q.put(3)
    q.put(4)
    assert q.size() == 3, "队列长度应为 3，实际 %s" % q.size()
    first = q.get(timeout_ms=100)
    assert first == 2, "丢弃最旧后第一个应为 2，实际 %s" % first
    print("  OK 满队列丢弃最旧")


def test_clear():
    """清空队列"""
    q = ThreadSafeQueue(max_size=10)
    q.put(1)
    q.put(2)
    q.clear()
    assert q.size() == 0, "清空后 size 应为 0，实际 %s" % q.size()
    result = q.get(timeout_ms=50)
    assert result is None, "清空后 get 应返回 None"
    print("  OK 清空队列")


def test_multiple_put_get():
    """连续 put 后全部 get"""
    q = ThreadSafeQueue(max_size=20)
    data = list(range(10))
    for x in data:
        q.put(x)
    assert q.size() == 10
    out = []
    for _ in range(10):
        v = q.get(timeout_ms=100)
        out.append(v)
    assert out == data, "数据不一致"
    print("  OK 连续写入读出一致性")


def main():
    print("=== ThreadSafeQueue Unit Test ===\n")
    tests = [
        ("basic put/get", test_basic_put_get),
        ("FIFO order", test_fifo_order),
        ("empty timeout", test_empty_queue_timeout),
        ("max size drop", test_max_size_drop_oldest),
        ("clear", test_clear),
        ("multi put/get", test_multiple_put_get),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            import sys
            print("  X %s: %s" % (name, e))
    print("\nResult: %s/%s passed" % (passed, len(tests)))


if __name__ == "__main__":
    main()
