#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''web app骨架'''

import logging; logging.basicConfig(level=logging.INFO)

import asyncio, os, json, time

from datetime import datetime

from aiohttp import web

from jinja2 import Environment, FileSystemLoader

from config import configs

import orm

from coroweb import add_routes, add_static

from handlers import cookie2user, COOKIE_NAME

#初始化jinja2模板
def init_jinja2(app, **kw):
    logging.info('init jinja2...')
    options = dict(
        #XML/HTML自动转义，就是在渲染模板时自动把变量中的<>&等字符转换为&lt;&gt;&amp，默认开启
        autoescape = kw.get('autoescape', True),
        #块开始标记符，如{% block title %}
        block_start_string = kw.get('block_start_string', '{%'),
        #块结束标记符
        block_end_string = kw.get('block_end_string', '%}'),
        #变量开始标记符,如{{ blog.name }}
        variable_start_string = kw.get('variable_start_string', '{{'),
        #变量结束标记符
        variable_end_string = kw.get('variable_end_string', '}}'),
        #使用模板时检查模板文件的状态，若有修改，则重新加载模板，默认为开启
        auto_reload = kw.get('auto_reload', True)
    )
    path = kw.get('path', None)
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    logging.info('set jinja2 template path: %s' % path)
    #设置模板环境
    #FileSystemLoader(), 从提供的路径中加载模板
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get('filters', None)
    if filters is not None:
        for name, f in filters.items():
            #将创建日期添加到环境中
            env.filters[name] = f
    #将模板环境作为属性添加到app中
    app['__templating__'] = env

#以下三个函数为middleware，是一种拦截器
#在一个URL被某个函数处理前，可经过middleware改变输入输出

#此函数的作用是在处理URL请求前，将请求方法和路径记录下来
async def logger_factory(app, handler):

    logging.info('——————logger_factory()->handler: %s' % handler)
    
    async def logger(request):
        logging.info('Request: %s %s' % (request.method, request.path))
        return (await handler(request))
    return logger

#在处理URL请求前，解析出用户信息并绑定到request中
async def auth_factory(app, handler):
    async def auth(request):
        logging.info('check user: %s %s' % (request.method, request.path))
        request.__user__ = None
        cookie_str = request.cookies.get(COOKIE_NAME)
        #若存在cookie，解析用户信息
        if cookie_str:
            user = await cookie2user(cookie_str)
            #若有用户信息，将其息绑定到request中，没有则表明cookie是伪造的
            if user:
                logging.info('set current user: %s' % user.email)
                request.__user__ = user
        #若请求路径是管理页面，但用户信息不存在或拥有管理员权限，则无法操作，跳转到登录页面
        if request.path.startswith('/manage/') and (request.__user__ is None or request.__user__.admin):
            return web.HTTPFound('/signin')
        return (await handler(request))
    return auth

#在处理URL请求前，将消息主体内容记录下来
async def data_factory(app, handler):
    async def parse_data(request):
        if request.method == 'POST':
            if request.content_type.startswith('application/json'):
                request.__data__ = await request.json()
                logging.info('request json: %s' % str(request.__data__))
            elif request.content_type.startswith('application/x-www-form-urlencoded'):
                request.__data__ = await request.post()
                logging.info('request.form: %s' % str(request.__data__))
        return (await handler(request))
    return parse_data

#在处理完URL请求后，将响应结果转换成web.Response返回
async def response_factory(app, handler):
    async def response(request):
        logging.info('Response handler...')
        r = await handler(request)
        #StreamResponse是aiohttp的HTTP响应基类，web.Response继承于此，因此直接返回
        if isinstance(r, web.StreamResponse):
            return r
        #若响应结果为字节流，将其作为body部分返回，并将消息主体类型设置为流类型
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        #若响应结果为字符串
        if isinstance(r, str):
            #若内容为redirect，
            #redirect表示重定向，可将浏览器重定向到另一个URL，而不是将内容发送给用户
            if r.startswith('redirect:'):
                #返回重定向的URL
                return web.HTTPFound(r[9:])
            #否则，将字符串编码后作为body部分返回
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        #若响应结果为字典，获取其模板属性
        if isinstance(r, dict):
            template = r.get('__template__')
            #若无模板属性，将字典转化为JSON格式返回
            if template is None:
                resp = web.Response(body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
                resp.content_type = 'application/json;charset=utf-8'
                return resp
            #否则，
            else:
                r['__user__'] = request.__user__
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        #r为状态码，如200, 404, 500等
        if isinstance(r, int) and r >= 100 and r < 600:

            logging.info('——————response_factory()->r,int: %s' % r)
            
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:

            logging.info('——————response_factory()->r,tuple: %s' % r)

            #t为状态码，m描述，如200 OK，404 Not Found，500 Internal Server Error等
            t, m = r
            if isinstance(t, int) and t >= 100 and t < 600:
                return web.Response(t, str(m))
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp
    return response

#模板返回的日志创建日期是浮点数，通过此过滤器将其转换为日期字符串
def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta //3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    #若创建日期太早，就返回日期，2000年1月1日
    dt = datetime.fromtimestamp(t)

    logging.info('——————datetime_filter()->dt: %s' % dt)
    
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)

async def init(loop):
    await orm.create_pool(loop=loop, user='www-data', password='www-data', db='awesome')
    #创建web应用，循环类型为消息循环
    app = web.Application(loop=loop, middlewares=[
        logger_factory, auth_factory, response_factory
    ])  
    init_jinja2(app, filters=dict(datetime=datetime_filter))
    #注册URL处理函数
    add_routes(app, 'handlers')
    #添加静态文件
    add_static(app)
    #创建TCP服务器
    srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)         #创建TCP服务
    logging.info('server started at http://127.0.0.1:9000...')
    return srv

loop = asyncio.get_event_loop()    #获取Evenloop
loop.run_until_complete(init(loop))    #执行coroutine
loop.run_forever()

#run_until_complete和run_forever?
