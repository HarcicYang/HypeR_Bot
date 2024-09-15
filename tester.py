import sys


class PrivateMethodError(Exception):
    pass


def private(func):
    def wrapper(self, *args, **kwargs):
        # 获取当前帧的信息
        current_frame = sys._getframe(1)

        # 检查当前帧的局部变量，寻找self对象，确认调用者是否是同一个类的实例
        caller_locals = current_frame.f_locals
        if 'self' in caller_locals and caller_locals['self'].__class__ == self.__class__:
            pass
        else:
            raise PrivateMethodError()

        return func(self, *args, **kwargs)

    return wrapper


class MyClass:
    @private
    def method_a(self):
        print("Method A is called.")

    # @is_called_within_class
    def method_b(self):
        print("Method B is calling Method A.")
        self.method_a()


# 创建类的实例并调用方法
instance = MyClass()
instance.method_b()
