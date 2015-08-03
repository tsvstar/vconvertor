# PREPARE SONY MTS TO CORRECT CONVERSION (SYNCED AUDIO/VIDEO) USING AVIDEMUX
#	copy video + convert audio -> NAME.ts

# For my computer "use QT4 version" checkbox should be on

import sys,os, sqlite3
import my.util

def sql_log( sql, debug = False ):
    pass

class CursorWLog(object):
    def __init__(self, conn, *kw,**kww):
        self.curs_ = conn.cursor(*kw,**kww)
        sql_log("init()", debug=True)

    def execute( self, sql, *kw, **kww):
        sql_log( "execute(%s)" % sql, debug=True )
        rv = self.curs_.execute(sql,*kw,**kww)
        #globals()['cur_map'] = dict( [col,idx] for idx, col in enumerate(cur.description) )
        return rv

    def execute_fetched( self, sql, *kw, **kww):
        sql_log( "execute_fetched(%s)" % sql, debug=True )
        cur = self.curs_.execute(sql,*kw,**kww)
        rv = cur.fetchall()
        #globals()['cur_map'] = dict( [col,idx] for idx, col in enumerate(cur.description) )
        return rv

    def executemany( self, sql, *kw, **kww):
        try:
         sql_log( "executemany(%s) %s" % (sql,kw), debug=True )
         return self.curs_.execute(sql,*kw,**kww)
        except Exception as e:
          print '!!!',str(e)

    def __getattr__(self, name):
        rv = getattr(self.curs_,name)
        sql_log( "getattr(%s)=%s"%(name,rv), debug=True )
        return rv

    def __call__(self,*kw,**kww):
        sql_log( "call %s, %s"%(kw,kww), debug=True )
        return self.curs_.__call__(*kw,**kww)

home = os.path.expanduser("~/AppData/Roaming/avidemux")
DB_FILE = os.path.join(home,"jobs.sql")

conn = sqlite3.connect(DB_FILE)
conn.execute("PRAGMA temp_store = MEMORY")
#cur = conn.cursor()
cur = CursorWLog( conn )

query = "SELECT MAX(id) FROM jobs"
lastid = cur.execute_fetched( query )[0][0]
if lastid is None:
    lastid = 0

def AddJob( path ):
    global lastid, cur
    #'status': 1, 'outputFile': u'H:/F2015/20150719Performance/video/1/2/85.mkv', 'jscript': u'85.py', 'jobname': u'85', 'startTime': 0, 'endTime': 0, 'id': 1}
    path = path.replace('\\','/')

    py_job = u"""#PY  <- Needed to identify #
#--automatically built--

adm = Avidemux()
adm.loadVideo("%s")
#adm.clearSegments()
#adm.addSegment(0, 0, 7200000000)	# time in microseconds. 
#adm.markerA = 0
#adm.markerB = 7200000000
adm.videoCodec("Copy")
adm.audioClearTracks()
adm.audioAddTrack(0)
adm.audioCodec(0, "LavAAC", "bitrate=224");
adm.audioSetDrc(0, 0)
adm.audioSetShift(0, 0,0)
adm.setContainer("ffTS", "acceptNonCompliant=False", "vbr=True", "muxRateInMBits=10")
""" % path

    lastid += 1
    with open( "%s/jobs/%04d.py"%(home,lastid), 'wb' ) as f:
        f.write( py_job.encode('utf-8'))
    query = u"INSERT INTO jobs (id,jscript,jobname,outputFile,status,startTime,endTime) VALUES( %(id)d, '%(id)04d.py', '%(id)04d','%(path)s.ts', 1,0,0 )" % { 'id': lastid, 'path':path}
    cur.execute( query )

    print "Added %04d: %s" % ( lastid, path.encode('cp866','ignore'))

#res = my.util.scan_dir("H:/F2015/20150711ZoukotekaAdilio/src/",recursive=True, pattern="*.*")
dirname = sys.argv[1]
if not os.path.exists( dirname ) and dirname.endswith('"'):
    dirname = dirname[:-1]
res = my.util.scan_dir( dirname, recursive=False, pattern="*.mts")
for path in res:
    AddJob( path )
conn.commit()

"""
query = "SELECT * FROM jobs"
for r in cur.execute_fetched( query ):
    r = dict( [col[0],r[idx]] for idx, col in enumerate(cur.description) )
    print r
"""