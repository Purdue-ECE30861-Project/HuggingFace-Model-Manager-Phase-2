from src.external_contracts import HealthComponentCollection


class HealthAccessor:
    def __init__(self):
        pass

    def is_alive(self) -> bool:
        raise NotImplementedError()

    def component_health(self, window: int, include_timeline: bool) -> HealthComponentCollection:
        raise NotImplementedError
