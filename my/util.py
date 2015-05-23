import os, sys, time, re, subprocess
import codecs

baseencode = 'cp1251'           # default encoding (also filesystem encoding on windows)
console_encoding = 'cp866'      # console encoding
scriptencoding = baseencode
base_path = sys.path[0]         # directory of script


# Set console encoding
def prepare_console():
    reload(sys)
    sys.setdefaultencoding('utf-8')

"""
######### CLASSES TO PROCESS VALUES ###########
"""

# PURPOSE: safe get integer value of "value"(if it is not an integer return "default")
def makeint( value, default = 0 ):
    try: return int(value)
    except: return default

def makefloat( value, default = 0 ):
    try: return float(value)
    except: return default

def makebool( value, default = True ):
    try:
        value = value.lower()
        if value in ['y','yes','t','true']:
            return True
        if value in ['n','no','f','false']:
            return False
    except:
        pass
    return makeint( value, default )

# PURPOSE: split "value"(raw or splited string) with separator list "sep_list"
#               + remove empty entries (except leading)
def splitl( value, sep_list = [ '|', '+' ], removeEmpty = False ):
    if value is None:
        return []
    if isinstance(value,str) or isinstance(value,unicode):
        ar = [value]
    else:
        ar = list(value)
    for sep in sep_list:
        ar = reduce( lambda x,y: x + y.split(sep), ar, [] )
    ar = map( lambda x: x.strip(), ar )
    if removeEmpty:
        firstempty = len(ar) and (ar[0]=='')
        ar = filter( len, ar )
        if firstempty and len(ar):
            return [''] + ar
    return ar

# safe string strip as a function (to use in map)
def vstrip( value ):
    try: return value.strip()
    except: return ''

#
def adddict( value ):
    global cfg
    ptype, pname, value = value
    return _mycfg.parse_pattern( value, cfg.pattern_template['DETECT'] )

"""
######### STR ENCODING PROCESSING ###########
"""

# SAFE MAKE UNICODE STRING
def str_decode( s, enc=None ):
    if isinstance(s, str):
        if enc is None:
            enc = baseencode
        #print "{decode from %s}" %enc
        s = s.decode(enc,'xmlcharrefreplace')
    return s

# SAFE MAKE FROM UNICODE STRING
def str_encode( s, enc=None ):
    if isinstance(s, unicode):
        if enc is None:
            enc = baseencode
        #print "{encode to %s}" %enc
        s = s.encode(enc,'xmlcharrefreplace')
    return s

# SAFE TRANSCODING FROM ONE ENCODING TO ANOTHER
def str_transcode( s, src, tgt ):
    if src != tgt:
        return str_encode( str_decode( s, src ), tgt )
    else:
        return str_encode( s, tgt )


# TRANSCODE src(baseencode) -> cp866
def str_cp866( s, src = None ):
    return str_encode( str_decode( s, src ), console_encoding )


def str_encode_all( lst, enc = None ):
    return map( lambda s: str_encode(s,enc), lst )

def str_decode_all( lst, enc = None ):
    return  map( lambda s: str_decode(s,enc), lst )


"""
####     ######
"""
def grep_compile( pattern, caseInsensetive = False ):
    pattern = pattern.replace('.','\\.').replace('?','.?').replace('*','.*?').replace('^','\\^').replace('$','\\$') + '$'
    if caseInsensetive:
        return re.compile( pattern, re.IGNORECASE )
    return re.compile( pattern )

def PRINT_MARK(mark):
    import inspect
    frame = inspect.stack()[1]
    say( "%s at %s:%s", (mark, frame[1], frame[2]) )
    #exit()

"""
################################################################
#                  		   DEBUG PRINT     			           #
################################################################
"""

logfile = None
DEBUG_LEVEL = 0
def DBG( level, s, *kw ):
    if logfile and level <= DEBUG_LEVEL:
        if len(kw):
            s = unicformat(s,*kw)
        logfile.write(s+'\n')
def DBG_info( s, *kw ):
    DBG(0,s,*kw)
def DBG_trace( s, *kw ):
    DBG(1,s,*kw)
def DBG_trace2( s, *kw ):
    DBG(2,s,*kw)


_debugGuard = False
def debugDump( obj, short = False ):
    global _debugGuard
    if _debugGuard:
         return
    _debugGuard = True
    rv = "Object %s (%d)" % ( obj.__class__, id(obj) )
    for attr in dir(obj):
        if short and attr.startswith('__') and attr.endswith('__'):
                continue
        rv += "\nobj.%s = %s" % (attr, getattr(obj,attr))
    _debugGuard = False
    return rv

"""
################################################################
#                  		   STDOUT					           #
################################################################
"""

def init_console():
    # Set console encoding
    reload(sys)
    sys.setdefaultencoding('utf-8')

def print_mark( mark ):
    sys.stdout.write(mark)
    sys.stdout.flush()

def unicformat( s, *arg ):
    if not len(arg):
        return str_decode( s, scriptencoding )
    if len(arg)==1:
        arg = arg[0]

    if isinstance(arg,tuple):
        arg=list(arg)
    if not isinstance(arg,list):
        arg = [arg]
    for idx in xrange(0,len(arg)):
        if isinstance(arg[idx],str):
            arg[idx] = str_decode( str(arg[idx]) )
    try:
        return str_decode( s, scriptencoding ) % tuple(arg)
    except UnicodeDecodeError:
        for a in arg: print type(a)
        raise
    except UnicodeEncodeError:
        for a in arg: print type(a)
        raise

def say( s = '', *arg ):
    s = unicformat( s, *arg )
    print s.encode(console_encoding,'xmlcharrefreplace')
    DBG(0,s)

def say_cp866( s ):
    print str_encode( s, console_encoding )

def getinput( s ):
    if s:
        s = str_transcode(s,scriptencoding,console_encoding)
        print_mark(s)
    return raw_input('')

def getchar():
    return getch()


"""
===============================================================
                CONTEXT MANAGER
    remember given list of objects or func.
    OnEnter: call obj.__enter__() for all objects int the list
                in the order of appearance
    OnExit:  call given function and obj.__exit__() for objects
                in the order of appearance


    USAGE:  with guard_objects( [obj1, obj2, obj3 ] ) as sentry:
                something here
===============================================================
"""

# RUN OBJECT METHOD IF EXISTS
def safe_run( obj, method, *kw, **kww ):
    if hasattr(obj,method):
        getattr(obj,method)( *kw, **kww )

class ContextManager(object):
    def __init__( self, lst ):
	self.lst = lst

    def __enter__( self ):
        DBG_trace( "ContextManager.__enter__(%s)", str(self.lst) )	##DEBUG
        for o in self.lst:
            safe_run(o,"__enter__")
        return self	# what will be binded to "as" argument

    def __exit__( self, *kw, **kww ):
        DBG_trace("ContextManager.__exit__(%s)", str(self.lst) )	##DEBUG
        for o in self.lst:
            if hasattr(o,"__exit__"):
                o.__exit__( *kw, **kww )
            elif callable( o ):
                o(*kw, **kww)

def guard_objects( lst ):
	return ContextManager( lst )


"""
===============================================================
      CLASS FOR PSEUDO MULTITHREAD RUNNING SEVERAL JOBS

    worker = PsuedoMultiThread( handlerObj,
                                max_t,      - max thread
                                verbose,    = numeric (level of how much output)
                                shell )     = "shell" argument for calling subprocess
                                              ( give value as list or as a plain string)

    worker.add_task( input_value )      # input_value depends on handler

    NOTE:
    Have to be guarded by context: with PsuedoMultiThread() as worker:
    or manually call worker.__exit__() to finalize task

===============================================================
"""

class PsuedoMultiThread(object):
    max_threads = 1
    shell = False
    verbose = 1         # 0 -no message, 1-important only, 2,3...-debug also

    def __init__( self,  processorObj, max_t, verbose = None, shell = None ):
        self.task_queue = []
        self.processorObj = processorObj
        if verbose is not None:
            self.verbose = verbose
        if shell is not None:
            self.shell = shell
        self.max_threads = max_t

    def __enter__( self, *kw, **kww ):
        safe_run( self.processorObj, '__enter__', *kw, **kww )
        return self
    def __exit__( self, *kw, **kww ):
        DBG_trace("PsuedoMultiThread.__exit__")	##DEBUG
        self.finalize_tasks()
        safe_run( self.processorObj, '__exit__', *kw, **kww )
    def __del__( self ):
        DBG_trace("PsuedoMultiThread.__del__")	##DEBUG
        self.finalize_tasks()

    def add_task( self, value ):
        DBG_trace( "add_task(%s)", [value] )
        cmd = self.processorObj.add( value )
        DBG_trace("cmd=%s", [cmd])
        if cmd is None:
            return

        try:
            if self.shell:
                cmd = ' '.join(cmd)
            fp = subprocess.Popen( cmd, stdout=subprocess.PIPE, shell = self.shell )
            ##print "%s\n%s", (str(cmd),str(fp))
            if not fp:
                raise Exception( "Fail to open pipe")
            self.task_queue.append ( [value, fp] )
        except Exception as e:
            say( "!! Fail to process value: %s", str(e) )

        while ( len(self.task_queue) >= self.max_threads ):
            if self.verbose > 2: DBG_trace2( u"[%d/%d]" % ( len(self.task_queue), self.max_threads ) )
            self._task_process()

    def  finalize_tasks( self ):
        DBG_trace( "finalize_tasks()" )
        while len(self.task_queue) > 0:
            self._task_process()

    # process first task in queue
    def _task_process( self ):
        DBG_trace( "_task_process()" )
        value, fp = self.task_queue.pop(0)
        stdout,stderr = fp.communicate()
        ##print "STDOUT:\n%s\nSTDERR:%s\n" %(stdout,stderr)
        if stderr not in [ None, '']:
            say( "failed task %s\nERROR:%s", ( value, stderr ) )
        else:
            self.processorObj.handle( value, stdout )

"""
===============================================================
                FILE-RELATED INFO CACHE

    Keep any information related to file in cache.
    Safe(if file was changed, then cache record become invalid)

    HOW TO USE:
    which FileInfoCache( cachefilename ) as cache:
        val0 = cache.get( fname0 )
        if val0 is None:
            print "not found %s"%fname0
        cache.update( fname1, value1 )
        cache.delete( fname2 )
===============================================================
"""
class FileInfoCache(object):
    EXPIRE_AFTER = 3600*24*30       # how long (in seconds) records are valid
                                    # -- to keep cache file reasonable small

    def __init__( self, name ):
        self.fname = os.path.join( base_path, name )
        self.cache = {}             # main container: cache[fname] = [ 0mtime_tag, 1tstamp_of_add, 2value]
        self.dirty = False

        try:
            with codecs.open( self.fname, 'r', encoding='utf8' ) as f:
                lines = f.readlines()
            tsnow = int(time.time())
            for l in lines:
                a = l.rstrip('\n').split('|',3)
                if len(a)<4:
                    continue
                cachedFname, modifiedTime, tstamp, value = a
                tstamp = abs(makeint(tstamp))
                if cachedFname in self.cache:
                    if tstamp < self.cache[cachedFname][1]:
                        continue
                if (tsnow-tstamp) > self.EXPIRE_AFTER:
                    tstamp = - tstamp
                    self.dirty = True
                self.cache[cachedFname] = ( modifiedTime, tstamp, value )
        except  IOError as err:
            pass


    def __exit__( self, *kw, **kww ):
        DBG_trace("FileInfoCache.__exit__")		##DEBUG
        self.saveFile()
    def __del__( self ):
        DBG_trace("FileInfoCache.__del__")		##DEBUG
        self.saveFile()


    def _getMTimeTag( self, fname ):
        if os.path.isfile( fname ):
            return u"%d+%s" % (os.path.getsize(fname), os.path.getmtime(fname))
        else:
            return ''

    # MANUALLY FLUSH CACHE (better to use context)
    def saveFile( self ):
        DBG_trace( "FileInfoCache.saveFile()"	)		##DEBUG
        if self.dirty:
            return

        self.dirty = False
        with codecs.open( self.fname, 'w', encoding='utf8' ) as f:
            for k in sorted( self.cache ):
                v = self.cache[k]
                if v[1]>=0:
                    f.write( "%s|%s|%s|%s\n" % (k,v[0],v[1],v[2]) )

    # SAFE GET VALUE FROM CACHE (None - not found or invalid)
    def get( self, fname, check = True ):
        DBG_trace( "FileInfoCache.get %s:>> %s >> %s", (fname, self._getMTimeTag(fname), self.cache.get(fname,[None]) ) )
        if fname not in self.cache:
            return None
        if self._getMTimeTag(fname) != self.cache[fname][0]:
            self.delete(fname)
            return None
        return self.cache[fname][2]

    # DELETE CACHE RECORD
    def delete( self, fname ):
        if fname in self.cache:
            del self.cache[fname]
            self.dirty = True

    # UPDATE VALUE IN CACHE.
    # quick     if =True - immediate append to the end of cachefile
    # enforce   if =False - do not update if file info exists
    def update( self, fname, value, quick = True, enforce = False ):
        DBG_trace( "FileInfoCache.update( %s=>%s ,%s)", (fname, value, enforce) )
        if not enforce and fname in self.cache:
            return
        self.cache[fname] = ( self._getMTimeTag(fname), int(time.time()), value )
        if quick:
            try:
                with codecs.open( self.fname, 'a', encoding='utf8' ) as f:
                    f.seek( 0, os.SEEK_END )
                    v = self.cache[fname]
                    f.write( u"%s|%s|%s|%s\n" % ( fname, v[0], v[1], v[2] ) )
            except IOError as e:
                self.dirty = True
        else:
            self.dirty = True

"""
===============================================================
                WORKER FOR PsuedoMultiThread()

    Try to find valid value for the file in "cacheObj".
     If not found then allow to add job (run "cmd" with filename)
     and remember to cache

    processor = CachedProcessor( [cmd, here],
                                 cacheObj,      # FileInfoCache object to cache file-info
                                 validator,     # if given - function with 1 arg
                                                   (return False if value have incorrect format)
                                                   or could replace self.validate() in derived
                                 verbose,       # level of verbosity(numeric)
                                 shell )        # argument to run task
    NOTES:
        1. Is argument for PsuedoMultiThread()
        2. Results are: filled cacheObj and list of processed files in
            self.processed (both loaded and got from cache)

===============================================================
"""
class CachedProcessor(object):
    aggresiveCache = False   # False - rescan empty records, True - ignore empty cache records
    verbose = 3             # 0 - silent, 1-only errors, 2-valuable info, 3-debug

    def __init__( self, cmd, cacheObj, validator=None, shell = False, verbose = None ):
        self.cacheObj = cacheObj
        if isinstance(cmd, str) or isinstance(cmd,unicode):
            cmd = [cmd]
        self.cmd = list(cmd)
        self.validator = validator
        if verbose is not None:
            self.verbose = verbose
        self.processed = []
        self.shell = shell

    def __enter__( self, *kw, **kww ):
        DBG_trace("CachedProcessor.__enter__")		##DEBUG
        safe_run( self.cacheObj, '__enter__', *kw, **kww )
        return self

    def __exit__( self, *kw, **kww ):
        DBG_trace("CachedProcessor.__exit__")		##DEBUG
        safe_run( self.cacheObj, '__exit__', *kw, **kww )

    def validate( self, value ):
        if self.validator:
            return self.validator( value )
        return True

    def add( self, fname ):
        value = self.cacheObj.get( fname )
        if value is not None:
            if ( ( value=='' and self.aggresiveCache ) or self.validate(value) ):
                DBG_trace( "add %s: exists in cache", fname )
                self.processed.append( fname )
                return None
            self.cacheObj.delete(fname)

        sayfunc = say if self.verbose > 1 else DBG_trace
        sayfunc( "get info for: %s", fname )
        fname = str_encode(fname,'cp1251')      # CPYTHON do not understand unicode; PYPY works ok with unicode so this not need for it
        if self.shell:
            fname = '"%s"' % fname
        return self.cmd + [ fname ]

    def handle( self, fname, value ):
        value = value.rstrip('\n\r')
        DBG_trace( "CachedProcessor.handle(%s)\n%s\n", (fname,value) )
        if self.validate( value ):
            self.cacheObj.update( fname, value )
            self.processed.append( fname )
        elif self.verbose:
            if self.aggresiveCache:
                self.cacheObj.update( fname, '' )
            say( "INVALID OUTPUT(PROBABLY NOT GOOD MEDIA): %s", fname )

"""
    Customized implementation of OrderedDict
    Difference is: If set to existed value, than it is moved to the tail of iterator

    TODO: Important!!
        Looks like this is implementation-dependent.
        many operations could broke the order
"""
import collections
class MyOrderedDict( collections.OrderedDict ):
    def __init__(self, *kw,**kww):
        super(MyOrderedDict,self).__init__(*kw, **kww)

    """
    def __setitem__(self, key, value, dict_setitem=dict.__setitem__):
        DBG_trace( debugDump(self) )
        __map = getattr(self,'_OrderedDict__map')
        # Setting an existent item remove its from linked list
        if key in self:
            link_prev, link_next, _ = __map.pop(key)
            link_prev[1] = link_next                        # update link_prev[NEXT]
            link_next[0] = link_prev                        # update link_next[PREV]

        # Creates a new link at the end of the linked list
        root = getattr(self,'_OrderedDict__root')
        last = root[0]
        last[1] = root[0] = __map[key] = [last, root, key]
        return dict_setitem(self, key, value)
    """

    def __repr__(self):
        return strMap(self,True,False)
    def __str__(self):
        return strMap(self,True,False)

    #"""
    def __setitem__(self, key, value, dict_setitem=dict.__setitem__):
        ##DBG_trace("_set_(%s,%s)"%(key,value))
        if key in self:
            super(MyOrderedDict,self).__delitem__(key)
        return super(MyOrderedDict,self).__setitem__(key,value)
    #"""

    def update( self, src ):
        if isinstance( src, dict ):
            for k,v in src.items():
                self.__setitem__(k,v)
        else:
            for k,v in iter(src):
                self.__setitem__(k,v)

    def setdefault( self, key, value ):
        if key not in value:
            self.__setitem__( key, value )
        return self[key]


def strMap( d, isRepr=True, multiLine=False):
    out = map( lambda i: u"%s: %s" %(repr(i[0]), repr(i[1])), d.iteritems())
    if multiLine:
        prefix = (u"{%s}==>\n"%type(d)) if isRepr else ""
        return u"%s%s" % ( prefix, '\n'.join(out))
    else:
        prefix = (u"%s: "%type(d)) if isRepr else ""
        return u"{%s}" % ( ', '.join(out))


"""##################"""

def scan_dir( dirpath, recursive = True, pattern = None, caseInsensetive = True, verbose = True):
    sayfunc = say if verbose > 1 else DBG_trace
    sayfunc( "scan_dir(%s)", dirpath )
    if not os.path.isdir(dirpath):
        return []

    # convert given "pattern" from "str1|str2" or [str1,str2,.] ---> [regexp,regexp,..]
    if pattern is not None:
        if not isinstance(pattern,list):
            pattern = filter( len, map(lambda s: s.strip(), pattern.split('|')) )
        if '*' in pattern:
            pattern = None
        else:
            pattern = map( lambda s: grep_compile(s, caseInsensetive), pattern)

    to_process = []
    dirlst = os.listdir(dirpath)
    for f in dirlst:
        f = os.path.join(dirpath,f)
        if os.path.isdir(f):
            if recursive:
                to_process += scan_dir( f, recursive, pattern )
        else:
            f=str_decode(f,None)
            if pattern is None:
                to_process.append(f)
            else:
                _, fname = os.path.split(f)
                for p in pattern:
                    if p.match(fname):
                        to_process.append(f)
                        break
    return to_process

