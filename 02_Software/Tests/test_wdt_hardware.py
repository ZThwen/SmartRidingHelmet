"""
brief 硬件看门狗 (WDT) 验证测试 — STM32F413ZH IWDG
note 分阶段验证，逐步确认 machine.WDT 可用性和 IWDG 行为
      最后阶段会触发系统复位，请提前保存所有文件！
usage 通过 Thonny 上传到 NUCLEO-F413ZH 板子运行
"""

import time
import gc


# ==================== Phase 1: 模块可用性检查 ====================
def phase1_check_availability():
    """
    brief 检查 machine.WDT 和 machine.mem32 是否可用
    return True 如果都可用
    """
    print("\n" + "=" * 50)
    print("Phase 1: 检查 machine.WDT 和 machine.mem32 是否可用")
    print("=" * 50)

    # 测试 1: machine.WDT
    try:
        from machine import WDT
        print("  ✅ machine.WDT 可导入")
    except ImportError as e:
        print("  ❌ machine.WDT 不可用: %s" % e)
        print("     可能原因: 固件未编译 MICROPY_PY_MACHINE_WDT")
        return False

    # 测试 2: machine.mem32
    try:
        from machine import mem32
        print("  ✅ machine.mem32 可导入")
    except ImportError as e:
        print("  ❌ machine.mem32 不可用: %s" % e)
        print("     可能原因: 固件未编译 MICROPY_PY_MACHINE_MEMX")
        return False

    # 测试 3: machine.reset_cause + WDT_RESET 常量
    try:
        from machine import reset_cause, WDT_RESET
        cause = reset_cause()
        print("  ✅ machine.reset_cause() = %d" % cause)
        print("     WDT_RESET 常量 = %d" % WDT_RESET)
        if cause == WDT_RESET:
            print("     ⚠️ 上次复位原因是看门狗超时！")
    except Exception as e:
        print("  ❌ reset_cause 不可用: %s" % e)

    return True


# ==================== Phase 2: WDT 喂狗测试（安全） ====================
def phase2_feed_test():
    """
    brief 创建 4 秒 WDT，在超时前喂狗 3 次，验证系统不会复位
    note 此测试不会复位系统
    """
    print("\n" + "=" * 50)
    print("Phase 2: WDT 喂狗测试 (4 秒超时，每 1.5 秒喂一次)")
    print("=" * 50)

    from machine import WDT

    print("  创建 WDT(timeout=4000)...")
    wdt = WDT(timeout=4000)  # 4 秒超时
    print("  ✅ WDT 已启动")
    print("  注意: IWDG 一旦启动就无法软件关闭！")

    for i in range(3):
        time.sleep_ms(1500)  # 等 1.5 秒（在 4 秒超时内）
        wdt.feed()
        gc.collect()
        free = gc.mem_free()
        print("  [%d/3] 已喂狗 — 内存: %d bytes" % (i + 1, free))

    print("  ✅ Phase 2 通过: 喂狗后系统未复位")


# ==================== Phase 3: 等待超时测试（会复位！） ====================
def phase3_timeout_test():
    """
    brief 创建 WDT 后不喂狗，验证系统在超时后自动复位
    warning 此测试会触发系统复位！请提前保存所有文件！
    """
    print("\n" + "=" * 50)
    print("Phase 3: WDT 超时复位测试")
    print("=" * 50)
    print("  ⚠️  此测试将在 5 秒后触发系统复位")
    print("  ⚠️  请确保已保存所有未提交的文件！")
    print("  ⚠️  按 Ctrl+C 可取消...")
    print()

    for i in range(3, 0, -1):
        print("  %d..." % i)
        time.sleep_ms(1000)

    from machine import WDT

    wdt = WDT(timeout=5000)  # 5 秒超时
    print("  WDT 已启动 (5 秒超时)，不再喂狗...")
    print("  预期: 系统将在约 5 秒后自动复位")
    print()

    for i in range(10):
        time.sleep_ms(1000)
        free = gc.mem_free()
        print("  已过 %d 秒 — 内存: %d bytes (未喂狗)" % (i + 1, free))
        gc.collect()

    # 如果执行到这里，说明 WDT 没有生效
    print()
    print("  ❌ WDT 未触发复位 — 可能原因:")
    print("     1. 固件不支持 machine.WDT")
    print("     2. IWDG 时钟未初始化")
    print("     3. 超时配置无效")


# ==================== Phase 4: mem32 直接寄存器操作 (备选) ====================
def phase4_mem32_test():
    """
    brief 如果 machine.WDT 不可用，尝试通过 mem32 直接操作 IWDG 寄存器
    note 参考 Phase 1 的 mem32 检测结果
    """
    print("\n" + "=" * 50)
    print("Phase 4: mem32 直接寄存器操作验证")
    print("=" * 50)

    try:
        from machine import mem32
    except ImportError:
        print("  ❌ machine.mem32 不可用，跳过")
        return

    # STM32F413 IWDG 寄存器地址
    IWDG_BASE = 0x40003000
    IWDG_KR  = IWDG_BASE + 0x00  # 密钥寄存器
    IWDG_PR  = IWDG_BASE + 0x04  # 预分频器
    IWDG_RLR = IWDG_BASE + 0x08  # 重载寄存器
    IWDG_SR  = IWDG_BASE + 0x0C  # 状态寄存器

    # 读当前 IWDG 状态
    try:
        kr = mem32[IWDG_KR]
        pr = mem32[IWDG_PR]
        rlr = mem32[IWDG_RLR]
        sr = mem32[IWDG_SR]
        print("  ✅ IWDG 寄存器可读:")
        print("     KR  = 0x%08X" % kr)
        print("     PR  = 0x%08X" % pr)
        print("     RLR = 0x%08X" % rlr)
        print("     SR  = 0x%08X" % sr)

        # 判断当前状态
        if kr in (0x0000FFFF, 0x00000000):
            print("     状态: IWDG 已禁用（上电默认）")
        else:
            print("     状态: IWDG 可能已启用")
    except Exception as e:
        print("  ❌ IWDG 寄存器读取失败: %s" % e)
        return

    # 尝试写预分频器（不启动 WDT，安全操作）
    print()
    print("  尝试写 IWDG 配置（不启动看门狗）...")
    try:
        # 解锁写访问
        mem32[IWDG_KR] = 0x5555
        time.sleep_us(10)

        # 写预分频器 /64
        mem32[IWDG_PR] = 4
        print("  ✅ IWDG_PR 写入成功")

        # 等待 PVU 位清除
        for _ in range(100):
            if not (mem32[IWDG_SR] & 0x01):
                break
            time.sleep_us(100)

        # 写重载值
        mem32[IWDG_KR] = 0x5555
        mem32[IWDG_RLR] = 4095
        print("  ✅ IWDG_RLR 写入成功")

        # 等待 RVU 位清除
        for _ in range(100):
            if not (mem32[IWDG_SR] & 0x02):
                break
            time.sleep_us(100)

        print("  ✅ mem32 直接操作 IWDG 验证通过")
        print("  ⚠️  注意: 尚未写入 0xCCCC，WDT 未启动")
    except Exception as e:
        print("  ❌ IWDG 写入失败: %s" % e)


# ==================== 主流程 ====================
def main():
    print("=" * 50)
    print("  智能骑行头盔 — 硬件看门狗验证测试")
    print("  STM32F413ZH IWDG")
    print("=" * 50)

    gc.collect()
    print("  初始内存: %d bytes" % gc.mem_free())

    # Phase 1: 模块可用性
    avail = phase1_check_availability()

    if avail:
        # Phase 2: 喂狗测试（安全）
        print()
        # MicroPython 的 input() 行为: 如果无终端交互则超时返回空
        try:
            resp = input("按 Enter 开始 Phase 2 (WDT 喂狗测试 — 安全)...")
        except Exception:
            resp = ""
        phase2_feed_test()

        # Phase 3: 超时测试（会复位）
        print()
        print("Phase 3 会复位系统，如需跳过请在 3 秒内按 Ctrl+C")
        try:
            resp = input("按 Enter 开始 Phase 3 (会复位系统！) 或输入 skip 跳过: ")
        except Exception:
            resp = ""
        if resp.strip().lower() != 'skip':
            phase3_timeout_test()
    else:
        # Phase 4: 备选方案——mem32 直接寄存器
        print()
        print("⚠️  machine.WDT 不可用，尝试备选方案...")
        phase4_mem32_test()

    print()
    print("=" * 50)
    print("  测试完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
