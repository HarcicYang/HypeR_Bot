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
    def __init__(self, level=Logger.levels.ERROR):
        self.level = level
        self.logger = Logger.Logger()

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
