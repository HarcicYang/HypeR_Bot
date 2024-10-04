import subprocess
import threading
import queue


# 定义一个函数，用于从子进程中读取输出并放入队列
def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()


# 创建 Popen 对象，启动子进程
# 这里以 'ping www.google.com' 为例
process = subprocess.Popen(['ping', 'cn.bing.com'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

for i in process.stdout:
    print(i)
