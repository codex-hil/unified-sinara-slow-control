class ControlError(Exception):
    def __init__(self, code, message, *, uncertain=False):
        self.code, self.uncertain = code, uncertain
        super().__init__(message)


class ValidationError(ControlError):
    def __init__(self, message):
        super().__init__('INVALID_CONFIG', message)
