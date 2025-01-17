import sys
import os
import optparse
import re
import unittest
from xml.sax import saxutils

from nose.pyversion import UNICODE_STRINGS
from nose.tools import eq_
from nose.plugins.xunit import Xunit, escape_cdata, id_split, Tee
from nose.exc import SkipTest
from nose.config import Config

def mktest():
    class TC(unittest.TestCase):
        def runTest(self):
            pass
    TC.__qualname__ = TC.__name__
    test = TC()
    return test

mktest.__test__ = False

time_taken = re.compile(r'\d\.\d\d')


class TestSplitId(unittest.TestCase):

    def check_id_split(self, cls, name):
        split = id_split('{}.{}'.format(cls, name))
        eq_(split[0], cls)
        eq_(split[1], name)

    def test_no_parenthesis(self):
        self.check_id_split("test_parset", "test_args")

    def test_no_dot_in_args(self):
        self.check_id_split("test_parset", "test_args(('x', [1, 2]),)")

    def test_dot_in_args(self):
        self.check_id_split("test_parset", "test_args(('x.y', 1),)")

    def test_grandchild_has_dot_in_args(self):
        self.check_id_split("test_grandparset.test_parset",
                            "test_args(('x.y', 1),)")

class TestOptions(unittest.TestCase):

    def test_defaults(self):
        parser = optparse.OptionParser()
        x = Xunit()
        x.add_options(parser, env={})
        (options, args) = parser.parse_args([])
        eq_(options.xunit_file, "nosetests.xml")

    def test_file_from_environ(self):
        parser = optparse.OptionParser()
        x = Xunit()
        x.add_options(parser, env={'NOSE_XUNIT_FILE': "kangaroo.xml"})
        (options, args) = parser.parse_args([])
        eq_(options.xunit_file, "kangaroo.xml")

    def test_file_from_opt(self):
        parser = optparse.OptionParser()
        x = Xunit()
        x.add_options(parser, env={})
        (options, args) = parser.parse_args(["--xunit-file=blagojevich.xml"])
        eq_(options.xunit_file, "blagojevich.xml")

class TestTee(unittest.TestCase):
    def setUp(self):
        self.orig_stderr = sys.stderr
        sys.stderr = Tee('utf-8', self.orig_stderr)

    def tearDown(self):
        sys.stderr = self.orig_stderr

    def test_tee_has_error_and_encoding_attributes(self):
        tee = Tee('utf-8', sys.stdout)
        self.assertTrue(hasattr(tee, 'encoding'))
        self.assertTrue(hasattr(tee, 'errors'))

    def test_tee_works_with_distutils_log(self):
        try:
            from distutils.log import Log, DEBUG
        except ImportError:
            raise SkipTest("distutils.log not available; skipping")

        l = Log(DEBUG)
        try:
            l.warn('Test')
        except Exception as e:
            self.fail(
                "Exception raised while writing to distutils.log: {}".format(e))


class TestXMLOutputWithXML(unittest.TestCase):
    def test_prefix_from_environ(self):
        parser = optparse.OptionParser()
        x = Xunit()
        x.add_options(parser, env={'NOSE_XUNIT_PREFIX_WITH_TESTSUITE_NAME': 'true'})
        (options, args) = parser.parse_args([])
        eq_(options.xunit_prefix_class, True)

    def test_prefix_from_opt(self):
        parser = optparse.OptionParser()
        x = Xunit()
        x.add_options(parser, env={})
        (options, args) = parser.parse_args(["--xunit-prefix-with-testsuite-name"])
        eq_(options.xunit_prefix_class, True)

class BaseTestXMLOutputWithXML(unittest.TestCase):
    def configure(self, args):
        parser = optparse.OptionParser()
        self.x.add_options(parser, env={})
        (options, args) = parser.parse_args(args)
        self.x.configure(options, Config())

    def setUp(self):
        self.xmlfile = os.path.abspath(
            os.path.join(os.path.dirname(__file__),
                            'support', 'xunit.xml'))
        self.x = Xunit()

        try:
            import xml.etree.ElementTree
        except ImportError:
            self.ET = False
        else:
            self.ET = xml.etree.ElementTree

    def tearDown(self):
        os.unlink(self.xmlfile)

    def get_xml_report(self):
        class DummyStream:
            pass
        self.x.report(DummyStream())
        f = open(self.xmlfile, 'rb')
        data = f.read()
        f.close()
        return data

class TestXMLOutputWithXMLAndPrefix(BaseTestXMLOutputWithXML):
    def setUp(self):
        super().setUp()

    def _assert_testcase_classname(self, expected_classname):
        test = mktest()
        self.x.beforeTest(test)
        self.x.addSuccess(test, (None,None,None))

        result = self.get_xml_report()
        print(result)

        if self.ET:
            tree = self.ET.fromstring(result)
            tc = tree.find("testcase")
            eq_(tc.attrib['classname'], expected_classname)
        else:
            # this is a dumb test for 2.4-
            assert ('<testcase classname="%s" name="runTest"' % expected_classname) in result

    def test_addSuccess_default(self):
        self.configure([
            "--with-xunit",
            "--xunit-file=%s" % self.xmlfile,
            "--xunit-prefix-with-testsuite-name"
        ])

        self._assert_testcase_classname('nosetests.test_xunit.TC')

    def test_addSuccess_custom(self):
        custom_testsuite_name = 'eartest'
        self.configure([
            "--with-xunit",
            "--xunit-file=%s" % self.xmlfile,
            "--xunit-testsuite-name=%s" % custom_testsuite_name,
            "--xunit-prefix-with-testsuite-name"
        ])

        self._assert_testcase_classname("%s.test_xunit.TC" % custom_testsuite_name)



class TestXMLOutputWithXML(BaseTestXMLOutputWithXML):
    def setUp(self):
        super().setUp()
        self.configure([
            "--with-xunit",
            "--xunit-file=%s" % self.xmlfile
        ])

    def test_addFailure(self):
        test = mktest()
        self.x.beforeTest(test)
        try:
            raise AssertionError("one is not 'equal' to two")
        except AssertionError:
            some_err = sys.exc_info()

        self.x.addFailure(test, some_err)

        result = self.get_xml_report()
        print(result)

        if self.ET:
            tree = self.ET.fromstring(result)
            eq_(tree.attrib['name'], "nosetests")
            eq_(tree.attrib['tests'], "1")
            eq_(tree.attrib['errors'], "0")
            eq_(tree.attrib['failures'], "1")
            eq_(tree.attrib['skip'], "0")

            tc = tree.find("testcase")
            eq_(tc.attrib['classname'], "test_xunit.TC")
            eq_(tc.attrib['name'], "runTest")
            assert time_taken.match(tc.attrib['time']), (
                        'Expected decimal time: %s' % tc.attrib['time'])

            err = tc.find("failure")
            eq_(err.attrib['type'], "{}.AssertionError".format(AssertionError.__module__))
            err_lines = err.text.strip().split("\n")
            eq_(err_lines[0], 'Traceback (most recent call last):')
            eq_(err_lines[-1], 'AssertionError: one is not \'equal\' to two')
            eq_(err_lines[-2], '    raise AssertionError("one is not \'equal\' to two")')
        else:
            # this is a dumb test for 2.4-
            assert '<?xml version="1.0" encoding="UTF-8"?>' in result
            assert '<testsuite name="nosetests" tests="1" errors="0" failures="1" skip="0">' in result
            assert '<testcase classname="test_xunit.TC" name="runTest"' in result
            assert '<failure type="exceptions.AssertionError"' in result
            assert "AssertionError: one is not 'equal' to two" in result
            assert "AssertionError(\"one is not 'equal' to two\")" in result
            assert '</failure></testcase></testsuite>' in result

    def test_addFailure_early(self):
        test = mktest()
        try:
            raise AssertionError("one is not equal to two")
        except AssertionError:
            some_err = sys.exc_info()

        # add failure without startTest, due to custom TestResult munging?
        self.x.addFailure(test, some_err)

        result = self.get_xml_report()
        print(result)

        if self.ET:
            tree = self.ET.fromstring(result)
            tc = tree.find("testcase")
            assert time_taken.match(tc.attrib['time']), (
                        'Expected decimal time: %s' % tc.attrib['time'])
        else:
            # this is a dumb test for 2.4-
            assert '<?xml version="1.0" encoding="UTF-8"?>' in result
            assert ('<testcase classname="test_xunit.TC" '
                    'name="runTest" time="0') in result

    def test_addError(self):
        test = mktest()
        self.x.beforeTest(test)
        try:
            raise RuntimeError("some error happened")
        except RuntimeError:
            some_err = sys.exc_info()

        self.x.addError(test, some_err)

        result = self.get_xml_report()
        print(result)

        if self.ET:
            tree = self.ET.fromstring(result)
            eq_(tree.attrib['name'], "nosetests")
            eq_(tree.attrib['tests'], "1")
            eq_(tree.attrib['errors'], "1")
            eq_(tree.attrib['failures'], "0")
            eq_(tree.attrib['skip'], "0")

            tc = tree.find("testcase")
            eq_(tc.attrib['classname'], "test_xunit.TC")
            eq_(tc.attrib['name'], "runTest")
            assert time_taken.match(tc.attrib['time']), (
                        'Expected decimal time: %s' % tc.attrib['time'])

            err = tc.find("error")
            eq_(err.attrib['type'], "{}.RuntimeError".format(RuntimeError.__module__))
            err_lines = err.text.strip().split("\n")
            eq_(err_lines[0], 'Traceback (most recent call last):')
            eq_(err_lines[-1], 'RuntimeError: some error happened')
            eq_(err_lines[-2], '    raise RuntimeError("some error happened")')
        else:
            # this is a dumb test for 2.4-
            assert '<?xml version="1.0" encoding="UTF-8"?>' in result
            assert '<testsuite name="nosetests" tests="1" errors="1" failures="0" skip="0">' in result
            assert '<testcase classname="test_xunit.TC" name="runTest"' in result
            assert '<error type="exceptions.RuntimeError"' in result
            assert 'RuntimeError: some error happened' in result
            assert '</error></testcase></testsuite>' in result

    def test_non_utf8_error(self):
        # See http://code.google.com/p/python-nose/issues/detail?id=395
        test = mktest()
        self.x.beforeTest(test)
        try:
            raise RuntimeError(chr(128)) # cannot encode as utf8
        except RuntimeError:
            some_err = sys.exc_info()
        self.x.addError(test, some_err)
        result = self.get_xml_report()
        print(repr(result))
        if self.ET:
            tree = self.ET.fromstring(result)
            tc = tree.find("testcase")
            err = tc.find("error")
            if UNICODE_STRINGS:
                eq_(err.attrib['message'],
                    '\x80')
            else:
                eq_(err.attrib['message'],
                    '\ufffd')
        else:
            # this is a dumb test for 2.4-
            assert 'RuntimeError: \xef\xbf\xbd' in result

    def test_addError_early(self):
        test = mktest()
        try:
            raise RuntimeError("some error happened")
        except RuntimeError:
            some_err = sys.exc_info()

        self.x.startContext(None)

        # call addError without startTest
        # which can happen if setup() raises an error
        self.x.addError(test, some_err)

        result = self.get_xml_report()
        print(result)

        if self.ET:
            tree = self.ET.fromstring(result)
            tc = tree.find("testcase")
            assert time_taken.match(tc.attrib['time']), (
                        'Expected decimal time: %s' % tc.attrib['time'])
        else:
            # this is a dumb test for 2.4-
            assert '<?xml version="1.0" encoding="UTF-8"?>' in result
            assert ('<testcase classname="test_xunit.TC" '
                    'name="runTest" time="0') in result

    def test_addSuccess(self):
        test = mktest()
        self.x.beforeTest(test)
        self.x.addSuccess(test, (None,None,None))

        result = self.get_xml_report()
        print(result)

        if self.ET:
            tree = self.ET.fromstring(result)
            eq_(tree.attrib['name'], "nosetests")
            eq_(tree.attrib['tests'], "1")
            eq_(tree.attrib['errors'], "0")
            eq_(tree.attrib['failures'], "0")
            eq_(tree.attrib['skip'], "0")

            tc = tree.find("testcase")
            eq_(tc.attrib['classname'], "test_xunit.TC")
            eq_(tc.attrib['name'], "runTest")
            assert time_taken.match(tc.attrib['time']), (
                        'Expected decimal time: %s' % tc.attrib['time'])
        else:
            # this is a dumb test for 2.4-
            assert '<?xml version="1.0" encoding="UTF-8"?>' in result
            assert '<testsuite name="nosetests" tests="1" errors="0" failures="0" skip="0">' in result
            assert '<testcase classname="test_xunit.TC" name="runTest"' in result
            assert '</testsuite>' in result

    def test_addSuccess_early(self):
        test = mktest()
        # call addSuccess without startTest
        # which can happen (?) -- did happen with JsLint plugin
        self.x.addSuccess(test, (None,None,None))

        result = self.get_xml_report()
        print(result)

        if self.ET:
            tree = self.ET.fromstring(result)
            tc = tree.find("testcase")
            assert time_taken.match(tc.attrib['time']), (
                        'Expected decimal time: %s' % tc.attrib['time'])
        else:
            # this is a dumb test for 2.4-
            assert '<?xml version="1.0" encoding="UTF-8"?>' in result
            assert ('<testcase classname="test_xunit.TC" '
                    'name="runTest" time="0') in result
