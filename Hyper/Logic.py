from Hyper import Logger
import traceback


class Cacher:
    def __init__(self, cache_time: int = 10):
        self.cache_time: int = cache_time
        self.cached: dict = {}

    def cache(self, func):
        def wrapper(*args, **kwargs):
            if str(kwargs) not in self.cached:
                ret = func(*args, **kwargs)
                self.cached[str(kwargs)] = ret
                if len(self.cached) >= self.cache_time:
                    self.cached = {}
                return ret
            else:
                return self.cached[str(kwargs)]

        return wrapper

    def cache_async(self, func):
        async def wrapper(*args, **kwargs):
            if str(kwargs) not in self.cached:
                ret = await func(*args, **kwargs)
                self.cached[str(kwargs)] = ret
                if len(self.cached) >= self.cache_time:
                    self.cached = {}
                return ret
            else:
                return self.cached[str(kwargs)]

        return wrapper


class ErrorHandler:
    def __init__(self, level=Logger.levels.ERROR, retries: int = 0):
        self.level = level
        self.logger = Logger.Logger()
        self.retries = retries

    def handle(self, func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except:
                self.logger.log(f"出现错误：\n{str(traceback.format_exc())}", level=self.level)

        return wrapper

    def handle_async(self, func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except:
                self.logger.log(f"出现错误：\n{str(traceback.format_exc())}", level=self.level)

        return wrapper

    def auto_retry(self, func):
        def wrapper(*args, **kwargs):
            retried = 0
            while retried < self.retries:
                retried += 1
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    self.logger.log(f"出现错误：\n{str(e)}, 正在重试...", level=self.level)
            self.logger.log(f"错误在{retried}次重试后失败", level=self.level)

        return wrapper

    def auto_retry_async(self, func):
        async def wrapper(*args, **kwargs):
            retried = 0
            while retried < self.retries:
                retried += 1
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    self.logger.log(f"出现错误：\n{str(e)}, 正在重试...", level=self.level)
            self.logger.log(f"错误在{retried}次重试后失败", level=self.level)

        return wrapper
