from machine import Pin, Timer

# 创建 LED 引脚对象
led = Pin("LED_BLUE", Pin.OUT)

# 创建 Timer 对象
timer = Timer(-1)

# 定时器回调函数
def timer_callback(t):
    led.value(not led.value())

# 初始化定时器
# period=500 表示 500ms 触发一次
# mode=Timer.PERIODIC 表示周期触发
timer.init(
    period=500,
    mode=Timer.PERIODIC,
    callback=timer_callback
)
timer.deinit()