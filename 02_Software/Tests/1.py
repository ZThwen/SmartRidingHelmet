hex_str = "7b2261223a226e6176222c2264223a7b22646972223a22222c2264697374223a33312c22726f6164223a22227d7d"
try:
    decoded = bytes.fromhex(hex_str).decode('utf-8')
    print("hex 解码成功:", decoded)
except Exception as e:
    print("hex 解码失败:", e)

# 测试 _thread
try:
    import _thread
    print("_thread 可用")
except Exception as e:
    print("_thread 不可用:", e)