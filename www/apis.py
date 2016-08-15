#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''JSON API definition'''

import json, logging, inspect, functools

class Page(object):
    '''
    Page object for display pages.
    '''

    def __init__(self, item_count, page_index=1, page_size=10):
        '''
        Init Pageination by item_count, page_index and page_size.

        >>> p1= Page(100, 1)
        >>> p1.page_count
        10
        >>> p1.offset
        0
        >>> p1.limit
        10
        >>>p2 = Page(90, 9, 10)
        >>>p2.page_count
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
        #每页显示的博客数
        self.page_size = page_size
        #总页数为两者整除，余下不满一页的另起一页
        self.page_count = item_count // page_size + (1 if item_count % page_size > 0 else 0)
        #没有博客或当前页码大于总页数，则从第1页开始
        if (item_count == 0) or (page_index > self.page_count):
            self.offset = 0
            self.limit = 0
            self.page_index = 1
        else:
            self.page_index = page_index
            #偏移值，表示本页博客序号从何处开始
            #如第5页，偏移值为40，即第5页第一条博客序号为41
            self.offset = self.page_size * (page_index - 1)
            #不知道限制的具体作用
            self.limit = self.page_size
        #若当前页码小于总页数，则有下一页
        self.has_next = self.page_index < self.page_count
        #若当前页码大于1，则有上一页
        self.has_previous = self.page_index > 1

    #__str__使用print打印出的实例能显示出内部数据，而不是储存地址
    def __str__(self):
        return 'item_count: %s, page_count: %s, page_index: %s, page_size: %s, offset: %s, limit: %s' % (self.item_count, self.page_count, self.page_index, self.page_size, self.offset, self.limit)
    #使直接打印的实例能显示出内部数据
    __repr__ = __str__
        
class APIError(Exception):
    '''
    the base APIError which contains error(required), data(optional) and message(optional).
    '''
    def __init__(self, error, data='', message=''):  
        super(APIError, self).__init__(message)
        self.error = error
        self.data = data
        self.message = message

class APIValueError(APIError):
    '''
    Indicate the input value has error or invalid. The data specifies the error field of input form.
    '''
    def __init__(self, field, message=''):
        super(APIValueError, self).__init__('value:invalid', field, message)

class APIResourceNotFoundError(APIError):
    '''
    Indicate the resource was not found. The data specifies the resource name.
    '''
    def __init__(self, field, message=''):
        super(APIResourceNotFoundError, self).__init__('value:notfound', field, message)
        
class APIPermissionError(APIError):
    '''
    Indicate the api has no permission.
    '''
    def __init__(self, message=''):
        super(APIPermissionError, self).__init__('permission:forbidden', 'permission', message)
        
if __name__ =='__main__':
    import doctest
    doctest.testmod()
