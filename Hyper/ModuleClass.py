from Hyper import Events, Listener, Logger, Configurator

import dataclasses

config = Configurator.cm.get_cfg()
logger = Logger.Logger()
logger.set_level(config.log_level)


@dataclasses.dataclass
class ModuleInfo:
    is_hidden: bool = True
    module_name: str = "None"
    author: str = "None"
    version: str = "0.0"
    desc: str = "None"
    helps: str = "None"


class Module:
    def __init__(self, actions: Listener.Actions, event):
        self.actions = actions
        self.event = event

    async def handle(self):
        pass

    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo()


class InnerHandler:
    def __init__(self, module: Module, allowed: list):
        self.module = module
        self.allowed = allowed


register_modules: list[InnerHandler] = []


class ModuleRegister:
    @staticmethod
    def register(*args):
        def decorator(cls):
            if len(args) < 1:
                allowed = [Events.Event]
            else:
                allowed = list(args)

            from typing import Union

            def init(self, actions: Listener.Actions, event: Union[*allowed]):
                self.actions = actions
                self.event = event

            cls.__init__ = init

            register_modules.append(InnerHandler(cls, allowed))

            return cls

        return decorator

    @staticmethod
    def get_registered() -> list:
        return register_modules
