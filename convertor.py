# usage: convertor.bat [--debug] [--strict] [--key1=value1] [--key2==value2] [...] DIRECTORY_OR_FILE_TO_PROCESS1 [DIRECTORY_OR_FILE_TO_PROCESS2 [..]]

import os, sys, copy, re, codecs
import xml.etree.ElementTree as ETree

import my.config as _mycfg
import my.megui, my.util
from my.megui import _get_elem, ET
from my.util import makeint, makebool, splitl, adddict, vstrip, DBG_info, DBG_trace, DBG_trace2, say

################################

my.util.baseencode = 'cp1251'           # your filesystem encoding (for russian windows works with cp1251)
my.util.console_encoding = 'cp866'      # your console encoding (for russian console display as cp866)

try: my.util.logfile = codecs.open("convertor.log","a",'utf-8')
except: pass

ADJ_KEYS_SETTER_LOCAL = False           # if False - setter in adjustments ( {@key@=newvalue,..} ) change key value TO THIS AND ALL LATER jobs of this file
                                        # if True  - setter in adjustments ( {@key@=newvalue,..} ) change key value ONLY TO THIS job

isDebug, isStrict = 0, 0                # default values

################################

def main():
    global p_encode                         # INPUT VALUES
    global postponed_queue                  # OUTPUT VALUES

    argvkeys, to_process = initARGV()
    if argvkeys['help']>0:
        print "Usage:"
        print "  convertor.py [--debug] [--strict] [--key1=value1] [--key2==value2] [...] DIR_OR_FILE_TO_PROCESS1 [DIR_OR_FILE_TO_PROCESS2 [..]]"
        print "\nExample:"
        print "  convertor.py --strict --TASK=felix+debarrel --INDEX-ONLY=-1 --SUFFIX=new C:\\MY\\VIDEO\\ C:\\MY\\vidfile.mp4"

        initCONFIGS()
        LoadBaseCONFIGFiles()
        print "\nAvailable TASK:      %s" % ', '.join( sorted( cfg.config.get('TASK',{}).keys() ) )
        print "Available EXTRA_AVS: %s" % ', '.join( sorted( cfg.config.get('EXTRA_AVS',{}).keys() ) )
        exit()

    argvkeys = postprocessARGV( argvkeys )
    if isDebug:
        print "isStrict=%s" % (True if isStrict else False)
        print "Extra options: %s" % str(argvkeys)
        print "To process: %s" % str(to_process)

    initCONFIGS()
    parseCONFIGS( argvkeys )

    joblist = preprocessMEGUI()

    if len(to_process)==0:
        print "No source given - exit"
        exit()
    for pname in ['TOP','BASIC']:
        if pname not in p_encode:
            raise _mycfg.StrictError("No %s encoding pattern defined" % pname)

    """ PHASE1: Collect Info """
    process_queue = PHASE1( to_process )

    """  PHASE2: Add task """
    print
    postponed_queue = []
    PHASE2( process_queue, joblist )
    joblist.addPostponed( postponed_queue )
    joblist.save()
    ##for k,v in p_encode.iteritems(): print k,'=',v

"""========================= """
def initARGV():
    """ LOAD ARGV """
    my.util.prepare_console()
    argv = _mycfg.prepareARGV( sys.argv )[1:]
    if '/?' in argv:
        return {'help':1}, []
    argvkeys, to_process = _mycfg.ParseArgv( argv, optdict={ 'debug':0, 'strict':0, 'help':0} )
    return argvkeys, to_process

"""========================= """
def postprocessARGV( argvkeys ):
    global isDebug, isStrict                        # OUTPUT VALUES

    for n in argvkeys.keys():
        if len(n)>2 and n[0]=='@' and n[-1]=='@':
            argvkeys.setdefault('@',{})[n] = argvkeys[n]
            del argvkeys[n]

    isDebug, isStrict = argvkeys['debug'], argvkeys['strict']
    my.util.DEBUG_LEVEL = isDebug

    return argvkeys

"""=== CONFIG PROCESSING ===="""
def initCONFIGS():
    global isDebug
    global cfg                          # OUTPUT VALUES

    """ DESCRIBE CONFIG """
    cfg = _mycfg.ConfigLoader( isDebug = isDebug )
    cfg.opt = { 'ENFORCE_BITRATE':  makeint, # If defined and valid, that means "I surely know which video bitrate I'd like to have"
    	    'ENFORCE_PATTERN': splitl,		 # If defined, that means "I know which exactly templates should be used"

    	    'BITRATE':       makeint,		# Default value of bitrate (used if no correct defined in any matched template)
    	    'RECURSIVE':     makebool,		# is recursive scan for source files
    	    'STRICT':        makebool,		# are error (such as bad config, collision, etc) fatal
    	    'AVS_OVERWRITE': makebool,     	# Should .AVS be overwrited
    	    'INDEX_ONLY':    makeint,		# Should only AVS+index job be created[ 0=regular convert, 1=only index job, -1=first all index than all convert]
    	    'KEEP_TMP':      makebool,     	# Should do not remove intermediary files
    	    '@':             lambda s: s,  	# @{KEY} = value -- set the KEY to use it later in jobs as @KEY@
    	    'EXTRA_AVS':     splitl,    	# if not empty, then add to .AVS file correspondend [EXTRA_AVS=xxx] section. Could be several: extra1+extra2+...
    	    'SUFFIX':	     vstrip,		# suffix for template (if defined will try to use 'name.suffix' template first; '.old' )

    	    'FILES_ONLY':    splitl,  		# which files should be processed
    	    'MATCH_ONLY':    splitl,		# if only they are match to any of given template
    	    'TASK':          splitl,

    	    'ENCODE':        adddict,       # replacing of encoding sequences  #@tsv TO IMPLEMENT!!
    	    'DETECT':        adddict,		# replacing of detect patterns
            'TEMPLATE':      lambda s: s,   # TODO: templates
            'RESOLVE':       splitl,        # TODO!! RESOLVE{sony:720|_dga} = _dga|dgasony  # if video match to several patterns and they have collision how to process - we can resolve this by saying which encoding pattern should be used instead

    	    'MEGUI':         vstrip,		# path to MEGUI
    	   }

    # sections[sectype] = [ datatype, isname_required, proccessor]
    cfg.sections = { "":         [ 'dict', False, _mycfg.ConfigLoader.load_opt_processor],        # if no section defined, then expect OPT=VALUE pair
                     "TASK":  	 [ 'dict', True,  _mycfg.ConfigLoader.load_opt_processor],        # [TASK] contain OPT=VALUE pairs
                     "EXTRA_AVS":[ 'str',  True,  _mycfg.ConfigLoader.load_text_processor],       # [EXTRA_AVS] contain plain text
                     "TEMPLATE": [ 'dict', False, _mycfg.ConfigLoader.load_opttmpl_processor],    # [TEMPLATE] contain OPT=VALUE pairs
                     "DETECT":	 [ 'dict', False, _mycfg.ConfigLoader.load_pattern_processor],    # [DETECT] contain NAME => VALUE pattern pair
                     "ENCODE":	 [ 'dict', False, _mycfg.ConfigLoader.load_pattern_processor],    # [ENCODE] contain NAME => VALUE pattern pair
    		}

    cfg.tpath = './templates'


def LoadBaseCONFIGFiles():
    global cfg, isStrict
    cfg.load_config( fname= os.path.join(my.util.base_path, '!convert.cfg' ), strictError = isStrict )
    cfg.load_config( fname= os.path.join(my.util.base_path, '!templates.cfg' ), strictError = isStrict )

def parseCONFIGS( argvkeys ):
    global isDebug, isStrict
    global cfg, mainopts, p_encode, p_detect        # OUTPUT VALUES

    """ LOAD CONFIG """

    say( "\nLoad configs" )

    # a) load default values
    defaultOpt = (
      """FILES_ONLY=*.mp4|*.mts
         RECURSIVE=1
         KEEP_TMP=0
         AVS_OVERWRITE=0
         INDEX_ONLY=0""" )
    cfg.load_config( fname='INTERNAL', content=defaultOpt.split('\n'), strictError = True )
    internal = cfg.config['']	#.copy()
    del cfg.config['']

    # b) create default sections
    for sname, value in cfg.sections.items():
        section = cfg.config.setdefault(sname,{})
        if not value[1]:
            section[None] = dict() if value[0]=='dict' else list()

    # c) load regular config files
    LoadBaseCONFIGFiles()

    # d) Load pythonized "config"
    cfg.config[''][None].setdefault('@',{})
    try:
        if os.path.isfile("!custom_func.py.cfg"):
            import imp
            sys.dont_write_bytecode = True
            custom_func_cfg = imp.load_source("custom_func_cfg", "!custom_func.py.cfg")
            for name in dir(custom_func_cfg):
                val = getattr(custom_func_cfg,name)
                if name.startswith('FN_') and name==name.upper() and callable(val):
                    cfg.config[''][None]['@']["@%s@"%name.upper()] = val
    except Exception as e:
        err = "Fail to parse !custom_func.py.cfg: %s, %s" % (type(e),str(e))
        if isStrict or cfg.config[''][None].get('STRICT',0):
            raise _mycfg.StrictError(err)
        say( err )

    # d) get undefined values from internal default values
    cfg.config[''][None] = cfg.replace_opt( internal[None], cfg.config[''][None] )

    # e) debug output
    if isDebug:
        out = '\n'
        for k1,v1 in cfg.config.items():
            for k2,v2 in v1.items():
                if isinstance( v2, dict ):
                    for k3,v3 in v2.items():
                        out+= "[%s][%s]{%s} = %s\n" % (k1,k2, k3, str(v3) )
                    else:
                        out+= "[%s][%s] = %s\n" % (k1,k2, str(v2) )
        DBG_trace(out)


    """ PROCESS OPTS (including first iteration of applying tasks) """

    mainopts = dict.fromkeys( cfg.opt, '' )                 # initialize dict with '' for all options
    cfg.replace_opt( mainopts, cfg.config[''][None] )       # replace from base section config
    if not isinstance(mainopts.get('TEMPLATE',None), dict): # update opts.TEMPLATE from [TEMPLATE] section
        mainopts['TEMPLATE'] = {}
    mainopts['TEMPLATE'].update( cfg.config['TEMPLATE'][None] )
    DBG_trace("opts before tasks: %s",repr(mainopts))       ##@tsv
    mainopts['TASK'] = argvkeys.get('TASK', mainopts['TASK'])   # replace TASK from ARGV if given
    tasks = filter( len, cfg.get_opt(mainopts, 'TASK') )    # filter splited(on parse) list of tasks
    for t in tasks:
        #if isDebug:
        say( "Apply TASK '%s'", t )
        if t in cfg.config['TASK']:
            cfg.replace_opt( mainopts, cfg.config['TASK'][t] ) # replace from task
        elif t in cfg.config['EXTRA_AVS']:
            mainopts['EXTRA_AVS'] += ('+' if mainopts['EXTRA_AVS'] else '' ) + t
        else:
            say( "Unknown task '%s'", t )
            if isStrict or  cfg.get_opt( mainopts, 'STRICT' ):
                exit(1)
    cfg.replace_opt( mainopts, argvkeys ) # replace from given in ARGV options (they have most priority)

    isStrict = isStrict or cfg.get_opt( mainopts, 'STRICT' )
    mainopts['MATCH_ONLY'] = set( filter( len, cfg.get_opt( mainopts, 'MATCH_ONLY' ) ) )
    DBG_trace("Result opts: %s",repr(mainopts))       ##@tsv


    """ PREPARE PATTERNS """

    def apply_pattern( pname, opt, target ):
        if isinstance(opt, dict) and opt:
            say( "Update %s patterns from options: %s" % (pname, ', '.join(opt.keys())) )
            for k,v in opt.iteritems():
                if v.strip():
                    target[k] = v
                elif k in target:
                    del target[k]
            return target

    cfg.pattern_template['DETECT'] = _mycfg.PatternTemplate( 'DETECT',
    						'{CONTAINER}|VIDEO|{WIDTH}x{HEIGHT}@{FPS}|{V_BRATE} {V_BRATE_TYPE}|{RATIO}={AR_X}:{AR_Y}|{VCODEC}|{VPROFILE}|{VSCAN_TYPE}|{VSCAN_ORDER}'+
    						'|AUDIO|{A_CHANNEL}|{A_CODEC}|{A_CODEC2}|{A_BRATE}|{A_ALIGNMENT}|{A_DELAY_MS}')
    cfg.pattern_template['ENCODE'] = _mycfg.PatternTemplate( 'ENCODE', '{BITRATE}|{AVS_TEMPLATE}|{INDEX_JOB}|{VIDEO_PASS}|{AUDIO_ENCODE}|{MUX_JOB}' )
    apply_pattern( 'DETECT', mainopts.get('DETECT',None), cfg.config['DETECT'][None] )        # copy from opts
    apply_pattern( 'ENCODE', mainopts.get('ENCODE',None), cfg.config['ENCODE'][None] )
    ##for k in cfg.pattern_template:              # @tsv
    ##    cfg.pattern_template[k].isDebug=True
    p_detect = cfg.pattern_template['DETECT'].parse_pattern( cfg.config['DETECT'][None], strictError = True )
    p_encode = cfg.pattern_template['ENCODE'].parse_pattern( cfg.config['ENCODE'][None] )

    if isDebug:
        DBG_trace( "\nP_ENCODE\n   %s", _mycfg.PatternTemplate.PrintParsedList( p_encode ) )
        DBG_trace( "\nP_DETECT\n   %s", _mycfg.PatternTemplate.PrintParsedList( p_detect ) )

    """ CFG VALIDATION: CHECK TEMPLATES EXISTENCE """
    cfg.template_path = os.path.join( my.util.base_path, 'templates')
    if isStrict:
         PreloadEncodingTemplates( p_encode )

def preprocessMEGUI():
    global mainopts

    """ LOAD + REPAIR MEGUI JOBLIST """
    say( "Load joblist" )
    my.megui.megui_path = cfg.get_opt( mainopts, 'MEGUI' ).rstrip("\\/")+"\\"
    if not len(my.megui.megui_path):
        say( "No path to MEGUI defined" )
        exit(1)
    if not os.path.isdir(my.megui.megui_path):
        say( "Invalid path to MEGUI (%s)", my.megui.megui_path )
        exit(1)

    joblist = my.megui.JobList()
    ##my.megui.print_xml(joblist.tree._root)    #@tsv
    my.megui.load_jobdir(joblist)
    if joblist.dirty:
        say( "Store changes of jobs list" )
        joblist.save()

    return joblist


####################################################################

def PreloadEncodingTemplates( template_dict ):
    """-- try to load all templates in all patterns. exception on error--"""
    for pname,pval in template_dict.iteritems():
        for tokenname in [ "{AVS_TEMPLATE}", "{INDEX_JOB}", "{VIDEO_PASS}",
                            "{AUDIO_ENCODE}","{MUX_JOB}" ]:
            val = pval.get(tokenname,None)
            if val in [None, '']:
                continue
            idx = val.find('{')
            if idx>=0:
                if val.strip()[-1]!='}':
                    raise _mycfg.StrictError(u"No enclosing } at token %s of pattern %s" % (tokenname, pname) )
                val = val[:idx]
            try:
                cfg.load_multi_templates( val, fatal = True )
            except Exception as e:
                raise _mycfg.StrictError(u"Can't load template '%s' at token %s of pattern %s: %s" % (val,tokenname, pname,str(e)) )



"""-- derived class to process file (get media info) with defined validation--"""
class MyCachedProcessor( my.util.CachedProcessor ):
    ##def __init__( self, cmd, cacheObj, verbose = False, shell = False ):
    ##    super(MyCachedProcessor,self).__init__( cmd, cacheObj, verbose, shell )

    @staticmethod
    def validate( value, verbose = False ):
        try:
            return (cfg.pattern_template['DETECT']).parse_pattern( {'_': value}, strictError = True, silent = not verbose )
        except _mycfg.StrictError:
            return None

"""
    ********** PHASE 1: COLLECT INFO **************
    Pseudo multi-threaded with caching result
"""


def PHASE1( to_process ):
    DBG_info('')
    say( "PHASE 1: Collect info" )
    mediaInfoExe = os.path.join(my.util.base_path,'Media_07.72','MediaInfo.exe')
    #mediaInfoTemplate = os.path.join(my.util.base_path,'Media_07.72','template3.txt')
    #output = '--Output="file://%s"'%mediaInfoTemplate
    output = ( "--Output="+
        """General;%Format%
Video;|VIDEO|%Width%x%Height%@%FrameRate%|%BitRate/String%|%DisplayAspectRatio%=%DisplayAspectRatio/String%|%Format%|%Format_Profile%|%ScanType%|%ScanOrder%
Audio;|AUDIO|%Channel(s)%|%Codec%|%Codec/String%|%BitRate/String%|%Alignment%|%Delay%""" )


    cacheObj = my.util.FileInfoCache( '.cache' )
    processor = MyCachedProcessor( [ mediaInfoExe, output ],                # process command
                                    cacheObj,
                                    ##validator = validateValue,
                                    shell = False,
                                    verbose = ( 3 if isDebug else 2 ) )

    process_queue = []
    with my.util.PsuedoMultiThread( processor, max_t=1, shell=processor.shell ) as worker:
      for fname in to_process:
        if not os.path.exists(fname) and fname[-1]=='"': # " at the end could means just that this was finished with \\
            fname = fname[:-1]
        if os.path.isdir(fname):
            result = my.util.scan_dir( fname,
                            recursive = cfg.get_opt( mainopts, 'RECURSIVE' ),
                            pattern = cfg.get_opt( mainopts, 'FILES_ONLY' ) )
            for fname in result:
                worker.add_task(fname)
        elif os.path.isfile(fname):
            worker.add_task(fname)
        else:
            say( "Unknown source: %s" % fname )
            if isStrict:
                raise _mycfg.StrictError()

      for fname in processor.processed:
        process_queue.append( [ fname, cacheObj.get(fname,check=False) ] )
    return process_queue




"""
    ********** PHASE 2: FIND MATCHED TEMPLATES **************
"""

def PHASE2( process_queue, joblist ):
    DBG_info('')
    say( "PHASE 2: Generate tasks" )
    global p_detect

    # FOR EACH QUEUE ITEM:
    for fname, info in process_queue:
        DBG_info("\nPHASE 2_1: FIND MATCHES - %s", fname)
        if info in [None,'']:
            say ("No info for '%s' - skip it", fname)
            continue

        # 1) parse mediainfo
        parsed_info = MyCachedProcessor.validate( info, verbose = True )
        if parsed_info is None:
            say( "^^for file %s", fname )
            continue
        parsed_info = parsed_info['_']
        DBG_info( " parsed_info=%s", parsed_info['_'] )

        # 2) find matched 'detect' patterns
        detected = []
        is_forbid = False
        for pname, pdict in p_detect.iteritems():
            DBG_trace( "\nCHECK %s" % pname )
            for k,v in pdict.iteritems():
                sayfunc = DBG_trace if k=='_' else DBG_trace2
                sayfunc( " %s=%s" % ( k,repr(v) ) )

            for k,v in pdict.iteritems():
                if k in ['_']:
                    continue
                if v in [None,'']:
                    continue
                out = my.util.unicformat( "token=%s, expect=%s, real=%s", [k, v, parsed_info.get(k)] )
                if k not in parsed_info:
                    DBG_info(" %-10s: NOKEY -- %s", [pname, out] )
                    break
                if parsed_info[k] != v:
                    DBG_info(" %-10s: MISMATCH -- %s", [pname, out] )
                    break
                DBG_trace(" iter. %s", out)
            else:
                DBG_info(" %-10s: MATCHED",pname)
                is_forbid = is_forbid or ( pname if pname.startswith('__forbid') else False )
                detected.append( pname )
        DBG_trace('')

        #3) cutoff suffix from detect pattern (that the thing which allow to make a lot of correspondance to the same patter)
        detected = list( set( map( lambda s: s.split('.',1)[0], detected ) ) )

        say( u"%(fname)s\t=> %(w)s*%(h)s@%(fps)s = %(ar)s; %(profile)s ( %(detected)s )" % {
                        'fname': my.util.str_decode(fname),
                        #'fname': my.util.str_cp866(fname),
                        'w': parsed_info['{WIDTH}'],
                        'h': parsed_info['{HEIGHT}'],
                        'fps': parsed_info['{FPS}'],
                        'ar': parsed_info['{RATIO}'],
                        'profile': parsed_info['{VPROFILE}'],
                        'detected': ' + '.join(detected) if len(detected) else "BASIC",
                    }
            )

        # "found "__forbid*" pattern - means do not process such video ever
        if is_forbid:
            say( " >> skipped (match to '%s' pattern)", is_forbid )
            continue

        if mainopts['MATCH_ONLY'] and len( set(detected) & mainopts['MATCH_ONLY'] )==0:
            say( " >> skipped( patterns doesn't match to any of MATCH_ONLY: %s )", ', '.join(mainopts['MATCH_ONLY']) )
            continue

        # 4) apply ENFORCE_PATTERN if given
            # a) if "|pattern1|pattern2|.." - then append
            # b) if "pattern1|pattern2|.."  - then replace
        enforce_patterns = cfg.get_opt( mainopts, 'ENFORCE_PATTERN' )
        if enforce_patterns:
            if enforce_patterns[0]=='':
                enforce_patterns = detected + filter(len, enforce_patterns)
            if set(enforce_patterns)!= set(detected):
                say( " >> enforced encoding as %s", '+'.join(set(enforce_patterns)) )
            detected = enforce_patterns

        #
        to_encode = PHASE2_2( detected )
        if to_encode is None:
            continue

        encode = PHASE2_3( fname, to_encode, parsed_info, joblist )



"""
    ******* PHASE 2_2: Find template correspondance *******

    Scan each detected pattern and find exact existed subtemplate
    (with respect suffix and hierarchy)
    Warning/Exception if collision between patterns detected in any token.

    SCANING PATTERNS ALGORITHM:
        1) for ['sony:720','__dga'] with suffix 'old'
           [sony:720.old] -> sony:720 -> [sony.old] -> [sony]
           [__dga.old] -> __dga

        2) if still not then check default patterns
                   -> [BASIC.old] -> BASIC -> [TOP.old] -> TOP

    RETURN VALUE:
        to_encode = { TOKENNAME: {  'pname':    exact name of pattern which was used
                                    'pvalue':   value(template name or bitrate or special "copy")
                                    'adj':      value adjustment if exists
                                 }

    ??? HOW ADJ PROCESSED AND WHAT IS ITS FORMAT?
"""
def PHASE2_2( detected ):
    global p_encode

    DBG_info("\nPHASE 2_2: RESOLVE ENCODING TEMPLATES (%s)", repr(detected) )

    # initialize object which do scaning job
    #   (find for given token and given pattern most precise existed correspondance)
    encoder = _mycfg.Encoding( p_encode, cfg, mainopts.get('TEMPLATE',{}), cfg.get_opt( mainopts, 'SUFFIX' ) )

    to_encode = {}                      # to_encode[job_type] = {pname, pvalue, ?adj?, ?tmpl_list? }
    sysPatternList = [ 'BASIC', 'TOP' ]

    # OUTER CYCLE: PROCESS EACH TOKEN
    for p_token_name in cfg.pattern_template['ENCODE'].ar_tokens:
        if p_token_name in ['_']:       # skip 'printable value'
            continue
        DBG_trace( "process token %s", p_token_name )    #@tsv

        if p_token_name=='{BITRATE}':   # if enforced_bitrate defined, then do not get it from patterns
            enforced_brate = cfg.get_opt( mainopts, 'ENFORCE_BITRATE' )
            if  enforced_brate > 0:
                to_encode[p_token_name] = { 'pname': 'OPTION:ENFORCE_BITRATE',  'pvalue': enforced_brate }
                continue

        to_encode_cur = {}      # accumulate values for token here
        encoder.path = []       # reset list of processed patterns

        try:
            # INNER CYCLE: THRU MATCHED PATTERNS
            for pname in ( detected + sysPatternList ):

                # BASIC and TOP are default values. Do not check for values/collision if we already find template
                if ('pvalue' in to_encode_cur) and (pname in sysPatternList):
                    continue

                # Scan all variants of one pattern for requested token template
                pname_real, pvalue, adjustments, template_content = encoder.get_encode_pattern( pname, p_token_name,  (p_token_name=='{BITRATE}') )

                # adjustment - check collision + remember
                if (adjustments is not None):
                    if to_encode_cur.get('adj',adjustments) != adjustments :
                        raise _mycfg.StrictError( "collision between '%s' and '%s' encoding patterns for %s" % ( pname_real, to_encode_cur['pname'], p_token_name ) )
                    to_encode_cur['adj'] = adjustments

                # template - check collision + remember
                if pname_real is not None:
                    if to_encode_cur.get('pvalue',pvalue) != pvalue:
                        raise _mycfg.StrictError( "collision between '%s' and '%s' encoding patterns for %s" % ( pname_real, to_encode_cur['pname'], p_token_name ) )
                    to_encode_cur.update( { 'pname': pname_real, 'pvalue': pvalue, 'tmpl_list':template_content } )

            #If no value in any pattern found
            if to_encode_cur.get('pvalue',None) is None:
                # a) For BITRATE - try to get default value from options
                if p_token_name=='{BITRATE}':
                    encoder.path.append('OPTION:BITRATE')
                    default_brate = cfg.get_opt( mainopts, 'BITRATE' )
                    if default_brate <= 0:
                        raise _mycfg.StrictError( "No valid bitrate defined in any encoding patterns or options" )
                    to_encode_cur = { 'pname': 'OPTION:BITRATE',  'pvalue': default_brate }
                else:
                # b) For other cases - error. Should be defined exactly one
                    raise _mycfg.StrictError( "Undefined %s" % p_token_name )
        except _mycfg.StrictError as e:
            say( " >> skipped (%s)" % str(e) )
            if isStrict:
                raise
            return None
        finally:
            #sayfunc = say if (isDebug) else DBG_trace
            adj = to_encode_cur.get('adj',None)
            tmpl_name = to_encode_cur.get('pvalue',None)
            DBG_info( "%(token)s:\tValue=%(value)-15s Path: (%(path)s)" % {
                        'token': p_token_name,
                        'path': ' -> '.join(encoder.path),
                        'value': ( repr(tmpl_name) + _mycfg.Encoding.getAdjPrintable(adj) )
                        }
                    )
            tmpl = to_encode_cur.get('tmpl_list',_mycfg.EncTemplate())
            if len(tmpl.path)>1:
                DBG_info( "\t\t%s = %s%s" % ( tmpl_name, tmpl.path[-1], _mycfg.Encoding.getAdjPrintable(tmpl.adjustments) ) )
            if len(tmpl.path)>2:
                DBG_info( "\t\t(path: %s)" % '->'.join(tmpl.path) )

        to_encode[p_token_name] = to_encode_cur

    to_print = []
    for p_token_name in cfg.pattern_template['ENCODE'].ar_tokens:
        adj = _mycfg.Encoding.getAdjPrintable( to_encode[p_token_name].get('adj','') )
        to_print.append( str(to_encode[p_token_name].get('pvalue','')) + adj )

    say( "  => ENCODE AS: %s" % '|'.join(to_print) )

    return to_encode


"""
    ********** PHASE 2_3: GENERATE MEGUI TASK **************
"""

def PHASE2_3( fname, to_encode, info, joblist ):

    DBG_info("\nPHASE 2_3: GENERATE JOBS" )

    # Prepare keys (add opts, add detected values)
    def GetKeys(basekeys):
        keys = {}

        # add detect values
        for k,v in info.iteritems():
            keys["@%s@"%k] = v

        # add from mainopts
        kopts = cfg.get_opt( mainopts, '@' )
        if isinstance(kopts,dict):
            for k,v in kopts.iteritems():
                keys[k]=v

        # update/replace from basekeys
        keys.update(basekeys)

        # resolve all recursive dependencies
        for _ in range(0,len(keys)+3):
            detected, failed = {}, {}
            for k,v in keys.iteritems():
                if ( isinstance(v,basestring) and len(v)>2 and v[0]=='@' and v[-1]=='@' ):
                    detected[k]=v
                    if k!=v and v in keys:
                        keys[k] = keys[v]
                    else:
                        failed[k] = keys[k]
            if not detected:
                break
            if failed:
                say("Some keys are unresolved: %s", [failed] )
                break
        else:
            failed = map( filter( lambda tup: ( len(tup[1])>2 and tup[1][0]=='@' and tup[1][-1]=='@' ), keys.iteritems() ) )
            say("Looks like crossdependency in keys. Some keys are unresolved: %s", [failed] )
        return keys

    basekeys = { '@SRCPATH@': fname,                            # source file
             '@SRCPATH_WO_EXT@': os.path.splitext(fname)[0],   # source file without extension
             '@SRCPATH_VIDEO@': fname,                          # intermediary video file
             '@SRCPATH_AUDIO@': fname,                          # intermediary audio file
             '@MEGUI@': my.megui.megui_path,
             '@BITRATE@': to_encode.get("{BITRATE}",{}).get("pvalue",0),
             '@CRF@': to_encode.get("{BITRATE}",{}).get("pvalue",0)
    }
    keys = GetKeys(basekeys)
    keys['@{A_DELAY_MS}@'] = "%d" % int(my.util.makefloat(keys['@{A_DELAY_MS}@']))

    # DEBUG INFO
    if isDebug:
        DBG_trace( "fname=%s (%s)", [fname,type(fname)])
        DBG_trace( "to_encode==>",  )
        for k,v in to_encode.iteritems():
            DBG_trace( "  %s: %s", [repr(k), repr(v)])
        DBG_trace( "info=%s", repr(info) )
        DBG_trace( "mainopt=%s", repr(mainopts) )
        DBG_trace( 'keys=%s', repr(keys) )
        #for k,v in keys.iteritems():  print k,v

    # init copy of main opts (here will be accumulated options from adjustments
    optscopy = copy.deepcopy( mainopts )

    # Auxilary function. Find in childs a single record with "tag",
    #   raise exception if error and create it if needed
    def _xml_scan( xml, tag_path, err_msg='', createIfNotFound = False ):
        tag = tag_path[-1]
        elems = map( lambda e: e, xml.iter(tag) )
        ##DBG_info("@tsv _xml_scan(parent=%s,tags=%s,%s) elems=%s",[xml.tag, tag_path,createIfNotFound,elems])
        ##DBG_info("@tsv %s %s", [xml, my.util.debugDump(xml)])
        if len(elems)==0:
            if createIfNotFound:
                ##DBG_info("@tsv create")
                elems = [ ET.add_elem_notnil(xml,tag,'') ]
            else:
                raise _mycfg.StrictError( err_msg + "not found adjustment key <%s>"% ':'.join(tag_path) )
        elif len(elems)>1:
            raise _mycfg.StrictError( err_msg + "found several adjustment key <%s>"% ':'.join(tag_path) )
        return elems[0]


    # Workhorse function. Make parsing of job and applying of everything
    #   tokenname - name of token in to_encode dict
    #   baseAdjustment - dict with default values of an adjustments (so we able to have default modification for any job)
    #   xml       - if True, then loaded content will be translated to xmltree and adj applied
    #   allowEmpty - if False then check and raise error if no valid content given
    re_key = re.compile("@[A-Za-z0-9{}_]@")
    def getEncodeTokens( tokenname, baseAdjustment={}, xml = False, allowEmpty = False ):
        d = to_encode.get( tokenname, {})
        # 1. get values
        detect_pname = d.get('pname','')                    # name of pattern for detection
        encode_tname = d.get('pvalue','')                   # name of template for job
        tmpl = d.get('tmpl_list',_mycfg.EncTemplate())      # list of templates  (multipass)
        content = filter(len, tmpl.content )                # list of templates content (multipass)
        adj_v = my.util.MyOrderedDict( filter(len, d.get('adj',[]) ) )     # dict of adjustments
        DBG_trace( "getEncodeTokens(%s): detect=%s, encode=%s, template=%s", [tokenname,detect_pname,encode_tname, tmpl] )
        DBG_trace( "baseAdj=%s, tmplAdj=%s, adj=%s", [baseAdjustment, tmpl.adjustments, adj_v] )        # baseAdjustments - given by code for job type
                                                                                                        # tmplAdj         - comes from template alias ([TEMPLATE] section)
                                                                                                        # adj             - given in exact encoding job

        if not allowEmpty and len(content)==0:
            raise _mycfg.StrictError( "ERROR: Empty %s for %s %s" % ( tokenname, detect_pname, encode_tname) )

        # 2. adjustment = baseAdjustment + templateAliasAdjustments+ p_encode['adj'](override baseAdjustment)
        adj = my.util.MyOrderedDict(baseAdjustment)
        adj.update(tmpl.adjustments)
        adj.update(adj_v)
        DBG_trace("%s",adj)

        # 3. prepare adjustments by keys
        for k,v in adj.items():
            if v.find('@')>=0:
                for src, dst in keys.iteritems():       #@tsv
                    if callable(dst) and v.find(src)>=0:
                        dst = dst( keys, optscopy )
                    v = v.replace(src,str(dst))
                adj[k]=v

        # 4. process opts and keys from adjustments
        if ADJ_KEYS_SETTER_LOCAL:
            # CASE: {@key@=val} -- have local effect (only in this job)
            keys_local = keys.copy()
        else:
            # CASE: {@key@=val} -- have global effect (for whole pattern)
            keys_local = keys

        for k,v in adj.items():
            if len(k)>2 and k[0]=='%' and k[-1]=='%':
                optname = k[1:-1]
                if optname in cfg.opt:
                    cfg.replace_opt( optscopy, {optname:v} )
                del adj[k]
            elif len(k)>2 and k[0]=='@' and k[-1]=='@':
                kname = k[1:-1]
                kval = keys.get(k,None)
                if callable(kval):
                    kval(keys_local,optscopy,v)
                else:
                    keys_local[ kname ] = v
                del adj[k]
        ##DBG_info("@tsv adj = %s", str(adj))

        # 5. prepare content by keys
        for idx in range(0,len(content)):
            for src, dst in keys_local.iteritems():
                ##if src.startswith("@SRCPATH_"):
                ##    print src, dst
                if callable(dst) and content[idx].find(src)>=0:
                    ##my.util.PRINT_MARK('CALL CONTENT %s'% src)
                    dst = dst(keys_local,optscopy)
                content[idx] = content[idx].replace(src,str(dst))

        # 6. detect if any @KEY@ still left undefined
        for v in adj.itervalues():
            m = re_key.search(v)
            if m:
                raise _mycfg.StrictError( "For adjustment for pattern '%s/%s' found undefined key %s" % (detect_pname,tokenname, m.group(0)) )
        for idx in range(0,len(content)):
            m = re_key.search(content[idx])
            if m:
                suf = '.%dpass'%(idx+1) if idx else ''
                raise _mycfg.StrictError( "At template '%s%s' for pattern '%s/%s' found undefined key %s" % (encode_tname,suf,detect_pname,tokenname, m.group(0)) )

        # 7. convert to xml tree and process it
        if xml:
            for idx in range(0, len(content)):
                suf = '.%dpass'%(idx+1) if idx else ''
                err_msg = "At template '%s%s' for pattern '%s/%s' " % (encode_tname,suf,detect_pname,tokenname )

                # a) convert to xmltree
                content[idx] = ETree.ElementTree( ET.fromstring(content[idx]) )
                root = content[idx].getroot()

                # b) replace from adjustment
                for name, value in adj.items():
                    flag = ''
                    if name[0] in ['?','!','+']:
                        flag = name[0]
                        name = name[1:]
                    tagpath = name.split(':')
                    elem = root
                    ##DBG_info("@tsv adj[]=%s/%s",[name,value])
                    for idx in range(0,len(tagpath)):
                        if flag=='+' and (idx==len(tagpath)-1):
                            ##DBG_info("@tsv addelem(parent=%s,tag=%s)",[elem.tag, tagpath[-1]])
                            elem =  ET.add_elem_notnil(elem,tagpath[-1],'')
                        else:
                            elem = _xml_scan( elem, tagpath[:idx+1], err_msg = err_msg,
                                                createIfNotFound = (idx!=0 and flag!='?') )
                    elem.text = value

        return detect_pname, encode_tname, content, optscopy

    def AddJobs( content, **kww ):
        kww.setdefault('required',[])
        for c in content:
            jobname = joblist.addJobXML( c, **kww )
            DBG_info("..add %s",jobname ) #@tsv
            kww['required'] = [jobname]
        return kww['required']


    # PROCESS {AVS_TEMPLATE}
    avsfname = fname + '.avs'
    detect_pname, encode_tname, content, opts  = getEncodeTokens( '{AVS_TEMPLATE}' )

    if os.path.isfile(avsfname) and not cfg.get_opt( opts, 'AVS_OVERWRITE' ):
        say( "%s exists - do not overwrite", os.path.basename(avsfname) )
    else:
        #find non empty AVS names
        extra_avs_sections = filter( len, cfg.get_opt( opts, 'EXTRA_AVS' ) )
        #collect their contents
        extra_avs_contents = map( lambda section: u"\n#EXTRA:%s\n%s"%( section,
                                                                      (''.join(cfg.config['EXTRA_AVS'].get(section,[]))).strip() ),
                                  extra_avs_sections )
        #add to all passes
        content = map(lambda basecontent: u'\n'.join([basecontent.strip()]+extra_avs_contents), content )

        for idx in range(0,len(content)):
            avsfname = fname + (('.%d'%idx+1) if idx>0 else '' ) + '.avs'
            ##print my.util.str_encode(content[idx],'cp866')
            with codecs.open(avsfname,'wb',my.util.baseencode) as f:
                f.write( content[idx])

    to_del = []

    # PROCESS {INDEX_JOB}
    detect_pname, encode_tname, content, opts  = getEncodeTokens( '{INDEX_JOB}', xml=True )
    AddJobs( content )
    to_del.append( _get_elem(content[-1].getroot(),'Output').text )

    index_only = makeint( cfg.get_opt( opts, 'INDEX_ONLY' ) )
    if index_only>0:
        return

    # PREPARE ALL OTHER JOBS (to not leave unfinished if any error)
    video_tuple = getEncodeTokens( '{VIDEO_PASS}', xml=True, allowEmpty = True )
    content = video_tuple[2]
    if len(content):
        keys['@SRCPATH_VIDEO@'] = _get_elem(content[-1].getroot(),'Output').text

    audio_tuple = getEncodeTokens( '{AUDIO_ENCODE}', xml=True, allowEmpty = True )
    content = audio_tuple[2]
    if len(content):
        keys['@SRCPATH_AUDIO@'] = _get_elem(content[-1].getroot(),'Output').text

    mux_tuple = getEncodeTokens( '{MUX_JOB}', xml=True )

    postponed = postponed_queue if index_only<0 else None

    detect_pname, encode_tname, content, opts  = video_tuple
    required = AddJobs( content, postponed = postponed )

    detect_pname, encode_tname, content, opts  = audio_tuple
    required += AddJobs( content, postponed = postponed )

    detect_pname, encode_tname, content, opts  = mux_tuple
    if keys['@SRCPATH_VIDEO@']!=keys['@SRCPATH@']:
        to_del.append( keys['@SRCPATH_VIDEO@'] )
    if keys['@SRCPATH_AUDIO@']!=keys['@SRCPATH@']:
        to_del.append( keys['@SRCPATH_AUDIO@'] )

    if not makebool( cfg.get_opt( opts, 'KEEP_TMP' ) ):
        for delpath in to_del:
            ET.add_elem( _get_elem(content[-1].getroot(),'FilesToDelete'), 'string', delpath )
    res = AddJobs( content, postponed = postponed, required = required )       # Variant requirement of mux job from video/audio
    #res = AddJobs( content, postponed = postponed )

    joblist.save()


if __name__ == '__main__':
    import time
    DBG_info("\n===== %s ======", time.strftime("%d.%m.%y %H:%M") )
    try:
        main()
    except _mycfg.StrictError as e:
        if str(e):
            say( "ERROR: %s", str(e) )


