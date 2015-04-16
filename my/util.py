import os, sys, time, re, subprocess
import codecs

baseencode = 'cp1251'           # default encoding (also filesystem encoding on windows)
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

def makebool( value, default = True ):
    value = value.lower()
    if value in ['y','yes','t','true']:
        return True
    if value in ['n','no','f','false']:
        return False
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
    return str_encode( str_decode( s, src ), 'cp866' )


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

def PRINT_MARK(mark):
    import inspect
    frame = inspect.stack()[1]
    print "%s at %s:%s" % (mark, frame[1], frame[2])
    exit()



"""
################################################################
#                  		   STDOUT					           #
################################################################
"""

def init_console():
    # Set console encoding
    reload(sys)
    sys.setdefaultencoding('utf-8')

DEBUG_LEVEL = 0
def dbg_print( level, s ):
    if level <= DEBUG_LEVEL:
        print s

def print_mark( mark ):
    sys.stdout.write(mark)
    sys.stdout.flush()

def unicformat( s, arg = None ):
    if arg is None:
        return str_decode( s, scriptencoding )
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

def say( s = '', arg = None ):
    print unicformat( s, arg ).encode('cp866','xmlcharrefreplace')

def say_cp866( s ):
    print str_encode( s, 'cp866' )

def getinput( s ):
    if s:
        s = str_transcode(s,scriptencoding,'cp866')
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
        ##print "ContextManager.__enter__(%s)" % str(self.lst)	##DEBUG
        for o in self.lst:
            safe_run(o,"__enter__")
        return self	# what will be binded to "as" argument

    def __exit__( self, *kw, **kww ):
        ##print "ContextManager.__exit__(%s)" % str(self.lst)	##DEBUG
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
        print "PsuedoMultiThread.__exit__"	##DEBUG
        self.finalize_tasks()
        safe_run( self.processorObj, '__exit__', *kw, **kww )

    def __del__( self ):
        print "PsuedoMultiThread.__del__"	##DEBUG
        self.finalize_tasks()

    def add_task( self, value ):
        if self.verbose > 2:
            print "add_task(%s)" % str_transcode(value,None,'cp866')
        cmd = self.processorObj.add( value )
        if self.verbose > 1: print cmd
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
            print "!! Fail to process value: %s" % str(e)

        while ( len(self.task_queue) >= self.max_threads ):
            if self.verbose > 2: print "[%d/%d]" % ( len(self.task_queue), self.max_threads )
            self._task_process()

    def  finalize_tasks( self ):
        if self.verbose > 1: print "finalize_tasks()"
        while len(self.task_queue) > 0:
            self._task_process()

    # process first task in queue
    def _task_process( self ):
        if self.verbose > 1: print "_task_process()"
        value, fp = self.task_queue.pop(0)
        stdout,stderr = fp.communicate()
        ##print "STDOUT:\n%s\nSTDERR:%s\n" %(stdout,stderr)
        if stderr not in [ None, '']:
            print "failed task %s\nERROR:%s" % ( str_encode(value,'cp866'), str_encode(stderr,'cp866') )
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
            print "not fount %s"%fname0
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
        print "FileInfoCache.__exit__"		##DEBUG
        self.saveFile()

    def __del__( self ):
        print "FileInfoCache.__del__"		##DEBUG
        self.saveFile()


    def _getMTimeTag( self, fname ):
        if os.path.isfile( fname ):
            return u"%d+%s" % (os.path.getsize(fname), os.path.getmtime(fname))
        else:
            return ''

    # MANUALLY FLUSH CACHE (better to use context)
    def saveFile( self ):
        print "saveFile()"			##DEBUG
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
        ##print "get %s:>> %s >> %s" % (fname, self._getMTimeTag(fname), self.cache.get(fname,[None]) )
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
        ##print "update %s %s" % (fname, enforce)
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
        safe_run( self.cacheObj, '__enter__', *kw, **kww )
        return self

    def __exit__( self, *kw, **kww ):
        safe_run( self.cacheObj, '__exit__', *kw, **kww )

    def validate( self, value ):
        if self.validator:
            return self.validator( value )
        return True

    def add( self, fname ):
        value = self.cacheObj.get( fname )
        if value is not None:
            if ( ( value=='' and self.aggresiveCache ) or self.validate(value) ):
                if self.verbose > 2:
                    say( "%s: exists in cache", fname )
                self.processed.append( fname )
                return None
            self.cacheObj.delete(fname)

        if self.verbose > 1:
            say( "get info for: %s", fname )
        fname = str_encode(fname,'cp1251')      # CPYTHON do not understand unicode; PYPY works ok with unicode so this not need for it
        if self.shell:
            fname = '"%s"' % fname
        return self.cmd + [ fname ]

    def handle( self, fname, value ):
        value = value.rstrip('\n\r')
        ##print " handle%s\n%s\n" % (fname,value)
        if self.validate( value ):
            self.cacheObj.update( fname, value )
            self.processed.append( fname )
        elif self.verbose:
            if self.aggresiveCache:
                self.cacheObj.update( fname, '' )
            say( "INVALID OUTPUT(PROBABLY NOT GOOD MEDIA): %s", fname )


##################
def scan_dir( dirpath, recursive = True, pattern = None, caseInsensetive = True, verbose = True):
    if verbose:
        print "scan_dir(%s)"% str_transcode(dirpath,None,'cp866')
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

