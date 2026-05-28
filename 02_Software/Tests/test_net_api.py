"""
brief 测试 net 模块 API
note 单独验证 net.csqQueryPoll() 和 net.getState() 是否正常工作
"""
import net
import time

print("=" * 50)
print("net 模块 API 测试")
print("=" * 50)

# 测试 1：CSQ 信号强度
print("\n[测试 1] net.csqQueryPoll()")
print("-" * 30)
for i in range(5):
    csq = net.csqQueryPoll()
    print(f"  第 {i+1} 次: csq = {csq}", end="")
    if csq == -1:
        print(" (API 失败)")
    elif csq == 99:
        print(" (异常值 99)")
    elif csq == 0:
        print(" (返回 0)")
    elif 1 <= csq <= 31:
        print(f" (信号强度 {csq}/31)")
    else:
        print(f" (未知值)")
    time.sleep(1)

# 测试 2：网络注册状态
print("\n[测试 2] net.getState()")
print("-" * 30)
try:
    state = net.getState()
    print(f"  getState() 返回类型: {type(state)}")
    print(f"  返回值: {state}")
    if state != -1 and len(state) >= 2:
        voice_state = state[0]
        data_state = state[1]
        print(f"  语音网络状态码: {voice_state[0]}", end="")
        # 0=未注册 1=已注册 2=搜索中 3=被拒 5=漫游
        status_map = {0: "未注册", 1: "已注册(本地)", 2: "搜索中", 3: "被拒", 5: "已注册(漫游)"}
        print(f" ({status_map.get(voice_state[0], '未知')})")
        print(f"  数据网络状态码: {data_state[0]}", end="")
        print(f" ({status_map.get(data_state[0], '未知')})")
except Exception as e:
    print(f"  getState() 异常: {e}")

# 测试 3：获取小区信息
print("\n[测试 3] net.getCellInfo()")
print("-" * 30)
try:
    cell_info = net.getCellInfo()
    print(f"  getCellInfo() 返回类型: {type(cell_info)}")
    print(f"  返回值: {cell_info}")
except Exception as e:
    print(f"  getCellInfo() 异常: {e}")

# 测试 4：net 模块有哪些属性
print("\n[测试 4] dir(net)")
print("-" * 30)
attrs = [a for a in dir(net) if not a.startswith('_')]
print(f"  net 模块属性: {attrs}")

print("\n" + "=" * 50)
print("测试完成")
print("=" * 50)
