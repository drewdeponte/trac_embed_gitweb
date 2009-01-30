# Created by Noah Kantrowitz on 2007-06-05.
# Copyright (c) 2007 Noah Kantrowitz. All rights reserved.

import os.path
import re
import urllib
import urllib2

from trac.core import *
from trac.web.api import IRequestHandler
from trac.web.chrome import INavigationContributor, ITemplateProvider, add_stylesheet
from trac.perm import IPermissionRequestor
from trac.mimeview.api import MIME_MAP as BASE_MIME_MAP
from trac.prefs.api import IPreferencePanelProvider
from trac.config import Option, BoolOption
from trac.util.text import to_unicode
from trac.util.translation import _

from genshi.builder import tag
from genshi.core import Markup

# Make a copy to start us off
MIME_MAP = dict(BASE_MIME_MAP.iteritems())
MIME_MAP.update({
    'png': 'image/png',
})

class GitwebModule(Component):
    """A plugin to embed gitweb into Trac."""
    
    implements(IRequestHandler, INavigationContributor, IPermissionRequestor, ITemplateProvider, IPreferencePanelProvider)
    
    gitweb_url = Option('gitweb', 'url', doc='URL to gitweb')
    send_mime = BoolOption('gitweb', 'send_mime', default=False,
                           doc='Try to send back the correct MIME type for blob_plain pages.')
    
    patterns = [
        # (regex, replacement) 
        (r'^.*?<div class', '<div class', False),
        (r'<\/body.*', '', False),
        (r'git\?{1,}a=git-logo.png', 'www/images/git.png', False),
        (r'[\'\"]\/git\?{0,}([^\'\"]*)', '"?\\1', False),
        (r'git\.do\?(\S+)?\;a\=rss', 'git?\\1;a=rss', False),
        (r'<img src="git-logo.png" width="72" height="27" alt="git" class="logo"/>', 
         lambda req: '<img src="%s" width="72" height="27" alt="git" class="git-logo"/>' % \
                     req.href.chrome('gitweb', 'git-logo.png'), True),
        (r'<link rel="stylesheet" type="text/css" href="/pub/gitweb.css"/>',
         lambda req: '<link rel="stylesheet" type="text/css" href="%s"/>\n<link rel="stylesheet" type="text/css" href="%s"/>' % \
                (req.href.chrome('gitweb', 'gitweb-full.css'), req.href.chrome('gitweb', 'gitweb-trac.css')), True),
    ]
    patterns = [(re.compile(pat, re.S|re.I|re.U), rep, chrome) for pat, rep, chrome in patterns]
    
    # IRequestHandler methods
    def match_request(self, req):
        return req.path_info.startswith('/browser')
        
    def process_request(self, req):
        req.perm.assert_permission('BROWSER_VIEW')
        
        # Check for no URL being configured
        if not self.gitweb_url:
            raise TracError('You must configure a URL in trac.ini')
        
        # Grab the page
        urlf = urllib2.urlopen(self.gitweb_url+'?'+req.environ['QUERY_STRING'])
        page = urlf.read()
        
        # Check if this is a raw format send
        args = dict([(args or '=').split('=',1) for args in req.environ['QUERY_STRING'].split(';')])
        if args.get('a') == 'blob_plain':
            if self.send_mime:
                _, ext = os.path.splitext(args.get('f', ''))
                mime_type = MIME_MAP.get(ext[1:], 'text/plain')
            else:
                mime_type = 'text/plain'
            req.send(page, mime_type)
            
        # Check for RSS
        if args.get('a') in ('rss', 'opml', 'project_index', 'atom'):
            req.send(page, urlf.info().type)
        
        # Proceed with normal page serving
        chrome_enabled = req.session.get('gitweb_chrome_enabled', '0') == '1'
        page = to_unicode(page)
        for pat, rep, chrome in self.patterns:
            if chrome_enabled or chrome:
                if callable(rep):
                    rep = rep(req)
                page = pat.sub(rep, page)
            
        # If chrome wrapping is disabled, send back the page
        if not chrome_enabled:
            req.send(page, urlf.info().type)

        data = {
            'gitweb_page': Markup(page),
        }
        #add_link(req, 'stylesheet', 'http://dev.laptop.org/www/styles/gitbrowse.css', 'text/css')
        add_stylesheet(req, 'gitweb/gitweb.css')
        add_stylesheet(req, 'gitweb/gitweb-trac.css')
        return 'gitweb.html', data, urlf.info().type

    # INavigationContributor methods
    def get_navigation_items(self, req):
        if 'BROWSER_VIEW' in req.perm:
            yield 'mainnav', 'gitweb', tag.a(_('Browse Source'),
                                             href=req.href.browser())
                                             
    def get_active_navigation_item(self, req):
        return 'gitweb'
        
    # IPermissionRequestor methods
    def get_permission_actions(self):
        yield 'BROWSER_VIEW'
        
    # ITemplateProvider methods
    def get_htdocs_dirs(self):
        from pkg_resources import resource_filename
        return [('gitweb', resource_filename(__name__, 'htdocs'))]
            
    def get_templates_dirs(self):
        from pkg_resources import resource_filename
        return [resource_filename(__name__, 'templates')]

    # IPreferencePanelProvider methods
    def get_preference_panels(self, req):
        yield 'gitweb', _('Gitweb')

    def render_preference_panel(self, req, panel):
        if req.method == 'POST':
            chrome_enabled = 'chrome_enabled' in req.args
            req.session['gitweb_chrome_enabled'] = chrome_enabled and '1' or '0'
            req.redirect(req.href.prefs('gitweb'))

        data = {
            'chrome_enabled': req.session.get('gitweb_chrome_enabled', '0')
        }
        return 'prefs_gitweb.html', data
