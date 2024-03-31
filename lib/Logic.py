import inspect
import asyncio


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
