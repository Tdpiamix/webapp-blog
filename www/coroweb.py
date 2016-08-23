#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''aiohttp框架相对底层，因此重新封装一个web框架，
   减少编写的代码数量，且便于单独测试'''

import asyncio, os, inspect, logging, functools

from urllib import parse

from aiohttp import web

from apis import APIError

#此函数将以装饰器的方式给函数添加请求方法和请求路径两个属性，使其附带URL信息
def get(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator

def post(path):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator

#形参(paramseters)的类型有5种
#POSITIONAL_ONLY，即必须通过位置传入，Python中没有显式的语法来定义此类参数，多见于内建函数中
#POSITIONAL_OR_KEYWORD，可以通过关键字或位置传入，这是默认的参数类型
#VAR_POSITIONAL，即*args
#KEYWORD_ONLY，必须通过关键字传入，位于*args之后，**kw之前,可用'*,'与POSITIONAL_OR_KEYWORD区分开来
#VAR_KEYWORD，即**kwargs

#获取传入函数中默认值为空的KEYWORD_ONLY参数
def get_required_kw_args(fn):
    args = []
    #signature()：返回可调用对象的调用签名及其返回注释
    #不清楚调用签名是什么，从返回结果看是该可调用对象的全部形参
    #signauture.parameters：返回形参名与对应形参对象的有序映射
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        #若形参的类型为KEYWORD_ONLY且未指定默认值，将形参名加入args列表
        if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
            args.append(name)
    #以元组形式返回结果，可防止内容被修改
    return tuple(args)

#获取传入函数中全部KEYWORD_ONLY参数
def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            args.append(name)
    return tuple(args)

#判断传入函数是否有KEYWORD_ONLY参数
def has_named_kw_args(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.KEYWORD_ONLY:
            return True

#判断传入函数是否有VAR_KEYWORD参数
def has_var_kw_arg(fn):
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            return True

#判断传入函数是否有名为request的参数
def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        #找到名为的request形参后，判断下一个形参类型
        #下一个形参不能是POSITIONAL_OR_KEYWORD，不懂为什么要绕一圈
        if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
            #这句也不理解，last named parameter是指最后一个命名的参数？最后一个指定的参数？
            raise ValueError('request parameter must be the last named parameter in function: %s%s' % (fn.__name__, str(sig)))
    return found

#URL处理函数不一定是一个coroutine，因此用RequestHandler()来封装一个URL处理函数
#RequestHandler的目的就是从URL函数中分析其需要接收的参数
#从request中获取必要的参数，调用URL函数，然后把结果转换为web.Response对象
class RequestHandler(object):

    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_named_kw_args = has_named_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._required_kw_args = get_required_kw_args(fn)

        logging.info('——————RequestHandler()->self._func: %s' % self._func)
        #self._named_kw_args为元组，格式化时要传入与元素数量相等的占位符,这里直接拼接了
        #直接拼接会报错，logging内部错误，占位符合提供的参数数量不等，但信息仍会以
        #Message: '——————RequestHandler()->self._named_kw_args:'
        #Arguments: ('email,passwd',)
        #的形式打印出来
        if self._named_kw_args:
            print('——————RequestHandler()->self._named_kw_args:', self._named_kw_args)
        if self._required_kw_args:
            print('——————RequestHandler()->self._required_kw_args:', self._required_kw_args)
        if self._has_request_arg:
            logging.info('——————RequestHandler()->self._has_request_arg: %s' % self._has_request_arg)
        if self._has_var_kw_arg:
            logging.info('——————RequestHandler()->self._has_var_kw_arg: %s' % self._has_var_kw_arg)
        if self._has_named_kw_args:
            logging.info('——————RequestHandler()->self._has_named_kw_args: %s' % self._has_named_kw_args)

    #定义__call__()方法后，可将其实例视为函数
    #即x(arg1, arg2...)等同于调用x.__call__(self, arg1, arg2)
    @asyncio.coroutine
    def __call__(self, request):
        kw = None
        #不知道为什么有self._has_named_kw_args还要self._required_kw_args
        if self._has_var_kw_arg or self._has_named_kw_args or self._required_kw_args:
            if request.method == 'POST':
                #检查请求中是否包含消息主体类型
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content-Type.')
                ct = request.content_type.lower()
                #检查消息主体是否是JSON对象
                if ct.startswith('application/json'):
                    #对JSON对象进行反序列化
                    params = yield from request.json()
                    #判断JSON对象格式是否正确
                    #JSON的object类型对应Python的dict类型
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('JSON body must be object.')
                    kw = params
                    
                    logging.info('——————RequestHandler()->JSON->kw: %s' % kw)

                #检查消息主体是否是表单信息
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    #request.post()从request body读取POST参数,即表单信息
                    params = yield from request.post()
                    kw = dict(**params)

                    logging.info('——————RequestHandler()->x-www-form-urlencoded->kw: %s' % kw)
                    
                else:
                    return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
            if request.method == 'GET':
                qs = request.query_string
                #检查请求路径中是否有查询字符串
                #如https://www.baidu.com/s?ie=utf-8中，'?'后面的就是查询字符串，其变量名为ie，值为utf-8
                if qs:
                    kw = dict()
                    #parse.parse_qs()，以字典形式返回查询字符串中的数据，'True'表示保留空白字符串

                    logging.info('——————RequestHandler()->parse.parse_qs(): %s' % parse.parse_qs(qs, True))

                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        #经过以上处理，kw仍为空,则获取地址解析中的抽象匹配信息
        #不知道具体是什么，大概是根据URL参数返回文本
        if kw is None:
            kw = dict(**request.match_info)

            logging.info('——————RequestHandler()->request.match_info: %s' % kw)
            
        else:
            if not self._has_var_kw_arg and self._named_kw_args:
                #将不需要的参数从kw中移除，只保留传入的参数
                copy = dict()
                for name in self._named_kw_args:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            #检查并更新参数
            for k, v in request.match_info.items():
                if k in kw:
                     logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        #检查是否有传入的默认值为空的KEYWORD_ONLY参数
        if self._required_kw_args:
            for name in self._required_kw_args:
                if not name in kw:
                    return web.HTTPBadRequest('Missing argument: %s' % name)
        logging.info('call with args: %s' % str(kw))
        try:
            r = yield from self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)

#添加静态文件
def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static %s => %s' % ('/static/', path))

#add_route函数，用来注册一个URL处理函数
def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s' % str(fn))
    #若函数既不是协程也不是生成器，则将其变成协程
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        #这里检测的是是否通过@asyncio.coroutine标记得到的协程，async def定义的结果为False
        fn = asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)' % (method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
    #注册URL处理函数
    app.router.add_route(method, path, RequestHandler(app, fn))

#把多次URL处理函数的注册，变成自动扫描注册
def add_routes(app, module_name):
    #rfind()，返回字符串最后一次出现的位置，如果没有匹配项则返回-1
    n = module_name.rfind('.')
    #若未匹配到，则module_name在当前目录下，直接导入
    #__import__(module_name, globals(), locals(), [name])相当于from module_name import name
    if n == (-1):
        mod = __import__(module_name, globals(), locals())
    else:
        #将'.'号后的子模块名赋值给name
        name = module_name[n+1:]
        #为什么还要getattr()？
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):
        #排除私有属性
        if attr.startswith('_'):
            continue
        fn = getattr(mod, attr)
        #若模块属性可调用(即为函数)，且有method和path两个属性，即为URL处理函数，进行注册
        if callable(fn):
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)
