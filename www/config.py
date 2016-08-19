#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''配置文件的处理'''

import config_default

class Dict(dict):

    def __init__(self, names=(), values=(), **kw):
        super(Dict, self).__init__(**kw)
        for k, v in zip(names, values):
            self[k] = v

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

    def __setattr__(self, key, value):
        self[key] = value
        
#要修改数据库配置信息时，在自定义配置(config_override)中设置
#然后用自定义配置中的数据覆盖默认配置中的对应数据
def merge(defaults, override):
    r = {}
    #配置信息以字典形式储存，将其键值对拆分开
    for k, v in defaults.items():
        #若某项数据出现在自定义配置中，检查其是否是字典
        if k in override:
            #若是将其交给merge函数再次拆分
            if isinstance(v, dict):
                r[k] = merge(v, override[k])
            #用该数据覆盖默认配置中的对应数据
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

#将修改后的配置信息转换成自定义字典
def toDict(d):
    D = Dict()
    for k, v in d.items():
        D[k] = toDict(v) if isinstance(v, dict) else v
    return D

try:
    import config_override
    configs = merge(config_default.configs, config_override.configs)
except ImportError:
    pass

configs = toDict(configs)
