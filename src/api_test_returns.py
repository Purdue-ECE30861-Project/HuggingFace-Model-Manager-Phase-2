from typing import TypeVar, Generic
from abc import ABC, abstractmethod


T = TypeVar("T")
IS_MOCK_TESTING = True


class TestReturn(Generic[T], ABC):
    @abstractmethod
    def get_mock_value(self) -> T:
        pass

    def __call__(self) -> T | None:
        if IS_MOCK_TESTING:
            return self.get_mock_value()
        else:
            return None
