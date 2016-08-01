#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''web app骨架'''

import logging; logging.basicConfig(level=logging.INFO)
import asyncio, os, json, time
from datetime import datetime
from aiohttp import web

#URL处理函数
def index(request):
    #Python的字符串类型是str，在内存中以Unicode表示，若要在网络上传输，或者保存到磁盘上，就需要把str变为以字节为单位的bytes
    #return web.Response(body=b'<h1>Awesome</h1>')
    #要显示中文内容可将含有中文的str用utf-8编码为bytes
    return web.Response(body='你好'.encode('utf-8'), headers={'Content-Type':'text/html; charset=utf-8'})

async def init(loop):
    app = web.Application(loop=loop)    #创建web应用，循环类型为消息循环
    app.router.add_route('GET', '/', index)    #添加URL处理函数
    srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)         #创建TCP服务
    logging.info('server started at http://127.0.0.1:9000...')
    return srv

loop = asyncio.get_event_loop()    #获取Evenloop
loop.run_until_complete(init(loop))    #执行coroutine
loop.run_forever()

#run_until_complete和run_forever的区别?
