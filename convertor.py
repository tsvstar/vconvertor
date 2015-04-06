# usage: convertor.bat [--debug] [--strict] [--key1=value1] [--key2==value2] [...] DIRECTORY_OR_FILE_TO_PROCESS1 [DIRECTORY_OR_FILE_TO_PROCESS2 [..]]

#TODO: cached config(?)

import os,sys
import _mycfg
import my.util
from my.util import makeint, splitl, adddict, vstrip

import gc

"""
import subprocess
cmd = ['C:\\MY\\VK_PYPY\\convertor\\Media_07.72\\MediaInfo.exe', '--Output=General;%Format%\nVideo;|VIDEO|%Width%x%Height%@%FrameRate%', "E:\\_F_2015\\nostalgi\\20060810-8287.AVI"]
cmd = ['C:\\MY\\Portable Python 2.7.5.1\\convertor\\Media_07.72\\MediaInfo.exe', '--Output=General;%Format%\nVideo;|VIDEO|%Width%x%Height%@%FrameRate%|%BitRate/String%|%DisplayAspectRatio%|%Format%|%Format_Profile%|%ScanType%|%ScanOrder%\nAudio;|AUDIO|%Channel(s)%|%Codec%|%Codec/String%|%BitRate/String%|%Alignment%|%Delay%', u'E:\\\u0412\u0438\u0434\u0435\u043e\\2 \u0441\u043f\u043e\u0441\u043e\u0431\u0430 \u043d\u0430\u043b\u0430\u0434\u0438\u0442\u044c \u043e\u0442\u043d\u043e\u0448\u0435\u043d\u0438\u044f.mp4']

cmd[-1] = my.util.str_encode(cmd[-1],'cp1251')
#cmd = ' '.join(cmd)
print type(cmd)
print cmd
#subprocess.check_output(cmd,stderr=subprocess.STDOUT)
fp = subprocess.Popen( cmd, stdout=subprocess.PIPE, shell = not isinstance(cmd,list) )
#print subprocess.call(cmd, stderr=subprocess.STDOUT, shell=True)
stdout,stderr = fp.communicate()
print "STDOUT"
print stdout
print "STDERR"
print stderr

exit()
"""


################################

isDebug = 0
isStrict = 0

keys = {}
to_process = []
for v in sys.argv[1:]:
    v1 = v.lstrip()
    if v1.startswith("--"):
        v1 = v1[2:]
        if v1.lower()=='debug':
            isDebug += 1
        elif v1.lower()=='strict':
            isStrict += 1
        else:
            v1, v2 = _mycfg.split_pair( v1, '=' )
            keys[v1] = v2
    else:
        if v.endswith('"'):
            v = v[:-1]
        to_process.append(v)

if len(to_process)==0:
    print "No source given"
    exit()

if isDebug:
    print "isStrict=%s" % (True if isStrict else False)
    print "Extra options: %s" % str(keys)
    print "To process: %s" % str(to_process)


my.util.prepare_console()

cfg = _mycfg.ConfigLoader( isDebug = isDebug )

cfg.opt = { 'ENFORCE_BITRATE':  makeint,	# If defined and valid, that means "I surely know which video bitrate I'd like to have"
	    'ENFORCE_TEMPLATE': splitl,		# If defined, that means "I know which exactly templates should be used"

	    'BITRATE':       makeint,		# Default value of bitrate (used if no correct defined in any matched template)
	    'RECURSIVE':     makeint,		# is recursive scan for source files
	    'AVS_OVERWRITE': makeint,     	# Should .AVS be overwrited
	    'INDEX_ONLY':    makeint,		# Should only AVS+index job be created
	    'EXTRA_AVS':     splitl,    	# if not empty, then add to .AVS file correspondend [EXTRA_AVS=xxx] section. Could be several: extra1+extra2+...
	    'SUFFIX':	     vstrip,		# suffix for template (if defined will try to use 'name.suffix' template first; '.old' )

	    'FILES_ONLY':    splitl,  		# which files should be processed
	    'MATCH_ONLY':    splitl,		# if only they are match to any of given template
	    'TASK':          vstrip,

	    'ENCODE':        adddict,       # replacing of encoding sequences
	    'DETECT':        adddict,		# replacing of detect patterns
	   }

# sections[sectype] = [ datatype, isname_required, proccessor]
cfg.sections = { "":         [ 'dict', False, _mycfg.ConfigLoader.load_opt_processor],        # if no section defined, then expect OPT=VALUE pair
                 "TASK":  	 [ 'dict', True,  _mycfg.ConfigLoader.load_opt_processor],        # [TASK] contain OPT=VALUE pairs
                 "EXTRA_AVS":[ 'str',  True,  _mycfg.ConfigLoader.load_text_processor],       # [EXTRA_AVS] contain plain text
                 "DETECT":	 [ 'dict', False, _mycfg.ConfigLoader.load_pattern_processor],    # [DETECT] contain NAME => VALUE pattern pair
                 "ENCODE":	 [ 'dict', False, _mycfg.ConfigLoader.load_pattern_processor],    # [ENCODE] contain NAME => VALUE pattern pair
		}


# Config loader should say if non-empty but malformed string
defaultOpt = ( "FILES_ONLY=*.mp4|*.mts'\n" )
cfg.load_config( fname='INTERNAL', content=defaultOpt.split('\n'), strictError = isStrict )
cfg.load_config( fname= os.path.join(my.util.base_path, '!convert.cfg' ), strictError = isStrict )
cfg.load_config( fname= os.path.join(my.util.base_path, '!templates.cfg' ), strictError = isStrict )

if isDebug:
    print
    for k1,v1 in cfg.config.items():
        for k2,v2 in v1.items():
            if isinstance( v2, dict ):
                for k3,v3 in v2.items():
                    print "[%s][%s]{%s} = %s" % (k1,k2, k3, str(v3) )
                else:
                    print "[%s][%s] = %s" % (k1,k2, str(v2) )

# PROCESS OPTS (including first iteration of applying tasks)
mainopts = {}
for k,v in cfg.opt.iteritems():
    mainopts[k] = ''
cfg.replace_opt( mainopts, cfg.config[''][None] )   # replace from base section of options from config
mainopts['TASK'] = keys.get('TASK', mainopts['TASK'])   #replace TASK from given in ARGV options
tasks = filter( len, my.util.splitl( mainopts['TASK'] ) ) # split list of tasks
for t in tasks:
    if isDebug:
        print "Apply TASK '%s'" % t
    if t not in cfg.config['TASK']:
        print "Unknown task '%s'" % my.util.str_encode(t,'cp866')
        if isStrict:
            exit(1)
        continue
    cfg.replace_opt( mainopts, cfg.config['TASK'][t] ) # replace from task
cfg.replace_opt( mainopts, keys ) # replace from given in ARGV options (they have most priority)

# PREPARE PATTERNS
cfg.pattern_template['DETECT'] = _mycfg.PatternTemplate( '{CONTAINTER}|VIDEO|{WIDTH}x{HEIGHT}@{FPS}|{VIDEO_BRATE}|{RATIO}|{VCODEC}|{VPROFILE}|{VSCAN_TYPE}|{VSCAN_ORDER}'+
							'|AUDIO|{A_CHANNEL}|{A_CODEC}|{A_CODEC2}|{A_BRATE}|{A_ALIGNMENT}|{A_DELAY_MS}')
cfg.pattern_template['ENCODE'] = _mycfg.PatternTemplate( '{BITRATE}|{AVS_TEMPLATE}|{INDEX_JOB}|{VIDEO_PASS}|{AUDIO_ENCODE}|{MUX_JOB}' )
p_detect = cfg.pattern_template['DETECT'].parse_pattern( cfg.config['DETECT'][None] )
p_encode = cfg.pattern_template['ENCODE'].parse_pattern( cfg.config['ENCODE'][None] )

if isDebug:
    print
    for pname,pval in p_encode.items():
        pval1 = pval.copy()
        del pval1['_']
        print "%s = %s\n%s" % ( pname, pval['_'], str(pval1) )


# CHECK TEMPLATES EXISTENCE
template_path = os.path.join( my.util.base_path, 'templates')
if isStrict:
    for pname,pval in p_encode.items():
        cfg.load_template( template_path, pval.get("{AVS_TEMPLATE}",None) )
        cfg.load_template( template_path, pval.get("{INDEX_JOB}",None) )
        v = cfg.load_template( template_path, pval.get("{VIDEO_PASS}.1pass",None), fatal=False )
        if v is None:
            cfg.load_template( template_path, pval.get("{VIDEO_PASS}",None) )
        else:
            cfg.load_template( template_path, pval.get("{VIDEO_PASS}.2pass",None), fatal=False )
        cfg.load_template( template_path, pval.get("{AUDIO_ENCODE}",None) )
        cfg.load_template( template_path, pval.get("{MUX_JOB}",None) )


"""
for fname in to_process:
    fname = my.util.str_decode(fname)
    result = my.util.scan_files( fname, recursive = True, pattern = "*.jpg" )
    for f in result:
        print my.util.str_encode(f,'cp866')
exit()
"""

class MyCachedProcessor( my.util.CachedProcessor ):
    def __init__( self, cmd, cacheObj, verbose = False, shell = False ):
        super(MyCachedProcessor,self).__init__( cmd, cacheObj, verbose, shell )

    def validate( self, value ):
        global cfg, _mycfg
        try:
            #print value
            (cfg.pattern_template['DETECT']).parse_pattern( {'_': value}, strictError = True, silent = True )
            return True
        except _mycfg.StrictError:
            return False

#gc.set_debug(gc.DEBUG_STATS)

def PHASE1():
    print "PHASE 1: Collect info"
    cache = my.util.FileInfoCache( '.cache' )
    mediaInfoExe = os.path.join(my.util.base_path,'Media_07.72','MediaInfo.exe')
    #mediaInfoTemplate = os.path.join(my.util.base_path,'Media_07.72','template3.txt')
    #output = '--Output="file://%s"'%mediaInfoTemplate
    output = ( "--Output="+
        """General;%Format%
Video;|VIDEO|%Width%x%Height%@%FrameRate%|%BitRate/String%|%DisplayAspectRatio%|%Format%|%Format_Profile%|%ScanType%|%ScanOrder%
Audio;|AUDIO|%Channel(s)%|%Codec%|%Codec/String%|%BitRate/String%|%Alignment%|%Delay%""" )

    processor = MyCachedProcessor( [ mediaInfoExe, output], cache, shell = False, verbose = ( 3 if isDebug else 2 ) )
    worker = my.util.PsuedoMultiThread( processor, 2, shell = processor.shell )
    for fname in to_process:
        if os.path.isdir(fname):
            result = my.util.scan_dir( fname, recursive = True, pattern = "*.mp4|*.mts" )
            for fname in result:
                worker.add_task(fname)
        elif os.path.isfile(fname):
            worker.add_task(fname)
        else:
            print "Unknown source: %s" % fname
            if isStrict:
                exit()
    #worker.finalize_tasks()
    #gc.collect()

PHASE1()
#print gc.get_objects()
#print gc.garbage

print "\nPHASE 2: Generate tasks"
print "!!TODO!!"

