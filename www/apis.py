#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''API异常信息处理'''

import json, logging, inspect, functools

#设置分页信息
class Page(object):

    def __init__(self, item_count, page_index=1, page_size=10):
        '''
        >>> p1 = Page(100, 1)
        >>> p1.page_count
        10
        >>> p1.offset
        0
        >>> p1.limit
        10
        >>> p2 = Page(90, 9, 10)
        >>> p2.page_count
        9
        >>> p2.offset
        80
        >>> p2.limit
        10
        >>> p3 = Page(91, 10, 10)
        >>> p3.page_count
        10
        >>> p3.offset
        90
        >>> p3.limit
        10
        '''
        
        #博客总数
        self.item_count = item_count
        #每页能显示的博客数
        self.page_size = page_size
        #总页数为两者整除，余下不满一页的另起一页
        self.page_count = item_count // page_size + (1 if item_count % page_size > 0 else 0)
        #没有博客或当前页码大于总页数，从第1页开始
        if (item_count == 0) or (page_index > self.page_count):
            self.offset = 0
            self.limit = 0
            self.page_index = 1
        else:
            self.page_index = page_index
            #偏移值，表示本页之前已显示的博客数
            #如第5页，偏移值为40，则第5页要显示的博客应从数据库中第41条开始取
            self.offset = self.page_size * (page_index - 1)
            #从数据库获取博客内容时，用于指定返回结果行的最大数目
            #此处为10行，即每页能显示的博客数
            self.limit = self.page_size
        #若当前页码小于总页数，则有下一页
        self.has_next = self.page_index < self.page_count
        #若当前页码大于1，则有上一页
        self.has_previous = self.page_index > 1

    #__str__方法，使print打印出的实例能显示出内部数据，而不是内存地址
    def __str__(self):
        return 'item_count: %s, page_count: %s, page_index: %s, page_size: %s, offset: %s, limit: %s' % (self.item_count, self.page_count, self.page_index, self.page_size, self.offset, self.limit)
    
    #使直接打印的实例能显示出内部数据
    __repr__ = __str__

#API异常基类
class APIError(Exception):
    
    def __init__(self, error, data='', message=''):  
        super(APIError, self).__init__(message)
        self.error = error
        self.data = data
        self.message = message

#输入值异常，输入值错误或无效
class APIValueError(APIError):
   
    def __init__(self, field, message=''):
        super(APIValueError, self).__init__('value:invalid', field, message)

#资源异常，找不到资源
class APIResourceNotFoundError(APIError):
    
    def __init__(self, field, message=''):
        super(APIResourceNotFoundError, self).__init__('value:notfound', field, message)

#权限异常，API没有权限
class APIPermissionError(APIError):
    
    def __init__(self, message=''):
        super(APIPermissionError, self).__init__('permission:forbidden', 'permission', message)

if __name__ == '__main__':
    import doctest
    doctest.testmod()
