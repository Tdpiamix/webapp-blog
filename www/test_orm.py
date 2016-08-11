#!usr/bin/env python3
# -*- coding: utf-8 -*-

import orm, asyncio

from models import User, Blog, Comment

async def test():
      await orm.create_pool(user='www-data', password='www-data', db='awesome', loop=loop)
      u = User(name='Test01', email='Test01@example.com', passwd='test0123456', image='about:blank')
      await u.save()

loop = asyncio.get_event_loop()
loop.run_until_complete(test())
loop.run_forever()
