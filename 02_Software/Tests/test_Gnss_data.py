from quectel import GNSS
gnss = GNSS()
gnss.start()

import time
time.sleep(3)  # 等一会儿让 GNSS 搜星

loc = gnss.get_location()
if loc:
    print("返回类型:", type(loc))
    print("完整数据:", loc)           # 看全部内容
    print("所有键:", loc.keys())      # 看有哪些字段
else:
    print("暂无定位，实际返回值:", repr(loc))