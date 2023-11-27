import unittest
from nose.config import Config
from nose.plugins.builtin import TestId
from unittest import mock

class TestTestIdPlugin(unittest.TestCase):

    def test_default_id_file_is_in_working_dir(self):
        tid = TestId()
        c = Config()
        opt = mock.Bucket()
        opt.testIdFile = '.noseids'
        tid.configure(opt, c)
        print(tid.idfile)
        assert tid.idfile.startswith(c.workingDir), \
               "{} is not under {}".format(tid.idfile, c.workingDir)


if __name__ == '__main__':
    unittest.main()
