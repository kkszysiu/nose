def test_evens():
    yield check_even_cls

class Test:
    def test_evens(self):
        yield check_even_cls

class Check:
    def __call__(self):
        pass

check_even_cls = Check()
