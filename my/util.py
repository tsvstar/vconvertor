import os, sys, time, re, subprocess
import codecs

baseencode = 'cp1251'

base_path = sys.path[0]

"""
print "syspath=%s" % sys.path[0]
print "sysargv=%s" % sys.argv[0]
print "__file__=%s" % os.path.realpath(__file__)

# add path to import list
#sys.path.append('/foo/bar/mock-0.3.1')

import inspect, os
print inspect.getfile(inspect.currentframe()) # script filename (usually with path)
print os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
"""

# Set console encoding
def prepare_console():
    reload(sys)
    sys.setdefaultencoding('utf-8')

######### CLASSES TO PROCESS VALUES ###########

def makeint( value, default = 0 ):
    try: return int(value)
    except: return default

def splitl( value, sep_list = [ '|', '+' ] ):
    if value is None:
        return []
    ar = list(value)
    for sep in sep_list:
        ar = reduce( lambda x,y: x + y.split(sep), ar, [] )
    ar = map( lambda x: x.strip(), ar )
    firstempty = len(ar) and (ar[0]=='')
    ar = filter( len, ar )
    if firstempty and len(ar):
        return [''] + ar
    return ar

def adddict( value ):
    global cfg
    ptype, pname, value = value
    return _mycfg.parse_pattern( value, cfg.pattern_template['DETECT'] )

def vstrip( value ):
    try: return value.strip()
    except: return ''


######### STR ENCODING PROCESSING ###########

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
    return str_encode( str_decode( s, src ), tgt )


####     ######
def grep_compile( pattern ):
    pattern = pattern.replace('.','\\.').replace('?','.?').replace('*','.*?').replace('^','\\^').replace('$','\\$') + '$'
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


#### CLASS FOR PSEUDO MULTITHREAD RUNNING SEVERAL JOBS ######
class PsuedoMultiThread(object):
    #h_add = None
    #h_process = None
    max_threads = 1
    shell = False
    verbose = 1         # 0 -no message, 1-important only, 2,3...-debug also

    #def __init__( self,  add_handler_, process_handler_, max_t ):
    def __init__( self,  processorObj, max_t, verbose = None, shell = None ):
        self.task_queue = []
        self.processorObj = processorObj
        if verbose is not None:
            self.verbose = verbose
        if shell is not None:
            self.shell = shell
        ##self.h_add = add_handler_
        ##self.h_process = process_handler_
        self.max_threads = max_t

    def __del__( self ):
        print "PsuedoMultiThread.__del__"
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
            #print "%s\n%s", (str(cmd),str(fp))
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
        #print "STDOUT:\n%s\nSTDERR:%s\n" %(stdout,stderr)
        if stderr not in [ None, '']:
            print "failed task %s\nERROR:%s" % ( str_encode(value,'cp866'), str_encode(stderr,'cp866') )
        else:
            self.processorObj.handle( value, stdout )

##### CLASS CACHE #############
class FileInfoCache(object):
    def __init__( self, name ):
        self.fname = os.path.join( base_path, name )
        self.cache = {}
        self.dirty = False
        try:
            with codecs.open( self.fname, 'r', encoding='utf8' ) as f:
                lines = f.readlines()
            tsnow = int(time.time())
            EXPIRE_AFTER = 3600*24*7
            for l in lines:
                a = l.rstrip('\n').split('|',3)
                if len(a)<4:
                    continue
                cachedFname, modifiedTime, tstamp, value = a
                tstamp = abs(makeint(tstamp))
                if cachedFname in self.cache:
                    if tstamp < self.cache[cachedFname][1]:
                        continue
                if (tsnow-tstamp) > EXPIRE_AFTER:
                    tstamp = - tstamp
                    self.dirty = True
                self.cache[cachedFname] = ( modifiedTime, tstamp, value )
        except  IOError as err:
            pass

    def __del__( self ):
        print "FileInfoCache.__del__"
        self.saveFile()

    def saveFile( self ):
        print "saveFile()"
        if self.dirty:
            return
        with codecs.open( self.fname, 'w', encoding='utf8' ) as f:
            for k, v in self.cache.iteritems():
                if v[1]>=0:
                    f.write( "%s|%s|%s|%s\n" % (k,v[0],v[1],v[2]) )
        self.dirty = False

    def getMTimeTag( self, fname ):
        if os.path.isfile( fname ):
            return "%d+%s" % (os.path.getsize(fname), os.path.getmtime(fname))
        else:
            return ''

    def delete( self, fname ):
        if fname in self.cache:
            del self.cache[fname]
            self.dirty = True

    def update( self, fname, value, quick = True ):
        self.cache[fname] = ( self.getMTimeTag(fname), int(time.time()), value )
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

##### CLASS CACHE #############
class CachedProcessor(object):
    aggresiveCache = False   # False - rescan empty records, True - ignore empty cache records
    verbose = 3             # 0 - silent, 1-only errors, 2-valuable info, 3-debug

    def __init__( self, cmd, cacheObj, verbose = None, shell = False ):
        self.cacheObj = cacheObj
        self.cmd = list(cmd)
        if verbose is not None:
            self.verbose = verbose
        self.processed = []
        self.shell = shell

    # to replace
    def validate( self, value ):
        return True

    def add( self, fname ):
        self.processed.append( fname )
        if fname in self.cacheObj.cache:
            mtime = self.cacheObj.getMTimeTag( fname )
            if mtime == self.cacheObj.cache[fname][0]:
                value = self.cacheObj.cache[fname][2]
                if ( ( value=='' and self.aggresiveCache ) or self.validate(value) ):
                    if self.verbose > 2:
                        print "%s: get from cache" % str_transcode(fname,None,'cp866')
                    return None
            self.cacheObj.delete(fname)

        if self.verbose > 1:
            print "scan info for: %s" % str_transcode(fname,None,'cp866')
        fname = str_encode(fname,'cp1251')      # CPYTHON do not understand unicode; PYPY works ok with unicode so this not need for it
        if self.shell:
            fname = '"%s"' % fname
        return self.cmd + [ fname ]

    def handle( self, fname, value ):
        value = value.rstrip('\n\r')
        #print "%s\n%s\n" % (fname,value)
        if self.validate( value ):
            self.cacheObj.update( fname, value )
        elif self.verbose:
            if self.aggresiveCache:
                self.cacheObj.update( fname, '' )
            print "INVALID OUTPUT(PROBABLY NOT GOOD MEDIA): %s" % str_transcode(fname,None,'cp866')


##################
def scan_dir( dirpath, recursive = True, pattern = None, caseInsensetive = True):
    print "scan_dir(%s)"% str_transcode(dirpath,None,'cp866')
    if not os.path.isdir(dirpath):
        return []

    if pattern is not None:
        if not isinstance(pattern,list):
            if caseInsensetive:
                pattern = pattern.lower()
            a = filter( len, map(lambda s: s.strip(), pattern.split('|')) )
            if '*' in a:
                pattern = None
            else:
                pattern = map( lambda s: grep_compile(s), a)

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
                f1 = f.lower() if caseInsensetive else f
                for p in pattern:
                    if p.match(f1):
                        to_process.append(f)
                        break
    return to_process




"""
def split_stripped( s, sep, size ):
        a = s.split( sep, size-1 )
        while len(a)<size:
        a.append('')
        return map( lambda x: x.strip(), a )

def split_stripped( s, sep ):
        return map( lambda x: x.strip(), s.split(sep) )

"""

