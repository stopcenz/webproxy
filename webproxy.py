#!/usr/bin/env python
# -*- coding: utf-8 -*- 

# GAE-based webproxy server. V.7
# License: CC0 1.0

# -----------------------------------------------------------------------------
#
# Изменив параметры ниже вы можете перенастроить 
# ваш проксисервер на работу с другим узлом
#
# -----------------------------------------------------------------------------
# Введите здесь имя хоста. Его страницы будет транслировать ваш прокси.
# Например: "kinozal.tv"

host_name = "kinozal.tv"

# -----------------------------------------------------------------------------
# Тип соединения с указанным выше хостом.
# Допустимы только значения "http" или "https".

host_scheme = "http"

# -----------------------------------------------------------------------------
# Включает/выключает использование защищенного соединения с проксисервером. 
# Если страницы хоста открываются с ошибками или не работает авторизация 
# попробуйте выключить (0) эту опцию.
# Допустимы значения 0 или 1 (без кавычек).

encrypted_connection = 0

# -----------------------------------------------------------------------------
# Удаляемые из ответа сервера заголовки. Указываются в нижнем регистре.

skip_headers = [
  "content-security-policy", 
  "x-content-security-policy", 
  "content-security-policy-report-only", 
  "x-content-security-policy-report-only",
  "x-webkit-csp",
  "x-webkit-csp-report-only",
  "public-key-pins", 
  "public-key-pins-report-only"]

# -----------------------------------------------------------------------------

import webapp2
import logging
import re
import urllib
from google.appengine.api import urlfetch

class MainHandler(webapp2.RequestHandler):
  def head(self):    self.get()
  def post(self):    self.get()
  def put(self):     self.get()
  def patch(self):   self.get()
  def delete(self):  self.get()
  
  def get(self):
    # force on/off encrypted connection to the proxy
    if encrypted_connection and 'https' != self.request.scheme:
      self.response.headers.add_header('Strict-Transport-Security', 'max-age=31536000')
      self.redirect('https://' + self.request.host + self.request.path_qs, code = 307)
      return
    elif not encrypted_connection and 'http' != self.request.scheme:
      self.response.headers.add_header('Strict-Transport-Security', 'max-age=0')
      self.redirect('http://' + self.request.host + self.request.path_qs, code = 307)
      return
    
    # decode name of subdomain
    subdomain = ''
    path_qs = self.request.path_qs
    self.proxy_host_name = self.request.environ['DEFAULT_VERSION_HOSTNAME']
    if encrypted_connection:
      path_parts = self.request.path_qs.split('/', 2)
      if len(path_parts[1]) > 2 and '.' == path_parts[1][0] and '.' == path_parts[1][-1]:
        subdomain = path_parts[1][1:]
        path_qs = '/'
        if len(path_parts) > 2:
          path_qs += path_parts[2]
    else:
      host_parts = self.request.host.split('.')
      if len(host_parts) > 3:
        subdomain = '.'.join(host_parts[0:-3]) + '.'
      
    # add ip to torrents announce
    if 'info_hash' in self.request.GET and \
       'peer_id' in self.request.GET and \
       'port' in self.request.GET and \
       not 'ip' in self.request.GET:
       
      path_qs += '&ip=' + urllib.quote(self.request.remote_addr)
    
    url = host_scheme + '://' + subdomain + host_name + path_qs
    logging.debug(url)
    
    # translate browser headers
    headers = {}
    for name, value in self.request.headers.iteritems():
      if not name.startswith('X-'):
        headers[name] = value.replace(self.proxy_host_name, host_name) 
    
    # send req to host
    try:
      result = urlfetch.fetch(
        url              = url,
        payload          = self.request.body,
        method           = self.request.method,
        headers          = headers,
        allow_truncated  = False,
        follow_redirects = False,
        deadline         = 30
      )
    except Exception as e:
      self.response.set_status(504)
      self.response.write(str(e))
      logging.error(str(e))
      return
  
    if result.status_code < 512:
      self.response.status_int = result.status_code
    else: # fix cloudflare codes
      self.response.status_int = 503
    
    content = result.content
    self.response.headers = {}
    content_type  = '??'
    
    for header_line in result.header_msg.headers:
      (name, value) = header_line.split(':', 1)
      name_l = name.lower()
      value = value.strip()
      if name_l in skip_headers:
        continue
      if 'content-type' == name_l:
        content_type = re.split(r'[:;\s\/\\=]+', value.lower(), 2)
      else:
        value = value.replace(host_name, self.proxy_host_name)
      self.response.headers.add_header(name, value)
        
    # update text content
    if content_type[0] in ['text', 'application']:
      if content_type[1] in ['html', 'xml', 'xhtml+xml']:
        content = self.modify_content(content, mode = 'html')
      elif content_type[1] in ['css']:
        content = self.modify_content(content, mode = 'css')
      elif content_type[1] in ['javascript', 'x-javascript']:
        content = self.modify_content(content)
    
    self.response.write(content)
    
  def modify_content(self, content, mode = None):
    def dashrepl(matchobj):
      result = matchobj.group(1)
      subdomain = matchobj.group(4)
      if encrypted_connection:
        result += 'https://' + self.proxy_host_name
        if subdomain:
          result += '/.' + subdomain
      else:
        result += 'http://' + subdomain + self.proxy_host_name
      return result
    
    if mode == 'css':
      regexp = r'((url)\s*\(\s*[\'"]?)(https?:|)\/\/'
    elif mode == 'html':
      regexp = r'(\<[^\<\>]+\s(src|href|action)=[\'"]?)(https?:|)\/\/'
    else:
      regexp = r'(())(https?:)\/\/'
    regexp += r'([a-z0-9][-a-z0-9\.]*\.|)'
    regexp += re.escape(host_name)
    return re.sub(regexp, dashrepl, content, flags = re.IGNORECASE)

app = webapp2.WSGIApplication([
    ('/.*', MainHandler)
], debug=True)
