from datetime import datetime, timedelta
from typing import Iterable, List
from velib_rx.type_variables import T


class StopWatch:

    def __init__(self) -> None:
        super().__init__()

        self._time = datetime.now()

    def lap(self) -> timedelta:
        now = datetime.now()
        dt = now - self._time
        self._time = now
        return dt


def to_list(iterable: Iterable[T]) -> List[T]:
    return [t for t in iterable]


def memoize(fn):
    _memo_attr_name = '_memo_' + fn.__name__

    def _memo(self):
        if not hasattr(self, _memo_attr_name):
            setattr(self, _memo_attr_name, fn(self))
        return getattr(self, _memo_attr_name)

    return _memo


def matches(x: str, glob_prefix: str) -> bool:
    if glob_prefix.endswith('*'):
        return x.startswith(glob_prefix[:-1])
    else:
        return x == glob_prefix



class Record:

    @memoize
    def __str__(self):
        return self.__class__.__name__ + ' ' + str(vars(self))

    def __repr__(self):
        return self.__str__()

    @memoize
    def __hash__(self):
        return self.__str__().__hash__()

    def __eq__(self, other):
        # TODO: improve, iterable vars are not correctly handled
        return str(other) == str(self)

    # make readonly
    def __setattr__(self, key, value):
        if hasattr(self, key):  # disallow redefining
            raise ValueError(key + ' is read-only')

        super(Record, self).__setattr__(key, value)

    def __delattr__(self, name: str) -> None:
        if hasattr(self, name):
            raise ValueError(name + ' is read-only')


class MutableRecord:

    def __str__(self):
        return self.__class__.__name__ + ' ' + str(vars(self))

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return self.__str__().__hash__()

    def __eq__(self, other):
        # TODO: improve, iterable vars are not correctly handled
        return str(other) == str(self)




