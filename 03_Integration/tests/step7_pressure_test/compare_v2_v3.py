"""
brief 对比 stress_test_30min_active.py (V2) 和 stress_test_30min_v3.py (V3) 的 OPS_TIMELINE
usage  python compare_v2_v3.py
"""

import ast
import os

DIR = os.path.dirname(os.path.abspath(__file__))
V2_FILE = os.path.join(DIR, "stress_test_30min_active.py")
V3_FILE = os.path.join(DIR, "stress_test_30min_v3.py")


def _extract_ops_timeline(filepath):
    """从 .py 文件中提取 OPS_TIMELINE 列表"""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    # 找到 OPS_TIMELINE = [ 和匹配的 ]
    start = source.find("OPS_TIMELINE = [")
    if start == -1:
        raise ValueError("OPS_TIMELINE not found")
    start = source.index("[", start)

    # 找到匹配的 ] (处理嵌套括号)
    depth = 0
    end = start
    for i in range(start, len(source)):
        if source[i] == "[":
            depth += 1
        elif source[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if depth != 0:
        raise ValueError("Unmatched brackets in OPS_TIMELINE")

    list_str = source[start:end]

    # 定义用于 eval 的占位符常量
    ns = {
        "POWER_STATE_ACTIVE": "ACTIVE",
        "POWER_STATE_SUSPENDED": "SUSPENDED",
        "POWER_STATE_EMERGENCY": "EMERGENCY",
        "True": True,
        "False": False,
        "None": None,
    }

    # ast.literal_eval 不支持变量引用, 需要 compile + eval
    # 安全方式: compile 表达式然后用受限 namespace eval
    code = compile(list_str, "<string>", "eval", flags=ast.PyCF_ONLY_AST)

    # 自定义 eval: 遍历 AST, 将 Name 节点解析为 namespace 中的值
    class _NameResolver(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id in ns:
                if isinstance(ns[node.id], str):
                    return ast.Constant(value=ns[node.id])
                return ast.Constant(value=ns[node.id])
            return node

    code = _NameResolver().visit(code)
    ast.fix_missing_locations(code)
    compiled = compile(code, "<string>", "eval")
    return eval(compiled, {"__builtins__": {}}, ns)


def _classify(op_type, payload):
    """映射 operation_type 到人类可读的分类名"""
    CATEGORIES = {
        "ble_ctrl":  "控制-灯光/音量/电源/BLE",
        "voice":     "语音-查询",
        "wake":      "语音-唤醒",
        "vo_sleep":  "语音-睡眠",
        "nav":       "导航-方向",
        "alarm":     "控制-报警",
        "collision": "报警-碰撞",
        "sos_btn":   "报警-SOS按钮",
        "gps_lost":  "报警-GPS丢失",
        "bat_low":   "报警-低电量",
        "bat_crit":  "报警-电量危急",
        "bat_ready": "电池-注入",
        "power":     "电源-切换",
        "hr_alert":  "心率-告警",
        "set_phone": "SMS-配置",
    }
    return CATEGORIES.get(op_type, "未知-%s" % op_type)


def main():
    v2_ops = _extract_ops_timeline(V2_FILE)
    v3_ops = _extract_ops_timeline(V3_FILE)

    print("=" * 72)
    print("  OPS_TIMELINE 对比: V2 (stress_test_30min_active) vs V3 (stress_test_30min_v3)")
    print("=" * 72)

    # ---- 1. V2 操作统计 ----
    v2_counts = {}
    for (t, op_type, payload) in v2_ops:
        v2_counts[op_type] = v2_counts.get(op_type, 0) + 1

    print("\n>>> V2 操作统计 (%d 条):" % len(v2_ops))
    print("  %-18s %-30s %s" % ("操作类型", "分类", "次数"))
    print("  " + "-" * 60)
    for op_type in sorted(v2_counts.keys(), key=lambda k: v2_counts[k], reverse=True):
        print("  %-18s %-30s %d" % (op_type, _classify(op_type, None), v2_counts[op_type]))

    # ---- 2. V3 操作统计 ----
    v3_counts = {}
    for (t, op_type, payload) in v3_ops:
        v3_counts[op_type] = v3_counts.get(op_type, 0) + 1

    print("\n>>> V3 操作统计 (%d 条):" % len(v3_ops))
    print("  %-18s %-30s %s" % ("操作类型", "分类", "次数"))
    print("  " + "-" * 60)
    for op_type in sorted(v3_counts.keys(), key=lambda k: v3_counts[k], reverse=True):
        print("  %-18s %-30s %d" % (op_type, _classify(op_type, None), v3_counts[op_type]))

    # ---- 3. V3 比 V2 多的操作类型 ----
    v3_only = set(v3_counts.keys()) - set(v2_counts.keys())
    if v3_only:
        print("\n>>> V3 新增操作类型:")
        for op_type in sorted(v3_only):
            print("  + %-18s (%s)" % (op_type, _classify(op_type, None)))

    # ---- 4. 操作次数差异 ----
    all_types = sorted(set(list(v2_counts.keys()) + list(v3_counts.keys())))
    print("\n>>> 操作次数差异 (V2 vs V3):")
    print("  %-18s %8s %8s %8s" % ("操作类型", "V2", "V3", "差值"))
    print("  " + "-" * 50)
    total_v2 = 0
    total_v3 = 0
    for op_type in all_types:
        v2_n = v2_counts.get(op_type, 0)
        v3_n = v3_counts.get(op_type, 0)
        diff = v3_n - v2_n
        sign = "+" if diff > 0 else ""
        print("  %-18s %8d %8d %8s%d" % (op_type, v2_n, v3_n, sign, diff))
        total_v2 += v2_n
        total_v3 += v3_n

    print("  " + "-" * 50)
    print("  %-18s %8d %8d %8s%d" % ("总计", total_v2, total_v3,
                                       "+" if total_v3 > total_v2 else "",
                                       total_v3 - total_v2))

    # ---- 5. 操作密度对比 ----
    print("\n>>> 操作密度对比 (1800s = 30min):")
    print("  V2 总计: %d 操作, 平均间隔 %.1fs, 密度 %.1f 次/分" % (
        total_v2, 1800 / total_v2, total_v2 * 60 / 1800))
    print("  V3 总计: %d 操作, 平均间隔 %.1fs, 密度 %.1f 次/分" % (
        total_v3, 1800 / total_v3, total_v3 * 60 / 1800))

    # ---- 6. 时间点分布 ----
    print("\n>>> V3 新增操作时间点列表 (不在 V2 中的):")
    v2_time_types = set((t, op_type) for (t, op_type, p) in v2_ops)
    v3_time_types = set((t, op_type) for (t, op_type, p) in v3_ops)
    new_ops = sorted(v3_time_types - v2_time_types, key=lambda x: x[0])
    for (t, op_type) in new_ops:
        # 找到 payload
        payload = ""
        for (tt, ot, p) in v3_ops:
            if tt == t and ot == op_type:
                payload = str(p)[:50] if p is not None else ""
                break
        print("  t=%4ds  %-12s %s" % (t, op_type, payload))

    print("\n" + "=" * 72)
    print("  对比完成")


if __name__ == "__main__":
    main()
