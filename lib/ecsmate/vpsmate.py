#-*- coding: utf-8 -*-
#
# Copyright (c) 2012, ECSMate development team
# All rights reserved.
#
# ECSMate is distributed under the terms of the (new) BSD License.
# The full license can be found in 'LICENSE.txt'.

"""VPSMate operator
"""

import os
if __name__ == '__main__':
    import sys
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.append(root_path)

import pxssh
import shlex
import base64
from random import random


def install(ssh_ip, ssh_port, ssh_user, ssh_password, accesskey=None, vpsmate_ip=None, vpsmate_port=None):
    """Install VPSMate on a remote server.
    """
    try:          
        s = pxssh.pxssh()
        s.login(ssh_ip, ssh_user, ssh_password, port=ssh_port)
        s.sendline('rm -f install.py')
        s.prompt()
        s.sendline('wget http://www.vpsmate.org/tools/install.py')
        s.prompt()
        s.sendline('python install.py')
        s.expect('INSTALL COMPLETED!')
        s.sendcontrol('c')  # don't set username and password
        s.prompt()
        s.sendline('rm -f install.py')
        s.prompt()
        s.sendline('/usr/local/vpsmate/config.py loginlock on')
        s.prompt()
        if accesskey != None:
            s.sendline('/usr/local/vpsmate/config.py accesskey %s' % accesskey)
            s.prompt()
            s.sendline('/usr/local/vpsmate/config.py accesskeyenable on')
            s.prompt()
        if vpsmate_ip != None:
            s.sendline('/usr/local/vpsmate/config.py ip %s' % vpsmate_ip)
            s.prompt()
        if vpsmate_port != None:
            s.sendline('/usr/local/vpsmate/config.py port %s' % vpsmate_port)
            s.prompt()
        s.sendline('service vpsmate restart')
        s.prompt()
        s.logout()
        return True
    except pxssh.ExceptionPxssh, e:
        return False

def uninstall(ssh_ip, ssh_port, ssh_user, ssh_password):
    """Uninstall VPSMate on a remote server.
    """
    try:          
        s = pxssh.pxssh()
        s.login(ssh_ip, ssh_user, ssh_password, port=ssh_port)
        s.sendline('service vpsmate stop')
        s.prompt()
        s.sendline('rm -rf /usr/local/vpsmate /etc/init.d/vpsmate')
        s.prompt()
        s.logout()
        return True
    except pxssh.ExceptionPxssh, e:
        return False

def update(ssh_ip, ssh_port, ssh_user, ssh_password, accesskey=None, accesskeyenable=None,
    username=None, password=None, loginlock=None, vpsmate_ip=None, vpsmate_port=None):
    """Update config on remote server.
    """
    try:          
        s = pxssh.pxssh()
        s.login(ssh_ip, ssh_user, ssh_password, port=ssh_port)
        s.sendline('service vpsmate stop')
        s.prompt()
        if accesskey != None:
            s.sendline('/usr/local/vpsmate/config.py accesskey %s' % accesskey)
            s.prompt()
        if accesskeyenable != None:
            s.sendline('/usr/local/vpsmate/config.py accesskeyenable %s' % (accesskeyenable and 'on' or 'off'))
            s.prompt()
        if username != None:
            s.sendline('/usr/local/vpsmate/config.py username %s' % username)
            s.prompt()
        if password != None:
            s.sendline('/usr/local/vpsmate/config.py password %s' % password)
            s.prompt()
        if loginlock != None:
            s.sendline('/usr/local/vpsmate/config.py loginlock %s' % (loginlock and 'on' or 'off'))
            s.prompt()
        if vpsmate_ip != None:
            s.sendline('/usr/local/vpsmate/config.py ip %s' % vpsmate_ip)
            s.prompt()
        if vpsmate_port != None:
            s.sendline('/usr/local/vpsmate/config.py port %s' % vpsmate_port)
            s.prompt()
        s.logout()
        return True
    except:
        return False

def gen_accesskey():
    """Generate a access key.
    """
    keys = [chr(int(random()*256)) for i in range(0, 32)]
    return base64.b64encode(''.join(keys))


if __name__ == '__main__':
    import pprint
    pp = pprint.PrettyPrinter(indent=4)
    #pp.pprint(install('42.121.98.82', '22', 'root', 'xx', '960BmT039ONbgV6NxGfeIQgOVQcRF7fHvthFPSmlq+c='))
    #pp.pprint(uninstall('42.121.98.82', '22', 'root', 'xx'))
    #pp.pprint(gen_accesskey())