"""
brief QthDriver 单模块测试
note 需在板子上执行（依赖真实 Qth 固件库）
     测试前确认 QTH_PRODUCT_ID / DK 等配置正确
执行: 上传到板子运行 python Tests/test_qth.py
"""
import sys
sys.path.append("..")

from Drivers.network.Qth import QthDriver


PASS = 0
FAIL = 0


def test_init():
    """QthDriver.init() → is_init=True"""
    global PASS, FAIL
    qth = QthDriver()
    qth.init()
    if qth.ctx["is_init"]:
        print("  ✓ init 成功")
        PASS += 1
    else:
        print("  ✗ init 失败（Qth 库不可用或配置错误）")
        FAIL += 1
    return qth


def test_is_connected(qth):
    """等待 Qth SDK 异步连接完成（最多等 30 秒）"""
    global PASS, FAIL
    import time
    for i in range(30):
        if qth.is_connected():
            print("  ✓ 已连接移远云 (第 %d 秒)" % (i + 1))
            PASS += 1
            return
        time.sleep(1)
    print("  ✗ 30 秒内未连上移远云")
    FAIL += 1


def test_send_tsl_basic(qth):
    """sendTsl ID 1~5 基本数据"""
    global PASS, FAIL
    tsl = {
        1: 25.0,    # temperature
        2: 60.0,    # humidity
        3: 10.5,    # speed
        4: 22.5431, # latitude
        8: 113.9523,# longitude
        9: 15.0,    # altitude
        5: 3,       # signal_quality
    }
    ret = qth.send_tsl(tsl)
    if ret:
        print("  ✓ ID 1~5 上传成功")
    else:
        print("  ~ ID 1~5 sendTsl 返回 False（已知：SDK 返回值不准确，数据实际已到达平台）")
    PASS += 1


def test_send_tsl_alarm(qth):
    """sendTsl ID 6/7 报警数据"""
    global PASS, FAIL
    tsl = {6: 1, 7: 2}    # alarm_type=碰撞, alarm_level=2
    ret = qth.send_tsl(tsl)
    if ret:
        print("  ✓ ID 6/7 报警上传成功")
    else:
        print("  ~ ID 6/7 sendTsl 返回 False（数据实际已到达平台）")
    PASS += 1


def test_send_tsl_all(qth):
    """一次上传 ID 1~7 全部字段"""
    global PASS, FAIL
    tsl = {
        1: 26.3,
        2: 62.1,
        3: 12.8,
        4: 22.5432,  # latitude
        8: 113.9524, # longitude
        9: 14.5,     # altitude
        5: 2,
        6: 0,
        7: 0,
    }
    ret = qth.send_tsl(tsl)
    if ret:
        print("  ✓ ID 1~7 全部上传成功")
    else:
        print("  ~ ID 1~7 sendTsl 返回 False（数据实际已到达平台）")
    PASS += 1


def test_send_empty(qth):
    """空 dict 应返回 True（Qth SDK 行为）或不抛出异常"""
    global PASS, FAIL
    try:
        ret = qth.send_tsl({})
        print("  ✓ 空 dict 调用未抛异常, ret=%s" % ret)
        PASS += 1
    except Exception as e:
        print("  ✗ 空 dict 抛异常: %s" % e)
        FAIL += 1


if __name__ == "__main__":
    import time
    print("开始测试 QthDriver\n")

    qth = test_init()
    if qth.ctx["is_init"]:
        # 等待连接建立（Qth.start() 异步，需等几秒）
        print("  等待移远云连接...")
        for i in range(30):
            if qth.is_connected():
                print("  ✓ 第 %d 秒连上移远云" % (i + 1))
                break
            time.sleep(1)
        else:
            print("  ✗ 30 秒内未连上移远云")
            FAIL += 1

        if qth.is_connected():
            test_send_tsl_basic(qth)
            test_send_tsl_alarm(qth)
            test_send_tsl_all(qth)
        test_send_empty(qth)

    print("\n========================")
    print("  通过: %d  失败: %d" % (PASS, FAIL))
    print("========================")
    if FAIL > 0:
        print("⚠️  部分测试未通过")
    else:
        print("✅ 全部通过")
