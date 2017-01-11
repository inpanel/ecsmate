#!/usr/bin/env python2.6
#-*- coding: utf-8 -*-
#
# Copyright (c) 2012, ECSMate development team
# All rights reserved.
#
# ECSMate is distributed under the terms of the (new) BSD License.
# The full license can be found in 'LICENSE.txt'.

import os
import sys
root_path = os.path.dirname(__file__)
sys.path.append(os.path.join(root_path, 'lib'))

import ssl
import tornado.ioloop
import tornado.httpserver
import ecsmate.web
import ecsmate.config
from ecsmate.utils import make_cookie_secret


def write_pid():
    pidfile = '/var/run/ecsmate.pid'
    pidfp = open(pidfile, 'w')
    pidfp.write(str(os.getpid()))
    pidfp.close()

def main():
    # settings of tornado application
    settings = {
        'root_path': root_path,
        'data_path': os.path.join(root_path, 'data'),
        'static_path': os.path.join(root_path, 'static'),
        'vpsmate_path': os.path.join(root_path, 'static/vpsmate'),
        'xsrf_cookies': True,
        'cookie_secret': make_cookie_secret(),
    }
    
    application = ecsmate.web.Application([
        (r'/vpsmate/((?:css|js|js.min|lib|partials|images|favicon\.ico|robots\.txt)(?:\/.*)?)',
            ecsmate.web.StaticFileHandler, {'path': os.path.join(settings['static_path'], 'vpsmate')}),
        (r'/vpsmate/(.+?)/(.+?)/(.+?)/', ecsmate.web.VPSMateIndexHandler),
        (r'/vpsmate/(.+?)/(.+?)/(.+?)/(.*?)', ecsmate.web.VPSMateHandler),   # /vpsmate/InstanceName/IP/Port/URI
        (r'/xsrf', ecsmate.web.XsrfHandler),
        (r'/authstatus', ecsmate.web.AuthStatusHandler),
        (r'/login', ecsmate.web.LoginHandler),
        (r'/logout', ecsmate.web.LogoutHandler),
        (r'/account', ecsmate.web.AccountHandler),
        (r'/ecs/(.+)', ecsmate.web.ECSHandler),
        (r'/setting/(.+)', ecsmate.web.SettingHandler),
        (r'/backend/(.+)', ecsmate.web.BackendHandler),
        (r'/((?:css|js|js.min|lib|partials|images|favicon\.ico|robots\.txt)(?:\/.*)?)',
            ecsmate.web.StaticFileHandler, {'path': settings['static_path']}),
        (r'/($)', ecsmate.web.StaticFileHandler,
            {'path': os.path.join(settings['static_path'], 'index.html')}),
        (r'/backup', ecsmate.web.BackupHandler),
        (r'/restore', ecsmate.web.RestoreHandler),
        (r'/buyecs', ecsmate.web.BuyECSHandler),
        (r'/version', ecsmate.web.VersionHandler),
        (r'/.*', ecsmate.web.ErrorHandler, {'status_code': 404}),
    ], **settings)

    # read configuration from config.ini
    cfg = ecsmate.config.Config(settings['data_path'] + '/config.ini')
    server_ip = cfg.get('server', 'ip')
    server_port = cfg.get('server', 'port')

    server = tornado.httpserver.HTTPServer(application)
    try:
        server.listen(server_port, address=server_ip)
    except:
        server_ip = ''  # set to listen all
        cfg.set('server', 'ip', '')
        server.listen(server_port, address=server_ip)
    write_pid()
    tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
    main()