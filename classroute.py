#-------------------------------------------------------------------------------
# Name:        classroute
# Purpose:     class level route decorator for bottle
#
# Author:      jojosati
#
# Created:     27/05/2012
# Copyright:   (c) jojosati 2012
# Licence:     same as bottle.py
#-------------------------------------------------------------------------------
#!/usr/bin/env python

'''
classroute
a "route" decorator replacement for bottle,
plus ability to wrap class definition and instance method.
'''

from bottle import *

__version__ = '0.01.01'


def normalizepath(p) :
    return ('/' + p.replace('__','/').strip('/')).rstrip('/')


class PathItem(object):
    '''
    PathItem - a str represent for path variable  {$root},{$class},{$name}
    with some chained-transformable features as :
        .content - content only strip '/'
        .path - empty or content + starts with '/'
        .dir - path + ends with '/'
        .low - lower case
        .up - uppercase
        .title - capitalize first letter
        .normpath - same path with replacement of '__' to '/'
        .normpathlow - normpath + low
        .value - the original value
        .items - split path to selectable item as {$name.items[0].up}
    all features is chainable
    example:
        >>> "{0.normpath.content.items[0].title}".format(PathItem('//abc__def__'))
        'Abc'
    '''
    def __init__(self,value,default=None) :
        self._value = value
        self._default = default

    @property
    def _content(self) :
        return self._value.strip('/')

    @property
    def _path(self) :
        return ('/'+self._content).rstrip('/')

    @property
    def _normpath(self) :
        return normalizepath(self._value)

    @property
    def _normpathlow(self) :
        return self._normpath.lower()

    def __str__(self) :
        if callable(self._default) :
            return self._default(self)
        if isinstance(self._default,basestring) :
            return self._default
        if self._default == 1 :
            return self._normpathlow
        if self._default == 2 :
            return self._normpath
        return self._path if self._default else self._value

    @property
    def value(self) :
        return PathItem(self._value)

    @property
    def p(self) :
        return PathItem(self.__str__())

    @property
    def content(self) :
        return PathItem(self._content)

    @property
    def path(self) :
        return PathItem(self._path)

    @property
    def dir(self) :
        return PathItem(self._path+'/')

    @property
    def normpath(self) :
        return PathItem(self._normpath)

    @property
    def normpathlow(self) :
        return PathItem(self._normpathlow)

    @property
    def up(self) :
        return PathItem(self._value.upper())

    @property
    def low(self) :
        return PathItem(self._value.lower())

    @property
    def title(self) :
        return PathItem(self._value.title())

    @property
    def normalize(self) :
        return PathItem(normalizepath(self._value))

    @property
    def items(self) :
        return [PathItem(x) for x in self._value.split('/')]

def ismethod(callback) :
    return callable(callback) and hasattr(callback,'im_class')

def yieldclassroutes(callback):
    ism = ismethod(callback)
    re_skipfirst = r'(?:\/\:[^/]*|\/\<.*\>)(?=[$/]?)'
    cnt = 0
    for p in yieldroutes(callback) :
        if ism :
            p = '{$root}' + ''.join(re.split(re_skipfirst,p,1))
        if not cnt and p.endswith('/index') :
            yield p.rsplit('/',1)[0]+'/'
            cnt += 1
        yield p
        cnt += 1


def mroute(*a,**ka) :
    def decorator(callback) :
        if not hasattr(callback,'__routeargs__') :
            callback.__routeargs__ = []
        callback.__routeargs__.append((a,ka))
        return callback
    return decorator

def skiproute(callback) :
    callback.__routeargs__ = []
    return callback

def classroute(*ra,**rka) :
    from bottle import DEBUG

    callback = rka.pop('callback',None)
    if len(ra)>=3 :
        callback = ra[2]
        ra = ra[:2]+(None,)+ra[3:]
    if ra and (callable(ra[0]) or isinstance(ra[0],type)) :
        callback,ra = ra[0],(None,) + ra[1:]

    def decorator(callback):
        functools.wraps(callback)

        # get path argument
        path = rka.pop('path',None)
        path = (ra or [path])[0]
        cra = (ra or (None,))[1:]
        # method callback wrapper
        def mcallback(fn) :
            return lambda *ma,**mka: fn(*ma,**mka)
        def mname(fn) :
            n = fn.__name__
            if ismethod(fn) :
                n = fn.im_class.__name__ +'.'+n
            return n
        # check if not a class, pass to default route
        if not isinstance(callback,type) :
            if not path :
                path = list(yieldclassroutes(callback))
            ritems = {
                '$name' : PathItem(callback.__name__,2), #normpath
                '$root' : '',
                    }
            if ismethod(callback) :
                ritems.update({
                        '$class' : PathItem(callback.im_class.__name__,1), #normpathlow
                        })
            if path :
                path = [_x.format( **ritems) for _x in makelist(path)]

            if DEBUG:
                rm = rka.get('method',cra[0] if cra else 'route')
                print '{2} {0}():{1}'.format(
                            mname(callback),
                            '\n  '.join(['']+(path or '/.*')),
                            rm)
            return route(path,*cra,**rka)(mcallback(callback))

        classpath = callback.__name__


        def routeinit(self,path,cra,rka) :
            rootpath = (path or '').rstrip('/')\
                        .format(**{
                            '$class':PathItem(classpath,1),  #normpathlow
                            })

            # route items, may override by class's __init__
            if not hasattr(self,'__routeitems__') :
                self.__routeitems__ = MultiDict()
            self.__routeitems__.update({
                    '$root': PathItem(rootpath,3), #path
                    '$class': PathItem(classpath,1),  #normpathlow
                    })

            # add route for all method in class
            for n in dir(self) :
                # skip _xxxx name
                if n[0]=='_' :
                    continue
                m = getattr(self,n)

                # check if it's a method, (not use expensive inspect.ismethod)
                if not ismethod(m) :
                    continue

                if hasattr(m,'__routeargs__') :
                    # arguments from mroute/skiproute decorator
                    if not m.__routeargs__ :
                        # skip route for this method
                        continue

                for mra,mrka in getattr(m,'__routeargs__',
                                    [((None,)+(cra or tuple()),rka or {})]) :
                    mpaths = []
                    p = mrka.pop('path',mra[0] if mra else None)
                    if mra:
                        mra = mra[1:]
                    if p :
                        mpaths = makelist(p)

                    if not mpaths :
                        # try to parse __doc__ (undoc&never use?)
                        # for @route declaration within method or within class
                        re_route = r'(?:^\s*|\s+)\@mroute\s*\=(.*)'
                        docroutes = re.split(re_route, m.__doc__ or '')[1::2] \
                                or re.split(re_route, self.__class__.__doc__ or '')[1::2]
                        for x in map(eval,docroutes) :
                            mpaths.extend(makelist(x))

                    if not mpaths :
                        # if no declaration, use yieldroutes to generate route
                        # note: needs skip first arguments of class method.
                        mpaths.extend(yieldclassroutes(m))

                    # formatting route variable
                    if mpaths :
                        methodpath =  normalizepath(m.__name__)
                        ritems = {'$name' : PathItem(methodpath,2)} #normpath
                        ritems.update(self.__routeitems__)
                        mpaths = [_x.format(**ritems) for _x in mpaths]

                    if DEBUG:
                        rm = mrka.get('method',mra[0] if mra else 'classroute')
                        print '{2} {0}():{1} '.format(
                                    mname(m),'\n  '.join(['']+mpaths),rm)

                    route(mpaths,*mra,**mrka)(mcallback(m))

        # use wrapper to support stack multiple classroute
        def initwrap(path,cra,rka,baseinit) :
            def wrapper(self,*a,**ka) :
                # push back original method
                # to support multiple instances
                baseinit(self,*a,**ka)
                # support collection of paths
                for p in makelist(path) or [None] :
                    routeinit(self,p,cra,rka)
                self.__class__.__init__ = baseinit
            return wrapper
        callback.__init__ = initwrap(path,cra,rka,callback.__init__)
        return callback

    return decorator(callback) if callback else decorator


if __name__ == '__main__':
    # classroute Example
    debug() # enable verbose route path binding

    class A(object) :
       def __init__(self,name='World') :
            self.name = name

       def hello(self,name=None) :
           yield 'Hello '
           yield name or self.Name

    # bind to "/hello","/hello/<name>"
    @classroute
    class A1(A) :
       pass

    # bind to "/a2/hello","/a2/hello/<name>"
    @classroute('{$class}',['POST','GET'])
    class A2(A) :
       pass

    # bind to "/a/hello","/a/hello/<name>","/aa/hello","/aa/<name>"
    # same as @classroute(['/aa','/a')
    @classroute('/a')
    @classroute('/aa')
    class A3(A):
      pass

    # bind different root with different instance of same class
    # bind to "/john/hello","/john/hello/<name>"
    classroute('john')(A)('john')
    # bind to "/jane/hello","/jane/hello/<name>"
    classroute('jane')(A)('jane')

    #with helper function "mroute" and "skiproute"
    #fine tune for individual method in the class is possible.
    # bind to "/b/hello","/b/hello/<name>","/b/say/hello","/b/say/hello/<name>"
    @classroute('{$class}')
    class B(A):
        @mroute('{$root}/say/hello',['GET','POST'])
        def say__hi(self,name=None) :
              redirect('{$root}/hello/{0}',name or self.name,**self.__routeitems__)

        @skiproute
        def myfunc(self) :
            yield 'myfunc'

    # or use as route replacement, with special meaning of 'index'
    # bind to "/","/index"
    @classroute
    def index() :
        redirect('/hello')

    # also support for late binding to instance's method
    # bind to "/a/marcel"
    classroute('{$class}/marcel')(A('Marcel').hello)

    # create instance, to bind all route definition
    A1()
    A2()
    A3()
    b = B()

    # force binding to @skiproute method
    # bind to "/myfunc"
    classroute(b.myfunc)

    run()

