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
    is a "route" decorator replacement for bottle,
    with ability to wrap whole class definition
    or late binding to a class instance or specfic instance method.
'''

from bottle import *

__version__ = '0.01.03'

class PathItem(str) :
    '''
    add ability to access method via attribute style in str.format
    example :
        >>> '{0.@lower.@path}'.format('Hello')
        '/hello
    '''
    def __getattr__(self,attr,*default) :
        if attr[0]=='@' :
            # add support str.format to access method as attribute
            if attr[-1]!=')' :
                attr += '()' # short call without "()"
            x = eval('self.'+attr[1:])
            if isinstance(x,basestring) :
                x = type(self)(x) # to support chained attribute
            return x
        if default :
            return default[0]
        raise AttributeError(attr)

    def path(self,normalize=False,lower=False) :
        x = self
        if normalize :
            x = x.replace('__','/')
        if lower :
            x = x.lower()
        return ('/' + x.strip('/')).rstrip('/')

    def value(self) :
        '''
        return original value
        '''
        return str.__str__(self)

    def view(self,*view) :
        '''
        setting default view
        '''
        if view :
            self._view = '.'.join(view)
        return self

    def __str__(self) :
        '''
        return default view or original value
        '''
        v = getattr(self,'_view',None)
        if v :
            return ('{0.'+v+'}').format(self)
        return self.value()

    def items(self,chr='/',*a,**ka) :
        return [type(self)(x) for x in self.split(chr,*a,**ka)]

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

    app = rka.pop('app',None) # app to be routed
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

        # --- helper/wrapper functions ---
        def ismethod(callback) :
            return callable(callback) and hasattr(callback,'im_class')

        def yieldclassroutes(callback,*basepath):
            re_skipfirst = r'(?:\/\:[^/]*|\/\<.*\>)(?=[$/]?)'
            re_args = r'\/(?=[:<])'
            if basepath :
                for p in basepath :
                    if not p.endswith('/**') :
                        yield p
                        continue
                    p = p.rsplit('/',1)[0]
                    for a in yieldclassroutes(callback) :
                        yield '/'.join([p]+re.split(re_args,a,1)[1:])
                return
            ism = ismethod(callback)
            cnt = 0
            for p in yieldroutes(callback) :
                if ism :
                    p = '{$root}' + ''.join(re.split(re_skipfirst,p,1))
                if not cnt and p.endswith('/index') :
                    yield p.rsplit('/',1)[0]+'/'
                    cnt += 1
                yield p
                cnt += 1

        def pathvars(*a,**ka) :
            kdef = [('$root','@path'),('$class','@path(True)'),('$name','@path(True)')]
            for k,d,v in zip(*zip(*kdef)+[a]):
                if v is None :
                    v = ka.get(k,'')
                if not isinstance(v,PathItem) :
                    v = PathItem(v).view(d)
                ka[k] = v

            for k,v in ka.items() :
                if not isinstance(v,PathItem) :
                    ka[k] = PathItem(v)
            return ka

        def mcallback(fn) :
            return lambda *ma,**mka: fn(*ma,**mka)

        def mname(fn) :
            n = fn.__name__
            if ismethod(fn) :
                n = fn.im_class.__name__ +'.'+n
            return n
        def routeinit(self,path,cra,rka) :
            classpath = type(self).__name__
            rootpath = (path or '').rstrip('/')\
                        .format(**pathvars('',classpath))

            # route items, may override by class's __init__
            if not hasattr(self,'__routeitems__') :
                self.__routeitems__ = MultiDict()
            self.__routeitems__.update(pathvars(rootpath,classpath))

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

                # use arguments from @mroute decorator
                # or classroute decorator.
                for mra,mrka in getattr(m,'__routeargs__',
                                    [((None,)+(cra or tuple()),rka or {})]) :
                    mpaths = []
                    p = mrka.pop('path',mra[0] if mra else None)
                    if mra:
                        mra = mra[1:]
                    if p :
                        mpaths = makelist(p)

                    # if no mpath, use yieldroutes to generate route
                    # otherwise, yield that mpath with /** transforms
                    mpaths = list(yieldclassroutes(m,*mpaths))

                    # formatting route variable
                    if mpaths :
                        ritems = pathvars(None,None,m.__name__,**self.__routeitems__)
                        mpaths = [_x.format(**ritems) for _x in mpaths]

                    if DEBUG:
                        rm = mrka.get('method',mra[0] if mra else 'classroute')
                        print '{2} {0}():{1} '.format(
                                    mname(m),'\n  '.join(['']+mpaths),rm)

                    (app.route if app else route)(mpaths,*mra,**mrka)(mcallback(m))

        # use wrapper to support stack multiple classroute
        def initwrap(path,cra,rka,baseinit) :
            def wrapper(self,*a,**ka) :
                # push back original method
                # to support multiple instances
                baseinit(self,*a,**ka)
                self.__class__.__init__ = baseinit
                # support collection of paths
                for p in makelist(path) or [None] :
                    routeinit(self,p,cra,rka)
            return wrapper
        # ----- end helper/wrapper functions ------

        # check if not a class, pass to default route
        if not isinstance(callback,type) :
            if not callable(callback) \
                and type(callback).__name__ not in __builtins__:
                # bind to an instance
                # support collection of paths
                for p in makelist(path) or [None] :
                    routeinit(callback,p,cra,rka)
                return callback

            path = list(yieldclassroutes(callback,*makelist(path)))
            ritems = pathvars('','',callback.__name__)
            if ismethod(callback) :
                ritems = pathvars(None,callback.im_class.__name__,**ritems)
            if path :
                path = [_x.format( **ritems) for _x in path]

            if DEBUG:
                rm = rka.get('method',cra[0] if cra else 'route')
                print '{2} {0}():{1}'.format(
                            mname(callback),
                            '\n  '.join(['']+(path or '/.*')),
                            rm)
            return route(path,*cra,**rka)(mcallback(callback))
        callback.__init__ = initwrap(path,cra,rka,callback.__init__)
        return callback

    return decorator(callback) if callback else decorator

# for single entry to import classroute
classroute.route = mroute
classroute.skip = skiproute

if __name__ == '__main__':     # classroute Example

    debug() # enable verbose route path binding

    class A(object) :
       def __init__(self,name='World') :
            self.name = name

       def hello(self,name=None) :
           yield 'Hello '
           yield name or self.name

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

    #with helper function "mroute" (or "classroute.route) and "skiproute" (or "classroute.skip")
    #fine tune for individual method in the class is possible.
    # bind to "/B/hello","/B/hello/<name>","/B/say/hello","/B/say/hello/<name>"
    @classroute('{$class}')
    class B(A):
        @classroute.route('{$root}/say/hello',['GET','POST'])
        def say__hi(self,name=None) :
              redirect('{$root}/hello/{0}',name or self.name,**self.__routeitems__)

        @classroute.skip
        def myfunc(self,name='') :
            yield 'myfunc'
            if name :
                yield ' ('+name+')'

    # or use as route replacement, with special meaning of 'index'
    # bind to "/","/index"
    @classroute
    def index() :
        redirect('/hello')

    # create instance, to bind all route definition
    A1()
    A2()
    A3()
    b = B()

    # support for late binding to individual instance's method
    # bind to "/a-bottle"
    classroute('{$class}-bottle')(A('Bottle').hello)

    # force late binding to @skiproute method
    # bind to "/my","/my/:name"
    classroute('/my/**')(b.myfunc)

    # also support for late binding to instance
    # bind to "/bottle/..."
    classroute('/bottle')(A('Bottle'))

    #start server
    run()


