#!usr/bin/env python3
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

#修改默认配置中需要更改的地方
def merge(defaults, override):
    r = {}
    #配置数据以字典形式储存，将其键值对拆分开
    for k, v in defaults.items():
        #若数据名出现在override中，检查其是否是字典
        if k in override:
            #若是将其交给merge函数再次拆分
            if isinstance(v, dict):
                r[k] = merge(v, override[k])
            #否则，储存到r中
            else:
                r[k] = override[k]
        else:
            r[k] = v
    return r

#将更改后的配置数据传入自定义字典中
def toDict(d):
    D = Dict()
    for k, v in d.items():
        D[k] = toDict(v) if isinstance(v, dict) else v
    return D

try:
    import config_override
    configs = merge(config_default.configs, config_override,.configs)
except ImportError:
    pass

configs = toDict(configs)