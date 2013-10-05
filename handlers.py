#!/usr/bin/env python
"""Request handler utility classes.

Includes classes for serving templates with common variables and XRD[S] and JRD
files like host-meta and friends.
"""

__author__ = 'Ryan Barrett <webutil@ryanb.org>'

import logging
import os
import urlparse

import appengine_config
import webapp2

from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template

# Included in most static HTTP responses.
BASE_HEADERS = {
  'Cache-Control': 'max-age=300',
  'X-XRDS-Location': 'https://%s/.well-known/host-meta.xrds' %
    appengine_config.HOST,
  'Access-Control-Allow-Origin': '*',
  }


class TemplateHandler(webapp2.RequestHandler):
  """Renders and serves a template based on class attributes.

  Subclasses must override template_file() and may also override template_vars()
  and content_type().
  """

  def template_file(self):
    """Returns the string template file path."""
    raise NotImplementedError()

  def template_vars(self):
    """Returns a dict of template variable string keys and values."""
    return {}

  def content_type(self):
    """Returns the string content type."""
    return 'text/html'

  def force_to_sequence(self):
    """Returns variables that should be coerced to sequences if necessary."""
    return set()

  def get(self):
    self.response.headers['Content-Type'] = self.content_type()
    # can't update() because wsgiref.headers.Headers doesn't have it.
    for key, val in BASE_HEADERS.items():
      self.response.headers[key] = val

    vars = {'host': appengine_config.HOST}

    # add query params. use a list for params with multiple values.
    for key in self.request.params:
      values = self.request.params.getall(key)
      if len(values) == 1:
        values = values[0]
      vars[key] = values

    vars.update(self.template_vars())

    for key in self.force_to_sequence():
      val = vars.get(key, None)
      if val is not None and not isinstance(val, (list, tuple)):
        vars[key] = (val,)

    self.response.out.write(template.render(self.template_file(), vars))


class XrdOrJrdHandler(TemplateHandler):
  """Renders and serves an XRD or JRD file.

  JRD is served if the request path ends in .json, or the query parameters
  include 'format=json', or the request headers include
  'Accept: application/json'.

  Subclasses must override template_prefix().
  """
  def content_type(self):
    return 'application/json' if self.is_jrd() else 'application/xrd+xml'

  def template_file(self):
    return self.template_prefix() + ('.jrd' if self.is_jrd() else '.xrd')

  def is_jrd(self):
    """Returns True if JRD should be served, False if XRD."""
    return (os.path.splitext(self.request.path)[1] == '.json' or
            self.request.get('format') == 'json' or
            self.request.headers.get('Accept') == 'application/json')


class HostMetaHandler(XrdOrJrdHandler):
  """Renders and serves the /.well-known/host-meta file.
  """
  def template_prefix(self):
    return 'templates/host-meta'


class HostMetaXrdsHandler(TemplateHandler):
  """Renders and serves the /.well-known/host-meta.xrds XRDS-Simple file.
  """
  def content_type(self):
    return 'application/xrds+xml'

  def template_file(self):
    return 'templates/host-meta.xrds'


HOST_META_ROUTES = [
  ('/\.well-known/host-meta(?:\.json)?', HostMetaHandler),
  ('/\.well-known/host-meta.xrds', HostMetaXrdsHandler),
  ]
