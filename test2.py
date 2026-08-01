import ctypes
import ctypes.util
from ctypes import c_char_p, c_int, c_void_p

# 加载共享库 (根据文件路径修改)
lib = ctypes.CDLL("wrapper.node")  # 使用正确的路径和文件扩展名

# 定义函数签名
# 假设函数是 void some_function(int, std::string&, void*, const std::string&, const void*)
# Python 中没有 std::string 类型，所以我们用 c_char_p 来代替

lib.some_function.argtypes = [c_int, c_char_p, c_void_p, c_char_p, c_void_p]
lib.some_function.restype = None  # 函数返回类型是 void

# 准备参数
param1 = 42  # 整数参数
param2 = b"Hello, World!"  # 字符串参数 (转换为字节序列)
param3 = None  # 示例指针参数（可以是有效的内存地址）
param4 = b"Constant String"  # 常量字符串
param5 = None  # 示例常量指针参数

# 调用函数
lib.some_function(param1, param2, param3, param4, param5)
