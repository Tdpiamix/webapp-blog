#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''URL处理函数'''

import re, time, json, logging, hashlib, base64, asyncio

from aiohttp import web

from coroweb import get, post

from apis import APIError, APIValueError, APIResourceNotFoundError

from models import User, Comment, Blog, next_id

from config import configs

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret    #cookie密匙

#根据用户的信息生成cookie
def user2cookie(user, max_age):
    #设定cookie过期时间，max_age为cookie的有效时间
    expires = str(int(time.time() + max_age))
    #构造原始字符串
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    #将用户id,过期时间和加密字符串组合成用户cookie
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)

#通过cookie解析出用户信息
async def cookie2user(cookie_str):
    if not cookie_str:
        return None
    #cookie的形式为id-expires-sha1，若正确，将其拆分开
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        #判断cookie是否过期
        if int(expires) < time.time():
            return None
        user = await User.find(uid)
        if user is None:
            return None
        #将原始字符串加密，与从cookie中获取的加密字符串比较，若不相等，则cookie是伪造的
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        #若验证成功，返回用户信息
        return user
    except Exception as e:
        logging.exception(e)
        return None

#获取页码，检查其合法性
def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p

#首页
@get('/')
def index(request):
    summary = 'Lorem ipsum dolor sit amet, consectetur asupisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    blogs = [
        Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
        Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
        Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
    ]
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }

#注册页
@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }

#登录页
@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }

#用户登录验证
@post('/api/authenticate')
def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid passwd.')
    #根据email从数据库中查找用户信息
    users = yield from User.findAll('email=?', [email])
    #若查询结果为空，即用户不存在
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    #数据库中储存的用户密码是经过加密的
    #用户登录时，根据用户输入的密码构造加密字符串
    sha1 = hashlib.sha1()
    #以下三步相当于sha1((user.id+':'+user.passwd).encode('utf-8'))
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    #将数据库中的用户密码与加密字符串比较，若不一致，则用户输入的密码错误
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid password.')
    #若验证成功，设置cookie
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    #将用户密码用'******'代替，防止泄露，数据库中储存的密码仍不变
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

#注销页
@get('/signout')
def signout(request):
    #获取上一个页面，即从哪个页面链接到当前页面的
    referer = request.headers.get('Referer')
    #注销后，自动返回上一个页面或主页
    r = web.HTTPFound(referer or '/')
    #清除cookie
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r

#匹配邮箱与密码
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

#创建用户
@post('/api/users')
def api_register_user(*, email, name, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    #根据email查找用户是否已存在
    users = yield from User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    #若注册信息无误，生成唯一id
    uid = next_id()
    #对密码进行加密，并将用户信息存入数据库
    #name.strip()，删除用户名前后空格
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    yield from user.save()
    #设置cookie
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passed = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

#获取用户信息
@get('/api/users')
def api_get_users():
    users = yield from User.findAll(orderBy='created_at desc')
    for u in users:
        u.passwd = '******'
    return dict(users=users)

    

