"""
brief MQTT 连接最小诊断测试
note 直接调用 umqtt.robust，不经过 MQTTDriver 封装
执行: 上传到板子运行
"""
from umqtt.robust import MQTTClient
import time

BROKER = "101.37.104.185"
PORT = 49687
CLIENT_ID = "66ccff"
USER = "quectel"
PASSWORD = "12345678"

print("")
print("=== MQTT Connect Test ===")
print("Broker: %s:%s" % (BROKER, PORT))
print("Client: %s" % CLIENT_ID)
print("")

print("[1] Creating client...")
try:
    c = MQTTClient(CLIENT_ID, BROKER, port=PORT,
                   user=USER, password=PASSWORD, keepalive=60)
    print("  OK client created")
except Exception as e:
    print("  FAIL: %s" % e)

print("[2] Connecting...")
try:
    c.connect()
    print("  OK connected to broker")
except Exception as e:
    print("  FAIL: %s" % e)

time.sleep(1)

print("[3] Publishing to helmet/data...")
try:
    c.publish(b"helmet/data", b'{"test":1,"source":"diag"}')
    print("  OK published")
except Exception as e:
    print("  FAIL: %s" % e)

time.sleep(1)

print("[4] Checking messages...")
try:
    c.check_msg()
    print("  OK check_msg done")
except Exception as e:
    print("  FAIL: %s" % e)

print("")
print("Check ConnectLab for the test message.")
print("================================")
