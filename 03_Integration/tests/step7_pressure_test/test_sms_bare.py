"""
brief SMS 最小复现 — 模拟 30 分钟压力测试的 SMS 崩溃模式
note 纯 quectel 调用，零框架依赖
usage REPL: import test_sms_bare
"""
import time
import gc
import _thread
from quectel import GNSS, Audio, SMS

TEST_PHONE = "13368190189"
AT_LOCK = _thread.allocate_lock()
SMS_MSG = "SOS:3(GPS):https://uri.amap.com/marker?position=116.413640,39.905604&name=SOS%E7%B4%A7%E6%80%A5%E6%B1%82%E5%8A%A9"

def _audio_cb(evt):
    pass  # 哑回调


def _tts_burst(audio, texts):
    """模拟报警链路: stop→TTS→stop→TTS 密集序列"""
    for t in texts:
        try:
            audio.tts_stop()
        except:
            pass
        time.sleep_ms(100)
        AT_LOCK.acquire()
        try:
            audio.tts_play(t)
        finally:
            AT_LOCK.release()
        time.sleep_ms(500)  # 给 TTS 一点时间


def test_sms_bare():
    gc.collect()
    t0 = time.ticks_ms()
    print("=" * 50)
    print(" SMS 最小复现 (模拟压力测试)")
    print("=" * 50)

    gnss = GNSS()
    audio = Audio()
    sms = SMS()
    print("句柄创建完成")

    # ====== Init ======
    print("\n[GNSS] start...")
    if not gnss.start():
        print("FAIL"); return
    print("[GNSS] OK")

    print("[Audio] init...")
    if not audio.init(_audio_cb):
        print("FAIL"); return
    audio.set_speaker_volume(5)
    audio.tts_set_speed(85)
    print("[Audio] OK")

    # ====== GNSS 后台线程 ======
    gnss_running = True
    gnss_count = [0]

    def gnss_loop():
        while gnss_running:
            time.sleep_ms(2000)
            AT_LOCK.acquire(0)
            try:
                gnss.get_location()
                gnss_count[0] += 1
            except:
                pass
            finally:
                AT_LOCK.release()

    _thread.stack_size(4096)
    _thread.start_new_thread(gnss_loop, ())
    print("[GNSS] 线程启动")

    # ====== Warmup 30s ======
    print("\n暖机 30s...")
    for i in range(30):
        time.sleep_ms(1000)
    print("暖机完成 | polls=%d" % gnss_count[0])

    # ====== SMS1 (clean) ======
    print("\n--- SMS1 (洁净堆) ---")
    ok1 = False
    try:
        AT_LOCK.acquire()
        try:
            sms.send(TEST_PHONE, "SMS1:" + SMS_MSG)
            ok1 = True
        finally:
            AT_LOCK.release()
        print("SMS1: OK")
    except Exception as e:
        print("SMS1: FAIL - %s" % e)
    time.sleep_ms(3000)

    # ====== SMS2 (紧随其后) ======
    print("\n--- SMS2 (紧随其后) ---")
    ok2 = False
    try:
        AT_LOCK.acquire()
        try:
            sms.send(TEST_PHONE, "SMS2:" + SMS_MSG)
            ok2 = True
        finally:
            AT_LOCK.release()
        print("SMS2: OK")
    except Exception as e:
        print("SMS2: FAIL - %s" % e)
    time.sleep_ms(3000)

    # ====== Dense TTS load (模拟报警切换 + 语音查询) ======
    print("\n密集 TTS (模拟报警切换)...")
    tts_count = 0
    # 模拟压力测试中的报警链路: 碰撞→cancel→SOS→cancel 循环
    alarm_chain = [
        ["碰撞报警等级1", "报警已取消"],
        ["SOS报警请注意安全", "报警已取消"],
        ["碰撞报警等级2", "报警已取消"],
        ["SOS报警请注意安全", "报警已取消"],
        ["碰撞报警等级3", "报警已取消"],
        ["SOS报警请注意安全", "报警已取消"],
        ["碰撞报警等级1", "报警已取消"],
    ]
    for cycle in range(15):  # 15 轮报警循环
        _tts_burst(audio, alarm_chain[cycle % len(alarm_chain)])
        tts_count += len(alarm_chain[cycle % len(alarm_chain)])
        # 模拟语音查询 TTS
        AT_LOCK.acquire()
        try:
            audio.tts_play("查询%d" % cycle)
        finally:
            AT_LOCK.release()
        tts_count += 1
        time.sleep_ms(2000)

        if (cycle + 1) % 2 == 0:
            print("  轮%d | polls=%d | tts=%d" % (cycle + 1, gnss_count[0], tts_count))

    # ====== 模拟报警密集链 (stress test pattern: stop→TTS→stop→TTS in <1s) ======
    print("\n报警密集链...")
    for burst in range(10):
        # Rapid burst: stop old → play alarm → cancel → play cancel msg
        for cmd_text in [
            "碰撞报警等级3",
            "报警已取消",
            "SOS报警请注意安全",
            "报警已取消",
        ]:
            try: audio.tts_stop()
            except: pass
            time.sleep_ms(50)
            AT_LOCK.acquire()
            try:
                audio.tts_play(cmd_text)
            finally:
                AT_LOCK.release()
            time.sleep_ms(300)
            tts_count += 1
        time.sleep_ms(1000)
        if (burst+1) % 3 == 0:
            print("  密集轮%d | polls=%d | tts=%d" % (burst+1, gnss_count[0], tts_count))

    # 额外普通 TTS 填充（模拟导航 + 控制反馈）
    print("\n普通 TTS 填充...")
    for i in range(40):
        time.sleep_ms(2000)
        AT_LOCK.acquire()
        try:
            audio.tts_play("填%d" % i)
        finally:
            AT_LOCK.release()
        tts_count += 1
        if (i + 1) % 10 == 0:
            print("  polls=%d | tts=%d" % (gnss_count[0], tts_count))

    # ====== SMS3 (碎片堆) ======
    print("\n--- SMS3 (碎片堆) ---")
    ok3 = False
    try:
        AT_LOCK.acquire()
        try:
            sms.send(TEST_PHONE, "SMS3:" + SMS_MSG)
            ok3 = True
        finally:
            AT_LOCK.release()
        print("SMS3: OK")
    except Exception as e:
        print("SMS3: FAIL - %s" % e)

    # ====== 清理 ======
    gnss_running = False
    time.sleep_ms(2000)
    try:
        gnss.stop()
    except:
        pass
    gc.collect()

    # ====== 结果 ======
    print("\n" + "=" * 50)
    print(" 结果")
    print("=" * 50)
    print("SMS1 (洁净)  : %s" % ("OK" if ok1 else "FAIL"))
    print("SMS2 (紧随)  : %s" % ("OK" if ok2 else "FAIL"))
    print("SMS3 (负载后): %s" % ("OK" if ok3 else "FAIL"))
    print("GNSS 轮询    : %d" % gnss_count[0])
    print("TTS 播报     : %d" % tts_count)
    elapsed = time.ticks_diff(time.ticks_ms(), t0) // 1000
    print("耗时         : %ds" % elapsed)
    print("")

    if ok1 and ok2 and ok3:
        print("结论: 三次均成功")
    elif ok1 and ok2 and not ok3:
        print("结论: 复现成功 - EC200U 堆耗尽")
    else:
        print("结论: 前两次已失败，非负载问题")
    print("=" * 50)


test_sms_bare()
