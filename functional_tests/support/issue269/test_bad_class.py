class TestCrashy:
    def __init__(self):
        raise Exception("pow")
    def test_whatever(self):
        pass
