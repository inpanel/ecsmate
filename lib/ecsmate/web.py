#-*- coding: utf-8 -*-
#
# Copyright (c) 2012, ECSMate development team
# All rights reserved.
#
# ECSMate is distributed under the terms of the (new) BSD License.
# The full license can be found in 'LICENSE.txt'.

import os
import re
import binascii
import uuid
import json
import hashlib
import hmac
import time
import datetime
import platform
import subprocess
import functools
import tornado
import tornado.web
import tornado.httpclient
import tornado.gen
import tornado.ioloop
import ecs
import utils
import logging
import base64
import pyDes
import vpsmate
from tornado.escape import utf8 as _u
from tornado.escape import to_unicode as _d
from config import Config
from async_process import call_subprocess, callbackable


SERVER_NAME = 'ECSMate'
VPSMATE_VERSION = '1.0'
VPSMATE_BUILD = '1'

 
class Application(tornado.web.Application):
    def __init__(self, handlers=None, default_host="", transforms=None,
                 wsgi=False, **settings):
        settings['data_path'] = os.path.abspath(settings['data_path'])

        tornado.web.Application.__init__(self, handlers, default_host, transforms,
                 wsgi, **settings)


class RequestHandler(tornado.web.RequestHandler):

    def initialize(self):
        """Parse JSON data to argument list.
        """
        self.inifile = os.path.join(self.settings['data_path'], 'config.ini')
        self.config = Config(self.inifile)

        content_type = self.request.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            try:
                arguments = json.loads(tornado.escape.native_str(self.request.body))
                for name, value in arguments.iteritems():
                    name = _u(name)
                    if isinstance(value, unicode):
                        value = _u(value)
                    elif isinstance(value, bool):
                        value = value and 'on' or 'off'
                    else:
                        value = ''
                    self.request.arguments.setdefault(name, []).append(value)
            except:
                pass

    def set_default_headers(self):
        self.set_header('Server', SERVER_NAME)
    
    def check_xsrf_cookie(self):
        token = (self.get_argument("_xsrf", None) or
                 self.request.headers.get("X-XSRF-TOKEN"))
        if not token:
            raise tornado.web.HTTPError(403, "'_xsrf' argument missing from POST")
        if self.xsrf_token != token:
            raise tornado.web.HTTPError(403, "XSRF cookie does not match POST argument")

    def authed(self):
        # get the cookie within 30 mins
        if self.get_secure_cookie('authed', None, 30.0/1440) == 'yes':
            # regenerate the cookie timestamp per 5 mins
            if self.get_secure_cookie('authed', None, 5.0/1440) == None:
                self.set_secure_cookie('authed', 'yes', None)
        else:
            raise tornado.web.HTTPError(403, "Please login first")
    
    def getlastactive(self):
        # get last active from cookie
        cv = self.get_cookie('authed', False)
        try:
            return int(cv.split('|')[1])
        except:
            return 0

    @property
    def xsrf_token(self):
        if not hasattr(self, "_xsrf_token"):
            token = self.get_cookie("XSRF-TOKEN")
            if not token:
                token = binascii.b2a_hex(uuid.uuid4().bytes)
                expires_days = 30 if self.current_user else None
                self.set_cookie("XSRF-TOKEN", token, expires_days=expires_days)
            self._xsrf_token = token
        return self._xsrf_token


class StaticFileHandler(tornado.web.StaticFileHandler):
    def set_default_headers(self):
        self.set_header('Server', SERVER_NAME)


class ErrorHandler(tornado.web.ErrorHandler):
    def set_default_headers(self):
        self.set_header('Server', SERVER_NAME)


class FallbackHandler(tornado.web.FallbackHandler):
    def set_default_headers(self):
        self.set_header('Server', SERVER_NAME)


class RedirectHandler(tornado.web.RedirectHandler):
    def set_default_headers(self):
        self.set_header('Server', SERVER_NAME)


class VersionHandler(RequestHandler):
    def get(self):
        self.authed()
        version_info = {
            'version': VPSMATE_VERSION,
            'build': VPSMATE_BUILD,
        }
        self.write(version_info)


class XsrfHandler(RequestHandler):
    """Write a XSRF token to cookie
    """
    def get(self):
        self.xsrf_token


class AuthStatusHandler(RequestHandler):
    """Check if client has been authorized
    """
    def get(self):
        self.write({'lastactive': self.getlastactive()})

    def post(self):
        # authorize and update cookie
        try:
            self.authed()
            self.write({'authed': 'yes'})
        except:
            self.write({'authed': 'no'})


class LoginHandler(RequestHandler):
    """Validate username and password.
    """
    def post(self):
        username = self.get_argument('username', '')
        password = self.get_argument('password', '')

        loginlock = self.config.get('runtime', 'loginlock')
        if self.config.get('runtime', 'mode') == 'demo': loginlock = 'off'

        # check if login is locked
        if loginlock == 'on':
            loginlockexpire = self.config.getint('runtime', 'loginlockexpire')
            if time.time() < loginlockexpire:
                self.write({'code': -1,
                    'msg': u'登录已被锁定，请在 %s 后重试登录。<br>'\
                        u'如需立即解除锁定，请在服务器上执行以下命令：<br>'\
                        u'/usr/local/ecsmate/config.py loginlock off' %
                        datetime.datetime.fromtimestamp(loginlockexpire)
                            .strftime('%Y-%m-%d %H:%M:%S')})
                return
            else:
                self.config.set('runtime', 'loginlock', 'off')
                self.config.set('runtime', 'loginlockexpire', 0)

        loginfails = self.config.getint('runtime', 'loginfails')
        cfg_username = self.config.get('auth', 'username')
        cfg_password = self.config.get('auth', 'password')
        if cfg_password == '':
            self.write({'code': -1,
                'msg': u'登录密码还未设置，请在服务器上执行以下命令进行设置：<br>'\
                    u'/usr/local/ecsmate/config.py password \'您的密码\''})
        elif username != cfg_username:  # wrong with username
            self.write({'code': -1, 'msg': u'用户不存在！'})
        else:   # username is corret
            cfg_password, key = cfg_password.split(':')
            if hmac.new(key, password).hexdigest() == cfg_password:
                if loginfails > 0:
                    self.config.set('runtime', 'loginfails', 0)
                self.set_secure_cookie('authed', 'yes', None)
                
                passwordcheck = self.config.getboolean('auth', 'passwordcheck')
                if passwordcheck:
                    self.write({'code': 1, 'msg': u'%s，您已登录成功！' % username})
                else:
                    self.write({'code': 0, 'msg': u'%s，您已登录成功！' % username})
            else:
                if self.config.get('runtime', 'mode') == 'demo':
                    self.write({'code': -1, 'msg': u'用户名或密码错误！'})
                    return
                loginfails = loginfails+1
                self.config.set('runtime', 'loginfails', loginfails)
                if loginfails >= 5:
                    # lock 24 hours
                    self.config.set('runtime', 'loginlock', 'on')
                    self.config.set('runtime', 'loginlockexpire', int(time.time())+86400)
                    self.write({'code': -1, 'msg': u'用户名或密码错误！<br>'\
                        u'已连续错误 5 次，登录已被禁止！'})
                else:
                    self.write({'code': -1, 'msg': u'用户名或密码错误！<br>'\
                        u'连续错误 5 次后将被禁止登录，还有 %d 次机会。' % (5-loginfails)})


class LogoutHandler(RequestHandler):
    """Logout
    """
    def post(self):
        self.authed()
        self.clear_cookie('authed')


class BackupHandler(RequestHandler):
    def get(self):
        self.authed()

        if self.config.get('runtime', 'mode') == 'demo':
            self.write(u'DEMO状态不允许执行此操作！')
            return

        path = os.path.join(self.settings['data_path'], 'config.ini')
        if os.path.isfile(path):
            self.set_header('Content-Type', 'application/octet-stream')
            self.set_header('Content-disposition', 'attachment; filename=ecsmate_backup_%s.bak' % time.strftime('%Y%m%d'))
            self.set_header('Content-Transfer-Encoding', 'binary')
            with open(path) as f: self.write(f.read())
        else:
            self.write('配置文件不存在！')

    def authed(self):
        # get the cookie within 30 mins
        if self.get_secure_cookie('authed', None, 30.0/1440) == 'yes':
            # regenerate the cookie timestamp per 5 mins
            if self.get_secure_cookie('authed', None, 5.0/1440) == None:
                self.set_secure_cookie('authed', 'yes', None)
        else:
            raise tornado.web.HTTPError(403, "Please login first")

 
class RestoreHandler(RequestHandler):
    def post(self):
        self.authed()

        if self.config.get('runtime', 'mode') == 'demo':
            self.write(u'DEMO状态不允许执行此操作！')
            return

        path = os.path.join(self.settings['data_path'], 'config.ini')

        self.write(u'<body style="font-size:14px;overflow:hidden;margin:0;padding:0;">')

        if not self.request.files.has_key('ufile'):
            self.write(u'请选择备份配置文件！')
        else:
            self.write(u'正在上传...')
            file = self.request.files['ufile'][0]
            testpath = path+'.test'
            with open(testpath, 'wb') as f: f.write(file['body'])

            try:
                t = Config(testpath)
                with open(path, 'wb') as f: f.write(file['body'])
                self.write(u'还原成功！')
            except:
                self.write(u'配置文件有误，还原失败！')

            os.unlink(testpath)

        self.write('</body>')

        
class BuyECSHandler(RequestHandler):
    """Aliyun CPS program.
    """
    def get(self):
        self.redirect('http://www.aliyun.com/cps/rebate?from_uid=zop0qMW4KbY=')


class AccountHandler(RequestHandler):
    """ECS Account handler.
    """
    def get(self):
        self.authed()
        status = self.get_argument('status', '')

        accounts = self.config.get('ecs', 'accounts')
        try:
            accounts = json.loads(accounts)
        except:
            accounts = []
        
        accounts = sorted(accounts, key=lambda k:k['name'])
        if status:
            status = status == 'enable'
            accounts = filter(lambda a: a['status'] == status, accounts)

        if self.config.get('runtime', 'mode') == 'demo':
            for i, account in enumerate(accounts):
                accounts[i]['access_key_secret'] = '***DEMO状态下密钥被保护***'

        self.write({'code': 0, 'msg': u'成功加载 ECS 帐号列表！', 'data': accounts})
    
    def post(self):
        self.authed()
        action = self.get_argument('action', '')

        if self.config.get('runtime', 'mode') == 'demo':
            self.write({'code': -1, 'msg': u'DEMO状态不允许修改 ECS 帐号！'})
            return
        
        if action == 'add' or action == 'update':
            name = self.get_argument('name', '')
            access_key_id = self.get_argument('access_key_id', '')
            access_key_secret = self.get_argument('access_key_secret', '')
            status = self.get_argument('status', '')
            newaccount = {
                'name': name,
                'access_key_id': access_key_id,
                'access_key_secret': access_key_secret,
                'status': status == 'on',
            }
            if action == 'update':
                old_access_key_id = self.get_argument('old_access_key_id', '')

            accounts = self.config.get('ecs', 'accounts')
            try:
                accounts = json.loads(accounts)
            except:
                accounts = []

            if action == 'add':
                for account in accounts:
                    if account['access_key_id'] == access_key_id:
                        self.write({'code': -1, 'msg': u'添加失败！该 Access Key ID 已存在！'})
                        return
                accounts.append(newaccount)
            else:
                found = False
                for i, account in enumerate(accounts):
                    if account['access_key_id'] == old_access_key_id:
                        accounts[i] = newaccount
                        found = True
                        break
                if not found:
                    self.write({'code': -1, 'msg': u'更新失败！该 Access Key ID 不存在！'})
                    return

            self.config.set('ecs', 'accounts', json.dumps(accounts))
            if action == 'add':
                self.write({'code': 0, 'msg': u'新帐号添加成功！'})
            else:
                self.write({'code': 0, 'msg': u'帐号更新成功！'})
            
        elif action == 'delete':
            access_key_id = self.get_argument('access_key_id', '')
            accounts = self.config.get('ecs', 'accounts')
            try:
                accounts = json.loads(accounts)
            except:
                accounts = []

            found = False
            for i, account in enumerate(accounts):
                if account['access_key_id'] == access_key_id:
                    del accounts[i]
                    found = True
                    break
            if not found:
                self.write({'code': -1, 'msg': u'删除失败！该 Access Key ID 不存在！'})
                return

            self.config.set('ecs', 'accounts', json.dumps(accounts))
            self.write({'code': 0, 'msg': u'帐号删除成功！'})


class ECSHandler(RequestHandler):
    """ECS operation handler.
    """
    
    def _get_secret(self, access_key_id):
        accounts = self.config.get('ecs', 'accounts')
        try:
            accounts = json.loads(accounts)
        except:
            accounts = []

        for account in accounts:
            if account['access_key_id'] == access_key_id:
                return account['access_key_secret']

        return False

    @tornado.web.asynchronous
    @tornado.gen.engine
    def get(self, section):
        self.authed()

        if section == 'instances':
            access_key_id = self.get_argument('access_key_id', '')
            page_number = self.get_argument('page_number', '1')
            page_size = self.get_argument('page_size', '10')

            access_key_secret = self._get_secret(access_key_id)
            if access_key_secret == False:
                self.write({'code': -1, 'msg': u'该帐号不存在！'})
                self.finish()
                return

            srv = ecs.ECS(_u(access_key_id), _u(access_key_secret))
            result, data, reqid = yield tornado.gen.Task(callbackable(srv.DescribeInstanceStatus), PageNumber=_u(page_number), PageSize=_u(page_size))
            if not result:
                self.write({'code': -1, 'msg': u'云服务器列表加载失败！（%s）' % data['Message']})
                self.finish()
                return
            
            instances = []
            tasks = []
            if data.has_key('InstanceStatusSets'):
                for instance in data['InstanceStatusSets']:
                    tasks.append(tornado.gen.Task(callbackable(srv.DescribeInstanceAttribute), _u(instance['InstanceName'])))
                    instances.append(instance)
            
            if tasks:
                responses = yield tasks
                for i, response in enumerate(responses):
                    result, instdata, reqid = response
                    if result: instances[i].update(instdata)
            
            # get access info for VPSMate
            for instance in instances:
                if not self.config.has_option('vpsmate', instance['InstanceName']):
                    instance['VPSMateStatus'] = False
                else:
                    accessdata = self.config.get('vpsmate', instance['InstanceName'])
                    accessdata = accessdata.split('|')
                    accessinfo = {
                        'accesskey': accessdata[0],
                        'accessnet': accessdata[1],
                        'accessport': accessdata[2],
                    }
                    instance['VPSMateStatus'] = accessinfo

            self.write({'code': 0, 'msg': u'成功加载云服务器列表！', 'data': {
                'instances': instances,
                'page_number': data['PageNumber'],
                'page_size': data['PageSize'],
            }})
            self.finish()

        elif section == 'instance':
            access_key_id = self.get_argument('access_key_id', '')
            instance_name = self.get_argument('instance_name', '')

            access_key_secret = self._get_secret(access_key_id)
            if access_key_secret == False:
                self.write({'code': -1, 'msg': u'该帐号不存在！'})
                self.finish()
                return

            srv = ecs.ECS(_u(access_key_id), _u(access_key_secret))
            result, instdata, reqid = yield tornado.gen.Task(callbackable(srv.DescribeInstanceAttribute), _u(instance_name))
            if not result:
                self.write({'code': -1, 'msg': u'云服务器 %s 信息加载失败！（%s）' % (instance_name, instdata['Message'])})
                self.finish()
                return
            
            self.write({'code': 0, 'msg': u'成功加载云服务器信息！', 'data': instdata})
            self.finish()

        elif section == 'images':
            access_key_id = self.get_argument('access_key_id', '')
            region_code = self.get_argument('region_code', '')
            page_number = self.get_argument('page_number', '1')
            page_size = self.get_argument('page_size', '10')

            access_key_secret = self._get_secret(access_key_id)
            if access_key_secret == False:
                self.write({'code': -1, 'msg': u'该帐号不存在！'})
                self.finish()
                return

            srv = ecs.ECS(_u(access_key_id), _u(access_key_secret))
            result, data, reqid = yield tornado.gen.Task(callbackable(srv.DescribeImages), RegionCode=_u(region_code), PageNumber=_u(page_number), PageSize=_u(page_size))
            if not result:
                self.write({'code': -1, 'msg': u'系统镜像列表加载失败！（%s）' % data['Message']})
                self.finish()
                return
            
            if data.has_key('Images'):
                images = data['Images']
            else:
                images = []

            self.write({'code': 0, 'msg': u'成功加载系统镜像列表！', 'data': {
                'images': images,
                'total_number': data['ImageTotalNumber'],
                'page_number': data['PageNumber'],
                'page_size': data['PageSize'],
            }})
            self.finish()

        elif section == 'disks':
            access_key_id = self.get_argument('access_key_id', '')
            instance_name = self.get_argument('instance_name', '')

            access_key_secret = self._get_secret(access_key_id)
            if access_key_secret == False:
                self.write({'code': -1, 'msg': u'该帐号不存在！'})
                self.finish()
                return

            srv = ecs.ECS(_u(access_key_id), _u(access_key_secret))
            result, data, reqid = yield tornado.gen.Task(callbackable(srv.DescribeDisks), InstanceName=_u(instance_name))
            if not result:
                self.write({'code': -1, 'msg': u'磁盘列表加载失败！（%s）' % data['Message']})
                self.finish()
                return
            
            if data.has_key('Disks'):
                disks = data['Disks']
            else:
                disks = []

            self.write({'code': 0, 'msg': u'成功加载磁盘列表列表！', 'data': {
                'disks': disks
            }})
            self.finish()

        elif section == 'snapshots':
            access_key_id = self.get_argument('access_key_id', '')
            instance_name = self.get_argument('instance_name', '')
            disk_code = self.get_argument('disk_code', '')

            access_key_secret = self._get_secret(access_key_id)
            if access_key_secret == False:
                self.write({'code': -1, 'msg': u'该帐号不存在！'})
                self.finish()
                return

            srv = ecs.ECS(_u(access_key_id), _u(access_key_secret))
            result, data, reqid = yield tornado.gen.Task(callbackable(srv.DescribeSnapshots), InstanceName=_u(instance_name), DiskCode=_u(disk_code))
            if not result:
                self.write({'code': -1, 'msg': u'磁盘快照列表加载失败！（%s）' % data['Message']})
                self.finish()
                return
            
            if data.has_key('Snapshots'):
                snapshots = data['Snapshots']
            else:
                snapshots = []
                
            snapshots = sorted(snapshots, key=lambda k:k['CreateTime'], reverse=True)

            self.write({'code': 0, 'msg': u'成功加载磁盘快照列表！', 'data': {
                'snapshots': snapshots
            }})
            self.finish()

        elif section == 'accessinfo':
            instance_name = self.get_argument('instance_name', '')
            if not instance_name:
                self.write({'code': -1, 'msg': u'服务器不存在！'})
                self.finish()
                return

            if not self.config.has_option('vpsmate', instance_name):
                accessinfo = {'accesskey': '', 'accessnet': 'public', 'accessport': '8888'}
            else:
                data = self.config.get('vpsmate', instance_name)
                data = data.split('|')
                accessinfo = {
                    'accesskey': data[0],
                    'accessnet': data[1],
                    'accessport': data[2],
                }

            self.write({'code': 0, 'msg': u'', 'data': accessinfo})
            self.finish()

        else:
            self.write({'code': -1, 'msg': u'未定义的操作！'})
            self.finish()
    
    @tornado.web.asynchronous
    @tornado.gen.engine
    def post(self, section):
        self.authed()

        if section in ('startinstance', 'stopinstance', 'rebootinstance', 'resetinstance'):

            if self.config.get('runtime', 'mode') == 'demo':
                self.write({'code': -1, 'msg': u'DEMO状态不允许此类操作！'})
                self.finish()
                return

            access_key_id = self.get_argument('access_key_id', '')
            instance_name = self.get_argument('instance_name', '')
            if section in ('stopinstance', 'rebootinstance'):
                force = self.get_argument('force', '') and 'true' or None
            elif section == 'resetinstance':
                image_code = self.get_argument('image_code', '')

            access_key_secret = self._get_secret(access_key_id)
            if access_key_secret == False:
                self.write({'code': -1, 'msg': u'该帐号不存在！'})
                self.finish()
                return
            
            opstr = {'startinstance': u'启动', 'stopinstance': u'停止', 'rebootinstance': u'重启', 'resetinstance': u'重置'}

            srv = ecs.ECS(_u(access_key_id), _u(access_key_secret))
            if section == 'startinstance':
                result, data, reqid = yield tornado.gen.Task(callbackable(srv.StartInstance), _u(instance_name))
            elif section == 'stopinstance':
                result, data, reqid = yield tornado.gen.Task(callbackable(srv.StopInstance), _u(instance_name), ForceStop=_u(force))
            elif section == 'rebootinstance':
                result, data, reqid = yield tornado.gen.Task(callbackable(srv.RebootInstance), _u(instance_name), ForceStop=_u(force))
            elif section == 'resetinstance':
                result, data, reqid = yield tornado.gen.Task(callbackable(srv.ResetInstance), _u(instance_name), ImageCode=_u(image_code))
            if not result:
                self.write({'code': -1, 'msg': u'云服务器 %s %s失败！（%s）' % (instance_name, opstr[section], data['Message'])})
                self.finish()
                return
            
            self.write({'code': 0, 'msg': u'云服务器%s指令发送成功！' % opstr[section], 'data': data})
            self.finish()

        elif section in ('createsnapshot', 'deletesnapshot', 'cancelsnapshot', 'rollbacksnapshot'):

            if self.config.get('runtime', 'mode') == 'demo':
                self.write({'code': -1, 'msg': u'DEMO状态不允许此类操作！'})
                self.finish()
                return

            access_key_id = self.get_argument('access_key_id', '')
            instance_name = self.get_argument('instance_name', '')
            disk_code = self.get_argument('disk_code', '')
            if section in ('deletesnapshot', 'cancelsnapshot', 'rollbacksnapshot'):
                snapshot_code = self.get_argument('snapshot_code', '')

            access_key_secret = self._get_secret(access_key_id)
            if access_key_secret == False:
                self.write({'code': -1, 'msg': u'该帐号不存在！'})
                self.finish()
                return
            
            opstr = {'createsnapshot': u'创建', 'deletesnapshot': u'删除', 'cancelsnapshot': u'取消', 'rollbacksnapshot': u'回滚'}

            srv = ecs.ECS(_u(access_key_id), _u(access_key_secret))
            if section == 'createsnapshot':
                result, data, reqid = yield tornado.gen.Task(callbackable(srv.CreateSnapshot), InstanceName=_u(instance_name), DiskCode=_u(disk_code))
            elif section == 'deletesnapshot':
                result, data, reqid = yield tornado.gen.Task(callbackable(srv.DeleteSnapshot), InstanceName=_u(instance_name), DiskCode=_u(disk_code), SnapshotCode=_u(snapshot_code))
            elif section == 'cancelsnapshot':
                result, data, reqid = yield tornado.gen.Task(callbackable(srv.CancelSnapshotRequest), InstanceName=_u(instance_name), SnapshotCode=_u(snapshot_code))
            elif section == 'rollbacksnapshot':
                result, data, reqid = yield tornado.gen.Task(callbackable(srv.RollbackSnapshot), InstanceName=_u(instance_name), DiskCode=_u(disk_code), SnapshotCode=_u(snapshot_code))
            if not result:
                self.write({'code': -1, 'msg': u'快照%s失败！（%s）' % (opstr[section], data['Message'])})
                self.finish()
                return
            
            self.write({'code': 0, 'msg': u'快照%s指令发送成功！' % opstr[section], 'data': data})
            self.finish()

        elif section == 'accessinfo':

            if self.config.get('runtime', 'mode') == 'demo':
                self.write({'code': -1, 'msg': u'DEMO状态不允许此类操作！'})
                self.finish()
                return

            instance_name = self.get_argument('instance_name', '')
            accesskey = self.get_argument('accesskey', '')
            accessnet = self.get_argument('accessnet', '')
            accessport = self.get_argument('accessport', '')

            if not instance_name:
                self.write({'code': -1, 'msg': u'服务器不存在！'})
                self.finish()
                return

            self.config.set('vpsmate', instance_name, '%s|%s|%s' % (accesskey, accessnet, accessport))

            self.write({'code': 0, 'msg': u'VPSMate 远程控制设置保存成功！'})
            self.finish()

        else:
            self.write({'code': -1, 'msg': u'未定义的操作！'})
            self.finish()


class VPSMateIndexHandler(RequestHandler):
    """Index page of VPSMate.
    """
    def get(self, instance_name, ip, port):
        with open(os.path.join(self.settings['vpsmate_path'], 'index.html')) as f:
            html = f.read()
        html = html.replace('<link rel="stylesheet" href="', '<link rel="stylesheet" href="/vpsmate/')
        html = html.replace('<script src="', '<script src="/vpsmate/')
        html = html.replace("var template_path = '';", "var template_path = '/vpsmate';")
        self.write(html)


class VPSMateHandler(RequestHandler):
    """Operation proxy of VPSMate.

    REF: https://groups.google.com/forum/?fromgroups=#!topic/python-tornado/TB_6oKBmdlA
    """
    def handle_response(self, response): 
        if response.error and not isinstance(response.error, tornado.httpclient.HTTPError): 
            logging.info("response has error %s", response.error)
            self.set_status(500)
            self.write("Internal server error:\n" + str(response.error))
            self.finish()
        else:
            self.set_status(response.code)
            for header in ('Date', 'Cache-Control', 'Content-Type', 'Etag', 'Location'):
                v = response.headers.get(header)
                if v:
                    self.set_header(header, v)
            if response.body:
                self.write(response.body)
            self.finish()

    def forward(self, port=None, host=None): 
        try:
            tornado.httpclient.AsyncHTTPClient().fetch(
                tornado.httpclient.HTTPRequest(
                    url = "%s://%s:%s%s" % (
                        self.request.protocol, host or "127.0.0.1",
                        port or 80, self.request.uri),
                    method=self.request.method,
                    body=self.request.body,
                    headers=self.request.headers,
                    follow_redirects=False),
                self.handle_response)
        except tornado.httpclient.HTTPError, x:
            logging.info("tornado signalled HTTPError %s", x)
            if hasattr(x, response) and x.response:
                self.handle_response(x.response)
        except:
            self.set_status(500)
            self.write("Internal server error\n")
            self.finish()
    
    def gen_token(self, instance_name):
        if not self.config.has_option('vpsmate', instance_name):
            self.set_status(403)
            self.finish()
            return
        else:
            data = self.config.get('vpsmate', instance_name)
            data = data.split('|')
            accesskey = data[0]

        accesskey = base64.b64decode(accesskey)
        key = accesskey[:24]
        iv = accesskey[24:]
        k = pyDes.triple_des(key, pyDes.CBC, iv, pad=None, padmode=pyDes.PAD_PKCS5)
        access_token = k.encrypt('timestamp:%d' % int(time.time()))
        access_token = base64.b64encode(access_token)
        return access_token

    @tornado.web.asynchronous
    @tornado.gen.engine
    def get(self, instance_name, ip, port, uri):
        self.authed()
        self.request.body = None
        self.request.uri = '/'+uri
        self.request.headers['X-ACCESS-TOKEN'] = self.gen_token(instance_name)
        self.forward(port, ip)

    @tornado.web.asynchronous
    @tornado.gen.engine
    def post(self, instance_name, ip, port, uri):
        self.authed()
        self.request.uri = '/'+uri
        self.request.headers['X-ACCESS-TOKEN'] = self.gen_token(instance_name)
        self.forward(port, ip)


class SettingHandler(RequestHandler):
    """Settings for ECSMate
    """
    @tornado.web.asynchronous
    @tornado.gen.engine
    def get(self, section):
        self.authed()
        if section == 'auth':
            username = self.config.get('auth', 'username')
            passwordcheck = self.config.getboolean('auth', 'passwordcheck')
            self.write({'username': username, 'passwordcheck': passwordcheck})
            self.finish()

        elif section == 'server':
            ip = self.config.get('server', 'ip')
            port = self.config.get('server', 'port')
            self.write({'ip': ip, 'port': port})
            self.finish()

        elif section == 'upver':
            force = self.get_argument('force', '')
            lastcheck = self.config.getint('server', 'lastcheckupdate')

            # detect new version daily
            if force or time.time() > lastcheck + 86400:
                http = tornado.httpclient.AsyncHTTPClient()
                response = yield tornado.gen.Task(http.fetch, 'http://www.ecsmate.org/api/latest')
                if response.error:
                    self.write({'code': -1, 'msg': u'获取新版本信息失败！'})
                else:
                    data = tornado.escape.json_decode(response.body)
                    self.write({'code': 0, 'msg':'', 'data': data})
                    self.config.set('server', 'lastcheckupdate', int(time.time()))
                    self.config.set('server', 'updateinfo', response.body)
            else:
                data = self.config.get('server', 'updateinfo')
                try:
                    data = tornado.escape.json_decode(data)
                except:
                    data = {}
                self.write({'code': 0, 'msg': '', 'data': data})

            self.finish()

    def post(self, section):
        self.authed()
        if section == 'auth':
            if self.config.get('runtime', 'mode') == 'demo':
                self.write({'code': -1, 'msg': u'DEMO状态不允许修改用户名和密码！'})
                return

            username = self.get_argument('username', '')
            password = self.get_argument('password', '')
            passwordc = self.get_argument('passwordc', '')
            passwordcheck = self.get_argument('passwordcheck', '')

            if username == '':
                self.write({'code': -1, 'msg': u'用户名不能为空！'})
                return
            if password != passwordc:
                self.write({'code': -1, 'msg': u'两次密码输入不一致！'})
                return

            if passwordcheck != 'on': passwordcheck = 'off'
            self.config.set('auth', 'passwordcheck', passwordcheck)

            if username != '':
                self.config.set('auth', 'username', username)
            if password != '':
                key = utils.randstr()
                pwd = hmac.new(key, password).hexdigest()
                self.config.set('auth', 'password', '%s:%s' % (pwd, key))

            self.write({'code': 0, 'msg': u'登录设置更新成功！'})

        elif section == 'server':
            if self.config.get('runtime', 'mode') == 'demo':
                self.write({'code': -1, 'msg': u'DEMO状态不允许修改服务绑定地址！'})
                return

            ip = self.get_argument('ip', '*')
            port = self.get_argument('port', '8899')

            if ip != '*' and ip != '':
                if not utils.is_valid_ip(_u(ip)):
                    self.write({'code': -1, 'msg': u'%s 不是有效的IP地址！' % ip})
                    return
            port = int(port)
            if not port > 0 and port < 65535:
                self.write({'code': -1, 'msg': u'端口范围必须在 0 到 65535 之间！'})
                return
            
            self.config.set('server', 'ip', ip)
            self.config.set('server', 'port', port)
            self.write({'code': 0, 'msg': u'服务设置更新成功！将在重启服务后生效。'})


class BackendHandler(RequestHandler):
    """Backend process manager
    """
    jobs = {}
    locks = {}

    def _lock_job(self, lockname):
        cls = BackendHandler
        if cls.locks.has_key(lockname): return False
        cls.locks[lockname] = True
        return True

    def _unlock_job(self, lockname):
        cls = BackendHandler
        if not cls.locks.has_key(lockname): return False
        del cls.locks[lockname]
        return True

    def _start_job(self, jobname):
        cls = BackendHandler
        # check if the job is running
        if cls.jobs.has_key(jobname) and cls.jobs[jobname]['status'] == 'running':
            return False

        cls.jobs[jobname] = {'status': 'running', 'msg': ''}
        return True

    def _update_job(self, jobname, code, msg):
        cls = BackendHandler
        cls.jobs[jobname]['code'] = code
        cls.jobs[jobname]['msg'] = msg
        return True

    def _get_job(self, jobname):
        cls = BackendHandler
        if not cls.jobs.has_key(jobname):
            return {'status': 'none', 'code': -1, 'msg': ''}
        return cls.jobs[jobname]

    def _finish_job(self, jobname, code, msg, data=None):
        cls = BackendHandler
        cls.jobs[jobname]['status'] = 'finish'
        cls.jobs[jobname]['code'] = code
        cls.jobs[jobname]['msg'] = msg
        if data: cls.jobs[jobname]['data'] = data

    def get(self, jobname):
        """Get the status of the new process
        """
        self.authed()
        self.write(self._get_job(_u(jobname)))

    def _call(self, callback):
        with tornado.stack_context.NullContext():
            tornado.ioloop.IOLoop.instance().add_callback(callback)

    def post(self, jobname):
        """Create a new backend process
        """
        self.authed()

        # centos/redhat only job
        if jobname in ('yum_repolist', 'yum_installrepo', 'yum_info',
                       'yum_install', 'yum_uninstall', 'yum_ext_info'):
            if self.settings['dist_name'] not in ('centos', 'redhat'):
                self.write({'code': -1, 'msg': u'不支持的系统类型！'})
                return

        if self.config.get('runtime', 'mode') == 'demo':
            if jobname in ('update', 'datetime', 'swapon', 'swapoff', 'mount', 'umount', 'format'):
                self.write({'code': -1, 'msg': u'DEMO状态不允许此类操作！'})
                return

        if jobname == 'update':
            self._call(self.update)
        elif jobname in ('service_restart'):
            name = self.get_argument('name', '')
            service = self.get_argument('service', '')
            service = 'ecsmate'

            if self.config.get('runtime', 'mode') == 'demo':
                self.write({'code': -1, 'msg': u'DEMO状态不允许此类操作！'})
                return

            if not name: name = service
            dummy, action = jobname.split('_')
            if service != '':
                self._call(functools.partial(self.service,
                        _u(action),
                        _u(service),
                        _u(name)))
        elif jobname in ('vpsmate_install', 'vpsmate_uninstall', 'vpsmate_update'):

            if self.config.get('runtime', 'mode') == 'demo':
                self.write({'code': -1, 'msg': u'DEMO状态不允许此类操作！'})
                return

            ssh_ip = self.get_argument('ssh_ip', '')
            ssh_port = self.get_argument('ssh_port', '22')
            ssh_user = self.get_argument('ssh_user', '')
            ssh_password = self.get_argument('ssh_password', '')
            instance_name = self.get_argument('instance_name', '')
            
            if jobname == 'vpsmate_install':
                accessnet = self.get_argument('accessnet', 'public')
                accesskey = vpsmate.gen_accesskey()
                accessport = '8888'
            elif jobname == 'vpsmate_update':
                if not self.config.has_option('vpsmate', instance_name):
                    self.write({'code': -1, 'msg': u'该服务器还未配置远程控制！'})
                    return
                accessdata = self.config.get('vpsmate', instance_name)
                accessdata = accessdata.split('|')
                accesskey = accessdata[0]

            if jobname == 'vpsmate_install':
                self._call(functools.partial(self.vpsmate_install,
                        _u(ssh_ip), _u(ssh_port), _u(ssh_user), _u(ssh_password),
                        _u(instance_name), _u(accessnet), _u(accessport), _u(accesskey)))
            elif jobname == 'vpsmate_uninstall':
                self._call(functools.partial(self.vpsmate_uninstall,
                        _u(ssh_ip), _u(ssh_port), _u(ssh_user), _u(ssh_password),
                        _u(instance_name)))
            elif jobname == 'vpsmate_update':
                self._call(functools.partial(self.vpsmate_update,
                        _u(ssh_ip), _u(ssh_port), _u(ssh_user), _u(ssh_password),
                        _u(accesskey)))

        else:   # undefined job
            self.write({'code': -1, 'msg': u'未定义的操作！'})
            return

        self.write({'code': 0, 'msg': ''})

    @tornado.web.asynchronous
    @tornado.gen.engine
    def update(self):
        if not self._start_job('update'): return
        
        root_path = self.settings['root_path']
        data_path = self.settings['data_path']
        distname = self.settings['dist_name']

        # don't do it in dev environment
        if os.path.exists('%s/../.svn' % root_path):
            self._finish_job('update', 0, u'升级成功！')
            return
        
        # install the latest version
        http = tornado.httpclient.AsyncHTTPClient()
        response = yield tornado.gen.Task(http.fetch, 'http://www.ecsmate.org/api/latest')
        if response.error:
            self._update_job('update', -1, u'获取版本信息失败！')
            return
        versioninfo = tornado.escape.json_decode(response.body)
        downloadurl = versioninfo['download']
        initscript = u'%s/tools/init.d/%s/ecsmate' % (root_path, distname)
        steps = [
            {'desc': u'正在下载安装包...',
                'cmd': u'wget -q "%s" -O %s/ecsmate.tar.gz' % (downloadurl, data_path),
            }, {'desc': u'正在创建解压目录...',
                'cmd': u'mkdir %s/ecsmate' % data_path,
            }, {'desc': u'正在解压安装包...',
                'cmd': u'tar zxmf %s/ecsmate.tar.gz -C %s/ecsmate' % (data_path, data_path),
            }, {'desc': u'正在删除旧版本...',
                'cmd': u'find %s -mindepth 1 -maxdepth 1 -path %s -prune -o -exec rm -rf {} \;' % (root_path, data_path),
            }, {'desc': u'正在复制新版本...',
                'cmd': u'find %s/ecsmate -mindepth 1 -maxdepth 1 -exec cp -r {} %s \;' % (data_path, root_path),
            }, {'desc': u'正在删除旧的服务脚本...',
                'cmd': u'rm -f /etc/init.d/ecsmate',
            }, {'desc': u'正在安装新的服务脚本...',
                'cmd': u'cp %s /etc/init.d/ecsmate' % initscript,
            }, {'desc': u'正在更改脚本权限...',
                'cmd': u'chmod +x /etc/init.d/ecsmate %s/config.py %s/server.py' % (root_path, root_path),
            }, {'desc': u'正在删除安装临时文件...',
                'cmd': u'rm -rf %s/ecsmate %s/ecsmate.tar.gz' % (data_path, data_path),
            },
        ]
        for step in steps:
            desc = _u(step['desc'])
            cmd = _u(step['cmd'])
            self._update_job('update', 2, desc)
            result, output = yield tornado.gen.Task(call_subprocess, self, cmd)
            if result != 0:
                self._update_job('update', -1, desc+'失败！')
                break
            
        if result == 0:
            code = 0
            msg = u'升级成功！请刷新页面重新登录。'
        else:
            code = -1
            msg = u'升级失败！<p style="margin:10px">%s</p>' % _d(output.strip().replace('\n', '<br>'))

        self._finish_job('update', code, msg)

    @tornado.web.asynchronous
    @tornado.gen.engine
    def service(self, action, service, name):
        """Service operation.
        """
        jobname = 'service_%s_%s' % (action, service)
        if not self._start_job(jobname): return

        action_str = {'start': u'启动', 'stop': u'停止', 'restart': u'重启'}
        self._update_job(jobname, 2, u'正在%s %s 服务...' % (action_str[action], _d(name)))

        cmd = '/etc/init.d/%s %s' % (service, action)
        result, output = yield tornado.gen.Task(call_subprocess, self, cmd)
        if result == 0:
            code = 0
            msg = u'%s 服务%s成功！' % (_d(name), action_str[action])
        else:
            code = -1
            msg = u'%s 服务%s失败！<p style="margin:10px">%s</p>' % (_d(name), action_str[action], _d(output.strip().replace('\n', '<br>')))

        self._finish_job(jobname, code, msg)

    @tornado.web.asynchronous
    @tornado.gen.engine
    def vpsmate_install(self, ssh_ip, ssh_port, ssh_user, ssh_password, instance_name, accessnet, accessport=None, accesskey=None):
        """Install VPSMate
        """
        jobname = 'vpsmate_install_%s' % ssh_ip
        if not self._start_job(jobname): return

        self._update_job(jobname, 2, u'正在将 VPSMate 安装到 %s...' % ssh_ip)
        
        result = yield tornado.gen.Task(callbackable(vpsmate.install),
                    ssh_ip, ssh_port, ssh_user, ssh_password, accesskey=accesskey, vpsmate_port=accessport)
        if result == True:
            code = 0
            msg = u'VPSMate 安装成功！'
            self.config.set('vpsmate', instance_name, '%s|%s|%s' % (accesskey, accessnet, accessport))
        else:
            code = -1
            msg = u'VPSMate 安装过程中发生错误！'

        self._finish_job(jobname, code, msg)

    @tornado.web.asynchronous
    @tornado.gen.engine
    def vpsmate_uninstall(self, ssh_ip, ssh_port, ssh_user, ssh_password, instance_name):
        """Uninstall VPSMate
        """
        jobname = 'vpsmate_uninstall_%s' % ssh_ip
        if not self._start_job(jobname): return

        self._update_job(jobname, 2, u'正在将 VPSMate 从 %s 上卸载...' % ssh_ip)
    
        result = yield tornado.gen.Task(callbackable(vpsmate.uninstall),
                    ssh_ip, ssh_port, ssh_user, ssh_password)
        if result == True:
            code = 0
            msg = u'VPSMate 卸载成功！'
            try:
                self.config.remove_option('vpsmate', instance_name)
            except:
                pass
        else:
            code = -1
            msg = u'VPSMate 卸载过程中发生错误！'

        self._finish_job(jobname, code, msg)

    @tornado.web.asynchronous
    @tornado.gen.engine
    def vpsmate_update(self, ssh_ip, ssh_port, ssh_user, ssh_password, accesskey=None):
        """Update VPSMate
        """
        jobname = 'vpsmate_update_%s' % ssh_ip
        if not self._start_job(jobname): return

        self._update_job(jobname, 2, u'正在更新 %s 上的 VPSMate 配置...' % ssh_ip)
    
        result = yield tornado.gen.Task(callbackable(vpsmate.update),
                    ssh_ip, ssh_port, ssh_user, ssh_password, accesskey=accesskey)
        if result == True:
            code = 0
            msg = u'VPSMate 配置更新成功！'
        else:
            code = -1
            msg = u'VPSMate 配置更新过程中发生错误！'

        self._finish_job(jobname, code, msg)
