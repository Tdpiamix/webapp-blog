#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''URL处理函数'''

import re, time, json, logging, hashlib, base64, asyncio

import markdown2

from aiohttp import web

from coroweb import get, post

#尽量少用from module import *，因为判定一个特殊的函数或属性是从哪来的有些困难，
#并且会造成调试和重构都更困难
from apis import Page, APIError, APIValueError, APIPermissionError, APIResourceNotFoundError

from models import User, Comment, Blog, next_id

from config import configs

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret    #cookie密匙

#检验用户权限
def check_admin(request):
    #若用户信息不存在或者拥有管理员权限，报错
    if request.__user__ is None or request.__user__.admin:
        raise APIPermissionError()

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

#将text格式转换成html格式
def text2html(text):
    #将对应字符转换成html的格式，并过滤掉空白字符
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)

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
@asyncio.coroutine
def cookie2user(cookie_str):
    if not cookie_str:
        return None
    #cookie的格式为id-expires-sha1，若正确，将其拆分开
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        #判断cookie是否过期
        if int(expires) < time.time():
            return None
        user = yield from User.find(uid)
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

#————————————————用户浏览页面————————————————

#首页
@get('/')
def index(*, page='1'):
    page_index = get_page_index(page)
    #获取博客总数
    num = yield from Blog.findNumber('count(id)')
    #设置分页信息
    page = Page(num, page_index)
    if num == 0:
        blogs = []
    #根据分页情况获取博客内容
    else:
        blogs = yield from Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
    return {
        '__template__': 'blogs.html',
        'page': page,
        'blogs': blogs
    }

#博客详情页
@get('/blog/{id}')
def get_blog(id):
    #根据id从数据库中获取博客内容
    blog = yield from Blog.find(id)
    #根据blog_id获取评论，按评论时间降序排列
    comments = yield from Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
    #将博客和评论转换成html格式
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
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

#注销页
@get('/signout')
def signout(request):
    #获取上一个页面，即从哪个页面链接到当前页面的
    referer = request.headers.get('Referer')
    #注销后，本应跳转到/signout路径下，为了不影响用户浏览，自动返回上一个页面或主页
    r = web.HTTPFound(referer or '/')
    #清除cookie
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r

#————————————————管理页面————————————————

#管理重定向
@get('/manage/')
def manage():
    return 'redirect:/manage/comments'

#评论列表页
@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }

#博客列表页
@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }

#用户列表页
@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }

#创建博客页
@get('/manage/blogs/create')
def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        #在用户提交博客时，将数据post到action指定的路径
        'action': '/api/blogs'
    }

#编辑博客页
@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/%s' % id
    }

#————————————————后端API————————————————

#获取用户信息
@get('/api/users')
def api_get_users(*, page='1'):
    page_index = get_page_index(page)
    num = yield from User.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, users=())
    users = yield from User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    for u in users:
        u.passwd = '******'
    return dict(page=p, users=users)

#匹配邮箱与密码
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

#创建新用户
@post('/api/users')
def api_register_user(*, email, name, passwd):
    #检查注册信息合法性
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    #根据email查找用户是否已存在
    users = yield from User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', '该邮箱已被注册')
    #若注册信息合法，生成唯一id
    uid = next_id()
    #对密码进行加密后，将用户信息存入数据库
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    yield from user.save()
    r = web.Response()
    #设置cookie
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passed = '******'
    r.content_type = 'application/json'
    #返回json数据，ensure_ascii=False，即非ASCII字符将保持原样，不进行转义
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

#用户登录验证
@post('/api/authenticate')
def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', '请输入账号')
    if not passwd:
        raise APIValueError('passwd', '请输入密码')
    #根据email从数据库中查找用户信息
    users = yield from User.findAll('email=?', [email])
    #若查询结果为空，则用户不存在
    if len(users) == 0:
        raise APIValueError('email', '账号不存在')
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
        raise APIValueError('passwd', '密码错误')
    r = web.Response()
    #若验证成功，设置cookie
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    #将用户密码用'******'代替，防止泄露，数据库中储存的密码仍不变
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r

#获取单条博客信息
@get('/api/blogs/{id}')
def api_get_blog(*, id):
    blog = yield from Blog.find(id)
    return blog

#获取博客信息
@get('/api/blogs')
def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = yield from Blog.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = yield from Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)

#创建博客
@post('/api/blogs')
def api_create_blog(request, *, name, summary, content):
    #检查用用户权限
    check_admin(request)
    #检查博客信息合法性
    if not name or not name.strip():
        raise APIValueError('name', '请输入日志标题')
    if not summary or not summary.strip():
        raise APIValueError('summary', '请输入日志摘要')
    if not content or not content.strip():
        raise APIValueError('content', '请输入日志内容')
    #将博客信息存入数据库
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary=summary.strip(), content=content.strip())
    yield from blog.save()
    return blog

#编辑博客
@post('/api/blogs/{id}')
def api_update_blog(id, request, *, name, summary, content):
    check_admin(request)
    blog = yield from Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name', '请输入日志标题')
    if not summary or not summary.strip():
        raise APIValueError('summary', '请输入日志摘要')
    if not content or not content.strip():
        raise APIValueError('content', '请输入日志内容')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    #将博客信息更新到数据库
    yield from blog.update()
    return blog

#删除博客
@post('/api/blogs/{id}/delete')
def api_delete_blog(request, *, id):
    check_admin(request)
    blog = yield from Blog.find(id)
    yield from blog.remove()
    return dict(id=id)

#获取评论信息
@get('/api/comments')
def api_comments(*, page='1'):
    page_index = get_page_index(page)
    num = yield from Comment.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, comments=())
    comments = yield from Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)

#创建评论
@post('/api/blogs/{id}/comments')
def api_create_comment(id, request, *, content):
    #评论之前先检查用户是否登录
    user = request.__user__
    if user is None:
        raise APIPermissionError('请先登录')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = yield from Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
    yield from comment.save()
    return comment

#删除评论
@post('/api/comments/{id}/delete')
def api_delete_comments(id, request):
    check_admin(request)
    c = yield from Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    yield from c.remove()
    return dict(id=id)
