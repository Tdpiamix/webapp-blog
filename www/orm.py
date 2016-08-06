#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''ORM，对象关系映射，将关系数据库的一行映射为一个对象'''

import asyncio, logging

import aiomysql

def log(sql, args=()):
    logging.info('SQL: %s' % sql)

#创建全局连接池，每个HTTP请求都能从连接池中直接获取数据库连接
#避免了频繁地打开或关闭数据库连接
async def create_pool(loop, **kw):
    logging.info('create database connection pool...')
    #连接池储存于全局变量__pool中
    global __pool
    __pool = await aiomysql.create_pool( 
        host=kw.get('host', 'localhost'),    #数据库服务器地址，默认设在本地
        port=kw.get('port', 3306),    #数据库端口， 默认为3306
        user=kw['user'],    #登录名 
        password=kw['password'],    #登录口令
        db=kw['db'],    #数据库名
        charset=kw.get('charset', 'utf8'),    #字符集，默认为utf8
        autocommit=kw.get('autocommit', True),    #自动提交事务，默认开启
        maxsize=kw.get('maxsize', 10),    #连接池最多同时处理数， 默认为10
        minsize=kw.get('minsize', 1),    #连接池最少同时处理数， 默认为1
        loop=loop
    )

#select函数，用于执行SELECT语句
async def select(sql, args, size=None):
    log(sql, args)
    global __pool
    ########测试async with、yield from、await、__pool########
    #此处不能直接将yield from用await替换
    #通过async with语句可以使得Python程序在进入和退出runtime context（即with）时，执行异步调用
    async with __pool.get() as conn:
        #创建游标，默认以tuple形式返回查询结果，通过aiomysql.DictCursor可使结果以dict形式返回
        async with conn.cursor(aiomysql.DictCursor) as cur:
            #执行SQL语句，SQL语句的占位符是?，而MySQL的占位符是%s，需替换
            #将args参数添加到SELECT语句中，若没有，则使用默认的SELECT语句
            await cur.execute(sql.replace('?', '%s'), args or ())
            #如果传入size参数，接收size条返回结果行
            if size:
                rs = await cur.fetchmany(size)
            #否则，接收全部的返回结果行
            else:
                rs = await cur.fetchall()
        logging.info('rows returned: %s' % len(rs))
        return rs

#execute函数，用于执行INSERT, UPDATE, DELETE语句，三者所需参数相同
async def execute(sql, args, autocommit=True):
    log(sql)
    async with __pool.get() as conn:
        if not autocommit:
            #begin()是什么意思？
            await conn.begin()
        try:
            ########测试conn.cursor()########
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', '%s'), args)
                #获取执行影响的行数
                affected = cur.rowcount
            #若没有自动提交，则手动提交事务
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            #若没有自动提交，则回滚到语句被执行之前
            if not autocommit:
                await conn.rollback()
            raise
        return affected

#在INSERT语句中被调用，作用是构造出与需要插入的数据数量相等的占位符
def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ','.join(L)

#Field类，负责保存数据库表的字段名和字段类型
class Field(object):

    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    ########测试删除__str__########
    #打印信息，不知道为什么要有
    def __str__(self):
        return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)
    
class StringField(Field):

    #ddl("data definition languages"),用于定义数据类型
    #varchar, 可变长度字符串,此处字符串的可变范围为0~100
    #char,固定长度字符串,长度不够会用空格字符补齐)
    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)

class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

class BooleanField(Field):

    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

class FloatField(Field):

    def __init__(self,name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):

    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)

#metaclass允许你创建类或者修改类
#任何继承自Model的类，都会通过ModelMetaclass.__new__()来创建，它能自动扫描映射关系，并将其存储到自身的类属性中       
class ModelMetaclass(type):

    #__new__()在创建对象时调用，返回当前类的一个实例，第一个参数cls为类本身
    #__init__()在创建完对象后调用，对当前类的实例进行初始化,第一个参数self即__new__()返回的实例
    def __new__(cls, name, bases, attrs):
        #排除对Model类本身的修改,其作用是被继承,不存在与数据库表的映射
        #print('after __new__>>>%s' % name)
        if name =='Model':
            #print('Model>>>%s' % name)
            return type.__new__(cls, name, bases, attrs)
        #print('after Model>>>%s' % name)
        #获取数据库表名，若当前类中未定义__table__属性，则将类名作为表名
        #print(attrs.get('__table__', None))
        tableName = attrs.get('__table__', None) or name
        logging.info('found model: %s (table: %s)' % (name, tableName))
        mappings = dict()    #创建字典，用于储存类属性与数据库表中列的映射关系
        fields = []    #储存除主键外的属性
        primaryKey = None    #储存主键属性
        #历遍类属性，若其值为Field类型，将其存入映射关系字典中，建立映射关系
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('  found mapping: %s ==> %s' % (k, v))
                mappings[k] = v
                #若v是主键，判断primaryKey值是否存在
                if v.primary_key:
                    #若primaryKey值已存在，则主键不止一个，报错
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field: %s' % k)
                    #若primaryKey值为空，则将值赋给primaryKey
                    primaryKey = k
                #将不是主键的属性储存到fields中
                else:
                    fields.append(k)
        #若未找到主键，同样报错
        if not primaryKey:
            raise RuntimeError('PrimaryKey not found.')
        #将已存入映射关系字典中的属性从类属性中删除，防止实例属性遮盖类的同名属性，造成运行时错误
        for k in mappings.keys():
            attrs.pop(k)
        #将fields中的字符串用反引号`括起，防止表名、字段名、数据库名与mysql保留字冲突
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        attrs['__mappings__'] = mappings    #将属性和列的映射关系存入类属性中
        attrs['__table__'] = tableName    #存入表名
        attrs['__primary_key__'] = primaryKey    #存入主键属性名
        attrs['__fields__'] = fields    #存入除主键外的属性名
        #构造默认的SELECT, INSERT, UPDATE和DELETE语句，存入类属性中
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ','.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ','.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ','.join(map(lambda f:'`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        #要得到当前类的实例，应当在当前类中的__new__()方法语句中调用当前类的父类的__new__()方法
        return type.__new__(cls, name, bases, attrs)

#定义ORM映射的基类
class Model(dict, metaclass=ModelMetaclass):
    
    def __init__(self, **kw):
        #super继承，调用Model的父类dict的__init__方法
        super(Model, self).__init__(**kw)

    #当实例自身不存在key属性时，自动调用__getattr__方法
    #使实例可通过self.key的形式获取dict的值
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attribute '%s'" % key)

    #实例在设置属性时，自动调用__setattr__方法
    #使实例可通过self.key = value的形式设置dict的值
    def __setattr__(self, key, value):
        self[key] = value

    #实例自身存在key属性时使用此方法,否则会调用__getattr()__方法
    #获取key属性所对应的值，相当于self.key，若值不存在，返回None
    #__getattr__()和__setattr__()是针对**kw参数传入的dict的值的获取和设置方法
    #getValue()是针对实例自身属性的获取方法
    def getValue(self, key):
        return getattr(self, key, None)

    #获取key属性所对应的值，若值不存在，返回默认值
    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        #若值不存在，则从__mappings__中获取对应属性的默认值
        if value is None:
            field = self.__mappings__[key]
            #若默认值存在，判断其是否可调用，若可调用则将其返回值赋给value，否则直接赋给value
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                #将值设置为当前属性的值
                setattr(self, key, value)
        return value

    #@classmethod是一个装饰器，用来指定一个类的方法为类方法
    #类方法既可以直接类调用(C.f())，也可以进行实例调用(C().f())
    @classmethod
    #对默认SELECT语句的补充，可实现根据WHERE条件查找
    async def findAll(cls, where=None, args=None, **kw):
        sql = [cls.__select__]
        #若有where子句，将'where'字符串和where参数加入SELECT语句
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        #若有orderBy子句，将'order by'字符串和orderBy参数加入SELECT语句
        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        #若有limit子句，将'limit'字符串加入SELECT语句
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            #根据limit参数数量添加相应占位符，并将limit参数加入到args中
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: %s' % str(limit))
        #执行SELECT语句
        rs = await select(' '.join(sql), args)
        #logging.info('rs in findAll(): %s' % rs)
        #返回查询结果
        return [cls(**r) for r in rs]

    #实现根据WHERE条件查找，但返回的是查询结果的数目，适用于SELECT COUNT(*)语句
    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        #selectField参数传入的就是count子句？
        #_num_有是什么，要查询的列名？
        sql = ['select %s _num_ from `%s` ' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        #logging.info('rs in findNumber(): %s' % rs)
        if len(rs) == 0:
            return None
        #
        return rs[0]['_num_']

    #实现根据主键查找
    @classmethod
    async def find(cls, pk):
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        #logging.info('rs in find(): %s' % rs)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    #将实例的数据存入数据库
    async def save(self):
        #将除主键外的实例属性的值存入args列表
        args = list(map(self.getValueOrDefault, self.__fields__))
        #将主键的实例属性的值存入args列表
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        #一个实例只能插入一行数据，若返回的影响行数不为1，报错
        if rows != 1:
            logging.warn('failed to insert record: affected rows: %s' % rows)

    #数据的更新
    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warn('failed to update by primary key: affected rows: %s' % rows)

    #数据的删除
    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        rows = await execute(self.__dalete__, args)
        if rows != 1:
            logging.warn('failed to remove by primary key: affected rows: %s' % rows)

