"""Unit test utilities.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import base64
import difflib
import mox
import pprint
import re
import os
import rfc822
import StringIO
import urllib2
import urlparse
import wsgiref

import webapp2

from google.appengine.datastore import datastore_stub_util
from google.appengine.ext import db
from google.appengine.ext import testbed


def get_task_params(task):
  """Parses a task's POST body and returns the query params in a dict.
  """
  params = urlparse.parse_qs(base64.b64decode(task['body']))
  params = dict((key, val[0]) for key, val in params.items())
  return params


class HandlerTest(mox.MoxTestBase):
  """Base test class for webapp2 request handlers.

  Uses App Engine's testbed to set up API stubs:
  http://code.google.com/appengine/docs/python/tools/localunittesting.html

  Attributes:
    application: WSGIApplication
    handler: webapp2.RequestHandler
  """

  class UrlopenResult(object):
    """A fake urllib2.urlopen() result object. Also works for urlfetch.fetch().
    """
    def __init__(self, status_code, content, headers={}):
      self.status_code = status_code
      self.content = content
      self.headers = headers

    def read(self):
      return self.content

    def getcode(self):
      return self.status_code

    def info(self):
      return rfc822.Message(StringIO.StringIO(
          '\n'.join('%s: %s' % item for item in self.headers.items())))


  def setUp(self):
    super(HandlerTest, self).setUp()

    os.environ['APPLICATION_ID'] = 'app_id'
    self.current_user_id = '123'
    self.current_user_email = 'foo@bar.com'

    self.testbed = testbed.Testbed()
    self.testbed.setup_env(user_id=self.current_user_id,
                           user_email=self.current_user_email)
    self.testbed.activate()

    hrd_policy = datastore_stub_util.PseudoRandomHRConsistencyPolicy(probability=.5)
    self.testbed.init_datastore_v3_stub(consistency_policy=hrd_policy)
    self.testbed.init_taskqueue_stub(root_path='.')
    self.testbed.init_user_stub()

    self.mox.StubOutWithMock(urllib2, 'urlopen')

    # unofficial API, whee! this is so we can call
    # TaskQueueServiceStub.GetTasks() in tests. see
    # google/appengine/api/taskqueue/taskqueue_stub.py
    self.taskqueue_stub = self.testbed.get_stub('taskqueue')

    self.request = webapp2.Request.blank('/')
    self.response = webapp2.Response()
    self.handler = webapp2.RequestHandler(self.request, self.response)

  def tearDown(self):
    self.testbed.deactivate()
    super(HandlerTest, self).tearDown()

  def expect_urlopen(self, expected_url, response, status=200, **kwargs):
    """Stubs out urllib2.open() and sets up an expected call.

    Args:
      expected_url: string, regex or mox.Comparator
      response: string
      status: int, HTTP response code
    """
    urllib2.urlopen(expected_url, timeout=999).AndReturn(
      self.UrlopenResult(status, response))

  def assert_entities_equal(self, a, b, ignore=frozenset(), keys_only=False,
                            in_order=False):
    """Asserts that a and b are equivalent entities or lists of entities.

    ...specifically, that they have the same property values, and if they both
    have populated keys, that their keys are equal too.

    Args:
      a, b: db.Model instances or lists of instances
      ignore: sequence of strings, property names not to compare
      keys_only: boolean, if True only compare keys
      in_order: boolean. If False, all entities must have keys.
    """
    if not isinstance(a, (list, tuple, db.Query)):
      a = [a]
    if not isinstance(b, (list, tuple, db.Query)):
      b = [b]

    if not in_order:
      key_fn = lambda e: e.key()
      a = list(sorted(a, key=key_fn))
      b = list(sorted(b, key=key_fn))

    self.assertEqual(len(a), len(b),
                     'Different lengths:\n expected %s\n actual %s' % (a, b))

    for x, y in zip(a, b):
      try:
        self.assertEqual(x.key().to_path(), y.key().to_path())
      except (db.BadKeyError, db.NotSavedError):
        if keys_only:
          raise

      if not keys_only:
        self.assert_equals(x.properties(), y.properties())

  def entity_keys(self, entities):
    """Returns a list of keys for a list of entities.
    """
    return [e.key() for e in entities]

  def assert_equals(self, expected, actual):
    """Pinpoints individual element differences in lists and dicts.

    Ignores order in lists.
    """
    try:
      self._assert_equals(expected, actual)
    except AssertionError, e:
      raise AssertionError("""\
%s
Expected value: %s
Actual value:   %s""" % (''.join(e.args),
                         pprint.pformat(expected),
                         pprint.pformat(actual)))

  def _assert_equals(self, expected, actual):
    """Recursive helper for assert_equals().
    """
    key = None

    try:
      if isinstance(expected, re._pattern_type):
        if not re.match(expected, actual):
          self.fail("%r doesn't match %s" % (expected, actual))
      elif isinstance(expected, dict) and isinstance(actual, dict):
        for key in set(expected.keys()) | set(actual.keys()):
          self._assert_equals(expected.get(key), actual.get(key))
      elif isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
        expected = sorted(list(expected))
        actual = sorted(list(actual))
        for key, (e, a) in enumerate(zip(expected, actual)):
          self._assert_equals(e, a)
      elif (isinstance(expected, basestring) and isinstance(actual, basestring) and
            '\n' in expected):
        self.assert_multiline_equals(expected, actual)
      else:
        self.assertEquals(expected, actual)

    except AssertionError, e:
      # fill in where this failure came from. this recursively builds,
      # backwards, all the way up to the root.
      args = ('[%s] ' % key if key is not None else '') + ''.join(e.args)
      raise AssertionError(args)

  def assert_multiline_equals(self, expected, actual):
    """Compares two multi-line strings and reports a diff style output."""
    if expected != actual:
      self.fail(''.join(difflib.Differ().compare(expected.splitlines(True),
                                                 actual.splitlines(True))))
