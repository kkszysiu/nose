import os
import sys

here = os.path.dirname(__file__)
flag = os.path.join(here, 'shared_flag')

_multiprocess_shared_ = 1

def _log(val):
    ff = open(flag, 'a+')
    ff.write(val)
    ff.write("\n")
    ff.close()


def _clear():
    if os.path.isfile(flag):
        os.unlink(flag)


def logged():
    flag_file = open(flag)
    try:
        lines = [line for line in flag_file]
    finally:
        flag_file.close()
    return lines


def setup():
    print("setup called", file=sys.stderr)
    _log('setup')


def teardown():
    print("teardown called", file=sys.stderr)
    _clear()


def test_a():
    assert len(logged()) == 1, "len(%s) !=1" % called


def test_b():
    assert len(logged()) == 1, "len(%s) !=1" % called


class TestMe:
    def setup_class(cls):
        cls._setup = True
    setup_class = classmethod(setup_class)

    def test_one(self):
        assert self._setup, "Class was not set up"
