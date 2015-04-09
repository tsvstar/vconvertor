# usage: convertor.bat [--debug] [--strict] [--key1=value1] [--key2==value2] [...] DIRECTORY_OR_FILE_TO_PROCESS1 [DIRECTORY_OR_FILE_TO_PROCESS2 [..]]

#TODO: cached config(?)
#TODO: parse vbrate / ({<float}, {>float}, {>=float, <=float}
#TODO: better parsing (re.compile("^[A-Za-z_:0-9] *@?[=>]")
#TODO: alternate syntax ( NAME @=> name=val1|name2>=val2,name2<=val2_1 )
#TODO: multiple matches to same pattern(for detect)

import os,sys
import my.config as _mycfg
import my.megui
import my.util
from my.util import makeint, splitl, adddict, vstrip
#__file__
################################

def main():
    global cfg, isDebug, isStrict, mainopts
    global p_encode, p_detect

    """ LOAD ARGV """
    my.util.prepare_console()
    keys, to_process = _mycfg.ParseArgv( sys.argv[1:], optdict={ 'debug':0, 'strict':0} )
    isDebug, isStrict = keys['debug'], keys['strict']

    if isDebug:
        print "isStrict=%s" % (True if isStrict else False)
        print "Extra options: %s" % str(keys)
        print "To process: %s" % str(to_process)


    """ DESCRIBE CONFIG """

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

    	    'MEGUI':         vstrip,		# ??replacing of detect patterns
    	   }

    # sections[sectype] = [ datatype, isname_required, proccessor]
    cfg.sections = { "":         [ 'dict', False, _mycfg.ConfigLoader.load_opt_processor],        # if no section defined, then expect OPT=VALUE pair
                     "TASK":  	 [ 'dict', True,  _mycfg.ConfigLoader.load_opt_processor],        # [TASK] contain OPT=VALUE pairs
                     "EXTRA_AVS":[ 'str',  True,  _mycfg.ConfigLoader.load_text_processor],       # [EXTRA_AVS] contain plain text
                     "DETECT":	 [ 'dict', False, _mycfg.ConfigLoader.load_pattern_processor],    # [DETECT] contain NAME => VALUE pattern pair
                     "ENCODE":	 [ 'dict', False, _mycfg.ConfigLoader.load_pattern_processor],    # [ENCODE] contain NAME => VALUE pattern pair
    		}


    """ LOAD CONFIG """

    print "\nLoad configs"

    # a) load default values
    defaultOpt = ( "FILES_ONLY=*.mp4|*.mts\nRECURSIVE=1\n" )
    cfg.load_config( fname='INTERNAL', content=defaultOpt.split('\n'), strictError = True )
    internal = cfg.config['']	#.copy()
    del cfg.config['']

    # b) load files
    cfg.load_config( fname= os.path.join(my.util.base_path, '!convert.cfg' ), strictError = isStrict )
    cfg.load_config( fname= os.path.join(my.util.base_path, '!templates.cfg' ), strictError = isStrict )

    # c) get undefined values from internal default values
    cfg.config[''][None] = cfg.replace_opt( internal[None], cfg.config[''][None] )

    # d) debug output
    if isDebug:
        print
        for k1,v1 in cfg.config.items():
            for k2,v2 in v1.items():
                if isinstance( v2, dict ):
                    for k3,v3 in v2.items():
                        print "[%s][%s]{%s} = %s" % (k1,k2, k3, str(v3) )
                    else:
                        print "[%s][%s] = %s" % (k1,k2, str(v2) )


    """ PROCESS OPTS (including first iteration of applying tasks) """

    mainopts = dict.fromkeys( cfg.opt, '' )                 # initialize dict with '' for all options
    cfg.replace_opt( mainopts, cfg.config[''][None] )       # replace from base section config
    mainopts['TASK'] = keys.get('TASK', mainopts['TASK'])   # replace TASK from ARGV if given
    tasks = filter( len, cfg.get_opt(mainopts, 'TASK') )    # filter splited(on parse) list of tasks
    for t in tasks:
        #if isDebug:
        print "Apply TASK '%s'" % t
        if t not in cfg.config['TASK']:
            print "Unknown task '%s'" % my.util.str_encode(t,'cp866')
            if isStrict:
                exit(1)
            continue
        cfg.replace_opt( mainopts, cfg.config['TASK'][t] ) # replace from task
    cfg.replace_opt( mainopts, keys ) # replace from given in ARGV options (they have most priority)


    """ PREPARE PATTERNS """

    cfg.pattern_template['DETECT'] = _mycfg.PatternTemplate( 'DETECT',
    						'{CONTAINTER}|VIDEO|{WIDTH}x{HEIGHT}@{FPS}|{V_BRATE} {V_BRATE_TYPE}|{RATIO}|{VCODEC}|{VPROFILE}|{VSCAN_TYPE}|{VSCAN_ORDER}'+
    						'|AUDIO|{A_CHANNEL}|{A_CODEC}|{A_CODEC2}|{A_BRATE}|{A_ALIGNMENT}|{A_DELAY_MS}')
    cfg.pattern_template['ENCODE'] = _mycfg.PatternTemplate( 'ENCODE', '{BITRATE}|{AVS_TEMPLATE}|{INDEX_JOB}|{VIDEO_PASS}|{AUDIO_ENCODE}|{MUX_JOB}' )
    p_detect = cfg.pattern_template['DETECT'].parse_pattern( cfg.config['DETECT'][None], strictError = True )
    p_encode = cfg.pattern_template['ENCODE'].parse_pattern( cfg.config['ENCODE'][None] )

    if isDebug:
        _mycfg.PatternTemplate.PrintParsedList( p_encode )
        _mycfg.PatternTemplate.PrintParsedList( p_detect )

    """ CFG VALIDATION: CHECK TEMPLATES EXISTENCE """
    cfg.template_path = os.path.join( my.util.base_path, 'templates')
    if isStrict:
         PreloadEncodingTemplates( p_encode )

    """ LOAD + REPAIR MEGUI JOBLIST """
    print "Load joblist"
    my.megui.megui_path = cfg.get_opt( mainopts, 'MEGUI' )
    if not len(my.megui.megui_path):
        print "No path to MEGUI defined"
        exit(1)
    if not os.path.isdir(my.megui.megui_path):
        print "Invalid path to MEGUI (%s)" % my.megui.megui_path
        exit(1)

    """
    my.megui.load_jobs()
    if my.megui.dirty:
        print "Restore missed jobs"
        my.megui.save_jobs()
    """

    if len(to_process)==0:
        print "No source given"
        exit()

    """ PHASE1: Collect Info """
    process_queue = PHASE1( to_process )
    exit(1)

    """  PHASE2: Add task """
    print
    PHASE2( process_queue )



####################################################################

def PreloadEncodingTemplates( template_dict ):
    """-- try to load all templates in all patterns. exception on error--"""
    for pval in template_dict.itervalues():
        for tokenname in [ "{AVS_TEMPLATE}", "{INDEX_JOB}", "{VIDEO_PASS}",
                            "{AUDIO_ENCODE}","{MUX_JOB}" ]:
            cfg.load_multi_templates( pval.get(tokenname,None), fatal = True )


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
    print "PHASE 1: Collect info"
    mediaInfoExe = os.path.join(my.util.base_path,'Media_07.72','MediaInfo.exe')
    #mediaInfoTemplate = os.path.join(my.util.base_path,'Media_07.72','template3.txt')
    #output = '--Output="file://%s"'%mediaInfoTemplate
    output = ( "--Output="+
        """General;%Format%
Video;|VIDEO|%Width%x%Height%@%FrameRate%|%BitRate/String%|%DisplayAspectRatio%|%Format%|%Format_Profile%|%ScanType%|%ScanOrder%
Audio;|AUDIO|%Channel(s)%|%Codec%|%Codec/String%|%BitRate/String%|%Alignment%|%Delay%""" )


    cacheObj = my.util.FileInfoCache( '.cache' )
    processor = MyCachedProcessor( [ mediaInfoExe, output ],                # process command
                                    cacheObj,
                                    ##validator = validateValue,
                                    shell = False,
                                    verbose = ( 3 if isDebug else 2 ) )

    process_queue = []
    with my.util.PsuedoMultiThread( processor, max_t=2, shell=processor.shell ) as worker:
      for fname in to_process:
        if os.path.isdir(fname):
            result = my.util.scan_dir( fname,
                            recursive = cfg.get_opt( mainopts, 'RECURSIVE' ),
                            pattern = cfg.get_opt( mainopts, 'FILES_ONLY' ) )
            for fname in result:
                worker.add_task(fname)
        elif os.path.isfile(fname):
            worker.add_task(fname)
        else:
            print "Unknown source: %s" % fname
            if isStrict:
                raise _mycfg.StrictError()

      for fname in processor.processed:
        process_queue.append( [ fname, cacheObj.cache[fname] ] )
    return process_queue




"""
    ********** PHASE 2: FIND MATCHED TEMPLATES **************
"""

def PHASE2( process_queue ):
    print "PHASE 2: Generate tasks"
    global p_detect

    # FOR EACH QUEUE ITEM:
    for fname, info in process_queue:
        if info in [None,'']:
            continue

        # 1) parse mediainfo
        parsed_info = MyCachedProcessor.validate( info, verbose = True )
        if parsed_info is None:
            print "^^for file %s" % str_encode(fname,'cp866')
            continue
        parsed_info = parsed_info['_']

        # 2) find matched 'detect' patterns
        detected = []
        is_forbid = False
        for pname, pdict in p_detect.iteritems():
            for k,v in pdict:
                if v in [None,'']:
                    continue
                if k not in parsed_info:
                    break
                if parsed_info[k] != v:
                    break
            else:
                is_forbid = is_forbid or ( pname if pname.startswith('__forbid') else False )
                detected.append( pname )

        #3) cutoff suffix from detect pattern
        detected = list( set( map( lambda s: s.split('.',1)[0], detected ) ) )

        print "%(fname)s\t=> %(w)s*%(h)s@%(fps)s = %(ar)s; %(profile)s ( %(detected)s )" % {
                        'fname': my.util.str_cp866(fname),
                        'w': parsed_info['{WIDTH}'],
                        'h': parsed_info['{HEIGHT}'],
                        'fps': parsed_info['{FPS}'],
                        'ar': parsed_info['{RATIO}'],
                        'profile': parsed_info['{VPROFILE}'],
                        'detected': ' + '.join(detected) if len(detected) else "BASIC",
                    }

        # "found "__forbid*" pattern - means do not process such video ever
        if is_forbid:
            print " >> skipped (match to '%s' pattern)" % (is_forbid)
            continue

        # 4) apply ENFORCE_PATTERN if given
            # a) if "|pattern1|pattern2|.." - then append
            # b) if "pattern1|pattern2|.."  - then replace
        enforce_patterns = cfg.get_opt( mainopts, 'ENFORCE_PATTERN' )
        if enforce_patterns:
            if enforce_patterns[0]=='':
                enforce_patterns = detected + filter(len, enforce_patterns)
            if set(enforce_patterns)!= set(detected):
                print " >> enforced encoding as %s" % '+'.join(set(enforce_patterns))
            detected = enforce_patterns

        #
        to_encode = PHASE2_2( detected )
        if to_encode is None:
            continue

        PHASE2_3( to_encode )



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

    # initialize object which do scaning job
    #   (find for given token and given pattern most precise existed correspondance)
    encoder = _mycfg.Encoding( cfg, cfg.get_opt( mainopts, 'SUFFIX' ) )

    to_encode = {}                      # to_encode[job_type] = {pname, pvalue, ?adj?, ?tmpl_list? }
    sysPatternList = [ 'BASIC', 'TOP' ]

    # OUTER CYCLE: PROCESS EACH TOKEN
    for p_token_name in p_encode :
        if p_token_name in ['_']:       # skip 'printable value'
            continue


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
                    default_brate = cfgcfg.get_opt( mainopts, 'BITRATE' )
                    if default_brate <= 0:
                        raise _mycfg.StrictError( "No valid bitrate defined in any encoding patterns or options" )
                    to_encode_cur = { 'pname': 'OPTION:BITRATE',  'pvalue': default_brate }
                else:
                # b) For other cases - error. Should be defined exactly one
                    raise _mycfg.StrictError( "Undefined %s" % p_token_name )
        except _mycfg.StrictError as e:
            print " >> skipped (%s)" % str(e)
            if isStrict:
                raise
            return None
        finally:
            if (isDebug):
                adj = to_encode_cur.get('adj',None)
                if adj is not None:
                    ar_joined_pairs = map(lambda a: a[0] if a[1] is None else '='.join(a), adj)
                    adj = "{%s}" % ( ','.join(ar_joined_pairs) )
                print "Token %(token)s. Path of scaned patterns: (%(path)s). Value = %(value)s%(adj)s " % {
                            'token': p_token_name,
                            'path': ' -> '.join(encoder.path),
                            'value': repr(to_encode_cur.get('pvalue',None)),
                            'adj': adj  }

        to_encode[p_token_name] = to_encode_cur

    return to_encode


"""
    ********** PHASE 2_3: GENERATE MEGUI TASK **************
"""

def PHASE2_3( to_encode ):

    print "!!TODO!!"
    tokenlist = [ "{AVS_TEMPLATE}", "{INDEX_JOB}", "{VIDEO_PASS}",
                            "{AUDIO_ENCODE}","{MUX_JOB}" ]

    print "JOBS: " + ', '.join( lambda k: "%s=%s"%(k,to_encode.get(k,'???')), to_encode )
    return

    # prepare jobs
    jobs = []

    # add jobs
    for j in jobs:
        my.megui.add_job( j )
    my.megui.save_jobs()



if __name__ == '__main__':
    main()


