class ButtonRowFulledError(Exception):
    def __init__(self, message: str = None):
        super().__init__(message)


class NotSupportError(NotImplementedError):
    def __init__(self, message: str = None):
        super().__init__(message)
