from Hyper import Manager, Listener, Logger, Configurator

config = Configurator.Config("config.json")
logger = Logger.Logger()
logger.set_level(config.log_level)


class Module:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
        pass


class InnerHandler:
    def __init__(self, module: Module, allowed_post_types: list):
        self.module = module
        self.allowed_post_types = allowed_post_types


register_modules: list[InnerHandler] = []


class ModuleRegister:
    @staticmethod
    def register(*args):
        def decorator(func):
            if len(args) not in [1, 2]:
                raise TypeError("register() expects either 1 or 2 arguments")
            allowed_post_types = args[0] if len(args) == 1 else ["message", "notice", "request"]
            register_modules.append(InnerHandler(func, allowed_post_types))

            return func

        return decorator

    @staticmethod
    def get_registered() -> list:
        return register_modules
