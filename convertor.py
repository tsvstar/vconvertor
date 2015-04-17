# usage: convertor.bat [--debug] [--strict] [--key1=value1] [--key2==value2] [...] DIRECTORY_OR_FILE_TO_PROCESS1 [DIRECTORY_OR_FILE_TO_PROCESS2 [..]]

#TO_TEST: ENCODE{smth}, 2_3 phase, adjustments(raw, path:tag:name, flags(+?))

#TODO: cached config(?)
#TODO: parse vbrate / ({<float}, {>float}, {>=float, <=float}
#TODO: better parsing (re.compile("^[A-Za-z_:0-9] *@?[=>]")
#TODO: alternate syntax ( NAME @=> name=val1|name2>=val2,name2<=val2_1 )
#TODO: multiple matches to same pattern(for detect)

#TODO: adjustment -- give path in XML to fix (  DAR:AR=@{RATIO}@|DAR:X=@{AR_X}@|DAR:Y=@{AR_Y}@ )
#TODO: adjustment -- can have +=
#TODO: adjustment -- if starts from ? -- means do not add if not existent
#TODO:                              + -- add a new one anyway (FilesDelete:string for example)
#TODO: KEEP_TMP, RESOLVE

#TODO: option - delete temporary files (video+audio+stat [?stat del-is defined right in job])

#TODO: if token name starts from {!}  - case insensetive comparision

import os, sys, copy, re
import xml.etree.ElementTree as ET

import my.config as _mycfg
import my.megui, my.util
from my.megui import _get_elem, _add_elem
from my.util import makeint, makebool, splitl, adddict, vstrip

################################

def main():
    global cfg, isDebug, isStrict, mainopts
    global p_encode, p_detect, postponed_queue

    """ LOAD ARGV """
    my.util.prepare_console()
    argv = _mycfg.prepareARGV( sys.argv[1:] )
    keys, to_process = _mycfg.ParseArgv( argv, optdict={ 'debug':0, 'strict':0} )
    isDebug, isStrict = keys['debug'], keys['strict']

    if isDebug:
        print "isStrict=%s" % (True if isStrict else False)
        print "Extra options: %s" % str(keys)
        print "To process: %s" % str(to_process)


    """ DESCRIBE CONFIG """

    cfg = _mycfg.ConfigLoader( isDebug = isDebug )
    cfg.opt = { 'ENFORCE_BITRATE':  makeint, # If defined and valid, that means "I surely know which video bitrate I'd like to have"
    	    'ENFORCE_PATTERN': splitl,		 # If defined, that means "I know which exactly templates should be used"

    	    'BITRATE':       makeint,		# Default value of bitrate (used if no correct defined in any matched template)
    	    'RECURSIVE':     makebool,		# is recursive scan for source files
    	    'AVS_OVERWRITE': makebool,     	# Should .AVS be overwrited
    	    'INDEX_ONLY':    makeint,		# Should only AVS+index job be created[ 0=regular convert, 1=only index job, -1=first all index than all convert]
    	    'KEEP_TMP':      makebool,     	# Should do not remove intermediary files
    	    '@':             splitl,    	# @{KEY} = value -- set the KEY to use it later in jobs as @KEY@
    	    'EXTRA_AVS':     splitl,    	# if not empty, then add to .AVS file correspondend [EXTRA_AVS=xxx] section. Could be several: extra1+extra2+...
    	    'SUFFIX':	     vstrip,		# suffix for template (if defined will try to use 'name.suffix' template first; '.old' )

    	    'FILES_ONLY':    splitl,  		# which files should be processed
    	    'MATCH_ONLY':    splitl,		# if only they are match to any of given template
    	    'TASK':          splitl,

    	    'ENCODE':        adddict,       # replacing of encoding sequences  #@tsv TO IMPLEMENT!!
    	    'DETECT':        adddict,		# replacing of detect patterns
            'RESOLVE':       splitl,        # TODO!! RESOLVE{sony:720|_dga} = _dga|dgasony  # if video match to several patterns and they have collision how to process - we can resolve this by saying which encoding pattern should be used instead

    	    'MEGUI':         vstrip,		# path to MEGUI
    	   }

    # sections[sectype] = [ datatype, isname_required, proccessor]
    cfg.sections = { "":         [ 'dict', False, _mycfg.ConfigLoader.load_opt_processor],        # if no section defined, then expect OPT=VALUE pair
                     "TASK":  	 [ 'dict', True,  _mycfg.ConfigLoader.load_opt_processor],        # [TASK] contain OPT=VALUE pairs
                     "EXTRA_AVS":[ 'str',  True,  _mycfg.ConfigLoader.load_text_processor],       # [EXTRA_AVS] contain plain text
                     "DETECT":	 [ 'dict', False, _mycfg.ConfigLoader.load_pattern_processor],    # [DETECT] contain NAME => VALUE pattern pair
                     "ENCODE":	 [ 'dict', False, _mycfg.ConfigLoader.load_pattern_processor],    # [ENCODE] contain NAME => VALUE pattern pair
    		}

    cfg.tpath = './templates'


    """ LOAD CONFIG """

    print "\nLoad configs"

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
    print mainopts  #@tsv
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

    mainopts['MATCH_ONLY'] = set( filter( len, cfg.get_opt( mainopts, 'MATCH_ONLY' ) ) )
    print mainopts  #@tsv

    """ PREPARE PATTERNS """

    cfg.pattern_template['DETECT'] = _mycfg.PatternTemplate( 'DETECT',
    						'{CONTAINER}|VIDEO|{WIDTH}x{HEIGHT}@{FPS}|{V_BRATE} {V_BRATE_TYPE}|{RATIO}={AR_X}:{AR_Y}|{VCODEC}|{VPROFILE}|{VSCAN_TYPE}|{VSCAN_ORDER}'+
    						'|AUDIO|{A_CHANNEL}|{A_CODEC}|{A_CODEC2}|{A_BRATE}|{A_ALIGNMENT}|{A_DELAY_MS}')
    cfg.pattern_template['ENCODE'] = _mycfg.PatternTemplate( 'ENCODE', '{BITRATE}|{AVS_TEMPLATE}|{INDEX_JOB}|{VIDEO_PASS}|{AUDIO_ENCODE}|{MUX_JOB}' )
    ##for k in cfg.pattern_template:              # @tsv
    ##    cfg.pattern_template[k].isDebug=True
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
    my.megui.megui_path = cfg.get_opt( mainopts, 'MEGUI' ).rstrip("\\/")+"\\"
    if not len(my.megui.megui_path):
        print "No path to MEGUI defined"
        exit(1)
    if not os.path.isdir(my.megui.megui_path):
        print "Invalid path to MEGUI (%s)" % my.megui.megui_path
        exit(1)

    joblist = my.megui.JobList()
    ##my.megui.print_xml(joblist.tree._root)    #@tsv
    my.megui.load_jobdir(joblist)
    if joblist.dirty:
        print "Restore missed jobs"
        joblist.save()

    if len(to_process)==0:
        print "No source given"
        exit()

    """ PHASE1: Collect Info """
    process_queue = PHASE1( to_process )
    isDebug = 2

    """  PHASE2: Add task """
    print
    postponed_queue = []
    PHASE2( process_queue, joblist )
    joblist.addPostponed( postponed_queue )
    joblist.save()
    ##for k,v in p_encode.iteritems(): print k,'=',v


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
            print "Unknown source: %s" % fname
            if isStrict:
                raise _mycfg.StrictError()

      for fname in processor.processed:
        process_queue.append( [ fname, cacheObj.get(fname,check=False) ] )
    return process_queue




"""
    ********** PHASE 2: FIND MATCHED TEMPLATES **************
"""

def PHASE2( process_queue, joblist ):
    print "PHASE 2: Generate tasks"
    global p_detect

    isDebugPhase2 = False

    # FOR EACH QUEUE ITEM:
    for fname, info in process_queue:
        if info in [None,'']:
            say ("No info for '%s' - skip it", fname)
            continue

        # 1) parse mediainfo
        parsed_info = MyCachedProcessor.validate( info, verbose = True )
        if parsed_info is None:
            print "^^for file %s" % str_encode(fname,'cp866')
            continue
        parsed_info = parsed_info['_']
        if isDebugPhase2: print parsed_info       #@tsv

        # 2) find matched 'detect' patterns
        detected = []
        is_forbid = False
        for pname, pdict in p_detect.iteritems():
            if isDebugPhase2:
                print
                print "CHECK", pname         #@tsv
                for k,v in pdict.iteritems(): print k,'=',repr(v)

            for k,v in pdict.iteritems():
                if k in ['_']:
                    continue
                if v in [None,'']:
                    continue
                if isDebugPhase2: print "==", k, v, parsed_info.get(k)
                if k not in parsed_info:
                    if isDebugPhase2: print "NOKEY"
                    break
                if parsed_info[k] != v:
                    if isDebugPhase2: print "NOTMATCH"
                    break
            else:
                if isDebugPhase2: print "MATCH TO %s"%pname
                is_forbid = is_forbid or ( pname if pname.startswith('__forbid') else False )
                detected.append( pname )

        #3) cutoff suffix from detect pattern (that the thing which allow to make a lot of correspondance to the same patter)
        detected = list( set( map( lambda s: s.split('.',1)[0], detected ) ) )

        print u"%(fname)s\t=> %(w)s*%(h)s@%(fps)s = %(ar)s; %(profile)s ( %(detected)s )" % {
                        'fname': my.util.str_decode(fname),
                        #'fname': my.util.str_cp866(fname),
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

        if mainopts['MATCH_ONLY'] and len( set(detected) & mainopts['MATCH_ONLY'] )==0:
            print " >> skipped( patterns doesn't match to any of MATCH_ONLY: %s)" % ','.join(mainopts['MATCH_ONLY'])
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

    #@tsv
    print "PHASE2_2", detected

    # initialize object which do scaning job
    #   (find for given token and given pattern most precise existed correspondance)
    encoder = _mycfg.Encoding( p_encode, cfg, cfg.get_opt( mainopts, 'SUFFIX' ) )

    to_encode = {}                      # to_encode[job_type] = {pname, pvalue, ?adj?, ?tmpl_list? }
    sysPatternList = [ 'BASIC', 'TOP' ]

    # OUTER CYCLE: PROCESS EACH TOKEN
    print cfg.pattern_template['ENCODE']
    for p_token_name in cfg.pattern_template['ENCODE'].ar_tokens:
        if p_token_name in ['_']:       # skip 'printable value'
            continue
        print "!!%s" % p_token_name     #@tsv

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
            raise   # @tsv
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
                print "Token %(token)s. Path of scaned patterns: (%(path)s). Value = %(value)s %(adj)s " % {
                            'token': p_token_name,
                            'path': ' -> '.join(encoder.path),
                            'value': repr(to_encode_cur.get('pvalue',None)),
                            'adj': (adj if adj is not None else '') }

        to_encode[p_token_name] = to_encode_cur

    return to_encode


"""
    ********** PHASE 2_3: GENERATE MEGUI TASK **************
"""

def PHASE2_3( fname, to_encode, info, joblist ):


    print "PHASE2_3"
    print "!!TODO!\n"
    print "fname", fname
    ##print "to_encode", to_encode
    print to_encode['{AVS_TEMPLATE}']
    print "info", info
    print "mainopt", mainopts

    def GetKeys(basekeys):
        keys = {}
        # add from mainopts
        kopts = cfg.get_opt( mainopts, '@' )
        if isinstance(kopts,dict):
            for k,v in kopts.iteritems():
                keys["@%s@"%k]=v
        # add detect values
        for k,v in info.iteritems():
            keys["@%s@"%k] = v

        # update/replace from basekeys
        keys.update(basekeys)
        return keys

    basekeys = { '@SRCPATH@': fname,                            # source file
             '@SRC_PATH_WO_EXT@': os.path.splitext(fname)[0],   # source file without extension
             '@SRCPATH_VIDEO@': fname,                          # intermediary video file
             '@SRCPATH_AUDIO@': fname,                          # intermediary audio file
             '@MEGUI@': my.megui.megui_path,
             '@BITRATE@': to_encode.get("{BITRATE}",{}).get("pvalue",0)
    }
    keys = GetKeys(basekeys)
    keys['@{A_DELAY_MS}@'] = "%f" % my.utils.makefloat(keys['@{A_DELAY_MS}@'])

    print 'keys', keys
    #for k,v in keys.iteritems():  print k,v

    # init copy of main opts (here will be accumulated options from adjustments
    optscopy = copy.deepcopy( mainopts )

    def _xml_scan( xml, tag_path, err_msg='', createIfNotFound = False ):
        tag = tag_path[-1]
        elems = map( lambda e: e, root.iter(tag) )
        if len(elems)==0:
            if createIfNotFound:
                elems = [ _add_elem(xml,tag,'') ]
            else:
                raise _mycfg.StrictError( err_msg + "not found adjustment key <%s>"% ':'.join(tag_path) )
        elif len(elems)>1:
            raise _mycfg.StrictError( err_msg + "found several adjustment key <%s>"% ':'.join(tag_path) )
        return elems[0]


    # Workhorse. Made parsing of job and applying of everything
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
        content = filter(len, d.get('tmpl_list',[]) )       # list of templates content (multipass)
        adj_v = dict( filter(len, d.get('adj',[]) ) )       # dict of adjustments

        if not allowEmpty and len(content)==0:
            raise _mycfg.StrictError( "ERROR: Empty %s for %s %s" % ( tokenname, detect_pname, encode_tname) )

        # 2. adjustment = baseAdjustment + p_encode['adj'](override baseAdjustment)
        adj = dict(baseAdjustment)
        adj.update(adj_v)

        # 3. prepare adjustments by keys
        for k,v in adj.items():
            if v.find('@')>=0:
                for src, dst in keys.iteritems():
                    v = v.replace(src,dst)
                adj[k]=v

        # 4. process opts and keys from adjustments
        keys_local = list( keys )
        for k,v in adj.items():
            if len(k)>2 and k[0]=='%' and k[-1]=='%':
                optname = k[1:-1]
                if optname in cfg.opt:
                    cfg.replace_opt( optscopy, {optname:v} )
                del adj[k]
            elif len(k)>2 and k[0]=='@' and k[-1]=='@':
                keys_local[ k[1:-1] ] = v
                del adj[k]

        # 5. prepare content by keys
        for idx in range(0,len(content)):
            for src, dst in keys.iteritems():
                content[idx] = content[idx].replace(src,dst)

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
                content[idx] = ET.ElementTree( ET.fromstring(content[idx]) )
                root = content[idx].getroot()

                # b) replace from adjustment
                for name, value in adj:
                    flag = ''
                    if name[0] in ['?','!','+']:
                        flag = name[0]
                        name = name[1:]
                    tagpath = name.split(':')
                    elem = root
                    for idx in range(0,len(tagpath)):
                        if flag=='+' and (idx==len(tagpath)+1):
                            elem = _add_elem(elem,tagpath[-1],'')
                        else:
                            elem = _xml_scan( elem, tagpath[:idx+1], err_msg= err_msg,
                                                createIfNotFound = (idx!=0 and flag!='?') )
                    elem.text = value

        return detect_pname, encode_tname, content, adj, optscopy

    def AddJobs( content, **kww ):
        kww.setdefault('required',[])
        for c in content:
            jobname = joblist.addJobXML( c, **kww )
            kww['required'] = [jobname]
        return kww['required']


#to_encode {'{BITRATE}': {'pname': 'OPTION:BITRATE', 'pvalue': 1500},
#'{AVS_TEMPLATE}': {'pname': '__dga', 'pvalue': 'dga.avs', 'tmpl_list': ['LoadPlugin("@MEGUI@/tools/dgavcindex/DGAVCDecode.dll")\nAVCSource("@SRCPATH@.dga")\n']},
#'{INDEX_JOB}': {'pname': '__dga', 'pvalue': 'dga.idx', 'tmpl_list': ['<?xml version="1.0"?>\n<TaggedJob xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n  <EncodingSpeed />\n  <Job xsi:type="DGAIndexJob">\n    <Input>@SRC_PATH@</Input>\n    <Output>@SRC_PATH@.dga</Output>\n    <FilesToDelete>\n      <string>@SRC_PATH_WO_EXT@.log</string>\n    </FilesToDelete>\n    <LoadSources>false</LoadSources>\n    <DemuxVideo>false</DemuxVideo>\n    <DemuxMode>0</DemuxMode>\n    <AudioTracks />\n    <AudioTracksDemux />\n  </Job>\n  <RequiredJobNames />\n  <EnabledJobNames />\n  <Name>job9</Name>\n  <Status>WAITING</Status>\n  <Start>0001-01-01T00:00:00</Start>\n  <End>0001-01-01T00:00:00</End>\n</TaggedJob>']},
#'{VIDEO_PASS}': {'pname': 'BASIC', 'pvalue': 'x264base', 'tmpl_list': ['<?xml version="1.0"?>\n<TaggedJob xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n  <EncodingSpeed />\n  <Job xsi:type="VideoJob">\n    <Input>@SRCPATH@.avs</Input>\n    <Output />\n    <FilesToDelete />\n    <Zones />\n    <DAR />\n    <Settings xsi:type="x264Settings">\n      <EncodingMode>2</EncodingMode>\n      <BitrateQuantizer>1000</BitrateQuantizer>\n      <KeyframeInterval>250</KeyframeInterval>\n      <NbBframes>3</NbBframes>\n      <MinQuantizer>0</MinQuantizer>\n      <MaxQuantizer>69</MaxQuantizer>\n      <V4MV>false</V4MV>\n      <QPel>false</QPel>\n      <Trellis>false</Trellis>\n      <CreditsQuantizer>40</CreditsQuantizer>\n      <Logfile>@SRCPATH@.stats</Logfile>\n      <VideoName />\n      <CustomEncoderOptions />\n      <FourCC>0</FourCC>\n      <MaxNumberOfPasses>3</MaxNumberOfPasses>\n      <NbThreads>0</NbThreads>\n      <x264PresetLevel>medium</x264PresetLevel>\n      <x264PsyTuning>NONE</x264PsyTuning>\n      <QuantizerCRF>1000</QuantizerCRF>\n      <InterlacedMode>progressive</InterlacedMode>\n      <TargetDeviceXML>0</TargetDeviceXML>\n      <BlurayCompatXML>False</BlurayCompatXML>\n      <NoDCTDecimate>false</NoDCTDecimate>\n      <PSNRCalculation>false</PSNRCalculation>\n      <NoFastPSkip>false</NoFastPSkip>\n      <NoiseReduction>0</NoiseReduction>\n      <NoMixedRefs>false</NoMixedRefs>\n      <X264Trellis>1</X264Trellis>\n      <NbRefFrames>3</NbRefFrames>\n      <AlphaDeblock>0</AlphaDeblock>\n      <BetaDeblock>0</BetaDeblock>\n      <SubPelRefinement>7</SubPelRefinement>\n      <MaxQuantDelta>4</MaxQuantDelta>\n      <TempQuantBlur>0</TempQuantBlur>\n      <BframePredictionMode>1</BframePredictionMode>\n      <VBVBufferSize>0</VBVBufferSize>\n      <VBVMaxBitrate>0</VBVMaxBitrate>\n      <METype>1</METype>\n      <MERange>16</MERange>\n      <MinGOPSize>25</MinGOPSize>\n      <IPFactor>1.4</IPFactor>\n      <PBFactor>1.3</PBFactor>\n      <ChromaQPOffset>0</ChromaQPOffset>\n      <VBVInitialBuffer>0.9</VBVInitialBuffer>\n      <BitrateVariance>1.0</BitrateVariance>\n      <QuantCompression>0.6</QuantCompression>\n      <TempComplexityBlur>20</TempComplexityBlur>\n      <TempQuanBlurCC>0.5</TempQuanBlurCC>\n      <SCDSensitivity>40</SCDSensitivity>\n      <BframeBias>0</BframeBias>\n      <PsyRDO>1.0</PsyRDO>\n      <PsyTrellis>0</PsyTrellis>\n      <Deblock>true</Deblock>\n      <Cabac>true</Cabac>\n      <UseQPFile>false</UseQPFile>\n      <WeightedBPrediction>true</WeightedBPrediction>\n      <WeightedPPrediction>2</WeightedPPrediction>\n      <NewAdaptiveBFrames>1</NewAdaptiveBFrames>\n      <x264BFramePyramid>2</x264BFramePyramid>\n      <x264GOPCalculation>1</x264GOPCalculation>\n      <ChromaME>true</ChromaME>\n      <MacroBlockOptions>3</MacroBlockOptions>\n      <P8x8mv>true</P8x8mv>\n      <B8x8mv>true</B8x8mv>\n      <I4x4mv>true</I4x4mv>\n      <I8x8mv>true</I8x8mv>\n      <P4x4mv>false</P4x4mv>\n      <AdaptiveDCT>true</AdaptiveDCT>\n      <SSIMCalculation>false</SSIMCalculation>\n      <StitchAble>false</StitchAble>\n      <QuantizerMatrix>Flat (none)</QuantizerMatrix>\n      <QuantizerMatrixType>0</QuantizerMatrixType>\n      <DeadZoneInter>21</DeadZoneInter>\n      <DeadZoneIntra>11</DeadZoneIntra>\n      <X26410Bits>true</X26410Bits>\n      <OpenGop>False</OpenGop>\n      <X264PullDown>0</X264PullDown>\n      <SampleAR>0</SampleAR>\n      <ColorMatrix>0</ColorMatrix>\n      <ColorPrim>0</ColorPrim>\n      <Transfer>0</Transfer>\n      <AQmode>1</AQmode>\n      <AQstrength>1.0</AQstrength>\n      <QPFile />\n      <Range>auto</Range>\n      <x264AdvancedSettings>true</x264AdvancedSettings>\n      <Lookahead>40</Lookahead>\n      <NoMBTree>true</NoMBTree>\n      <ThreadInput>true</ThreadInput>\n      <NoPsy>false</NoPsy>\n      <Scenecut>true</Scenecut>\n      <Nalhrd>0</Nalhrd>\n      <X264Aud>false</X264Aud>\n      <X264SlowFirstpass>false</X264SlowFirstpass>\n      <PicStruct>false</PicStruct>\n      <FakeInterlaced>false</FakeInterlaced>\n      <NonDeterministic>false</NonDeterministic>\n      <SlicesNb>0</SlicesNb>\n      <MaxSliceSyzeBytes>0</MaxSliceSyzeBytes>\n      <MaxSliceSyzeMBs>0</MaxSliceSyzeMBs>\n      <Profile>2</Profile>\n      <AVCLevel>L_UNRESTRICTED</AVCLevel>\n      <TuneFastDecode>false</TuneFastDecode>\n      <TuneZeroLatency>false</TuneZeroLatency>\n    </Settings>\n  </Job>\n  <RequiredJobNames />\n  <EnabledJobNames>\n    <string>job5</string>\n  </EnabledJobNames>\n  <Name>job4</Name>\n  <Status>WAITING</Status>\n  <Start>0001-01-01T00:00:00</Start>\n  <End>0001-01-01T00:00:00</End>\n</TaggedJob>',
#                                                                       '<?xml version="1.0"?>\n<TaggedJob xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n  <EncodingSpeed />\n  <Job xsi:type="VideoJob">\n    <Input>@SRCPATH@.avs</Input>\n    <Output>@SRCPATH@.264</Output>\n    <FilesToDelete>\n      <string>@SRCPATH@.stats</string>\n      <string>@SRCPATH@.stats.mbtree</string>\n    </FilesToDelete>\n    <Zones />\n    <DAR />\n    <Settings xsi:type="x264Settings">\n      <EncodingMode>3</EncodingMode>\n      <BitrateQuantizer>1000</BitrateQuantizer>\n      <KeyframeInterval>250</KeyframeInterval>\n      <NbBframes>3</NbBframes>\n      <MinQuantizer>0</MinQuantizer>\n      <MaxQuantizer>69</MaxQuantizer>\n      <V4MV>false</V4MV>\n      <QPel>false</QPel>\n      <Trellis>false</Trellis>\n      <CreditsQuantizer>40</CreditsQuantizer>\n      <Logfile>@SRCPATH@.stats</Logfile>\n      <VideoName />\n      <CustomEncoderOptions />\n      <FourCC>0</FourCC>\n      <MaxNumberOfPasses>3</MaxNumberOfPasses>\n      <NbThreads>0</NbThreads>\n      <x264PresetLevel>medium</x264PresetLevel>\n      <x264PsyTuning>NONE</x264PsyTuning>\n      <QuantizerCRF>1000</QuantizerCRF>\n      <InterlacedMode>progressive</InterlacedMode>\n      <TargetDeviceXML>0</TargetDeviceXML>\n      <BlurayCompatXML>False</BlurayCompatXML>\n      <NoDCTDecimate>false</NoDCTDecimate>\n      <PSNRCalculation>false</PSNRCalculation>\n      <NoFastPSkip>false</NoFastPSkip>\n      <NoiseReduction>0</NoiseReduction>\n      <NoMixedRefs>false</NoMixedRefs>\n      <X264Trellis>1</X264Trellis>\n      <NbRefFrames>3</NbRefFrames>\n      <AlphaDeblock>0</AlphaDeblock>\n      <BetaDeblock>0</BetaDeblock>\n      <SubPelRefinement>7</SubPelRefinement>\n      <MaxQuantDelta>4</MaxQuantDelta>\n      <TempQuantBlur>0</TempQuantBlur>\n      <BframePredictionMode>1</BframePredictionMode>\n      <VBVBufferSize>0</VBVBufferSize>\n      <VBVMaxBitrate>0</VBVMaxBitrate>\n      <METype>1</METype>\n      <MERange>16</MERange>\n      <MinGOPSize>25</MinGOPSize>\n      <IPFactor>1.4</IPFactor>\n      <PBFactor>1.3</PBFactor>\n      <ChromaQPOffset>0</ChromaQPOffset>\n      <VBVInitialBuffer>0.9</VBVInitialBuffer>\n      <BitrateVariance>1.0</BitrateVariance>\n      <QuantCompression>0.6</QuantCompression>\n      <TempComplexityBlur>20</TempComplexityBlur>\n      <TempQuanBlurCC>0.5</TempQuanBlurCC>\n      <SCDSensitivity>40</SCDSensitivity>\n      <BframeBias>0</BframeBias>\n      <PsyRDO>1.0</PsyRDO>\n      <PsyTrellis>0</PsyTrellis>\n      <Deblock>true</Deblock>\n      <Cabac>true</Cabac>\n      <UseQPFile>false</UseQPFile>\n      <WeightedBPrediction>true</WeightedBPrediction>\n      <WeightedPPrediction>2</WeightedPPrediction>\n      <NewAdaptiveBFrames>1</NewAdaptiveBFrames>\n      <x264BFramePyramid>2</x264BFramePyramid>\n      <x264GOPCalculation>1</x264GOPCalculation>\n      <ChromaME>true</ChromaME>\n      <MacroBlockOptions>3</MacroBlockOptions>\n      <P8x8mv>true</P8x8mv>\n      <B8x8mv>true</B8x8mv>\n      <I4x4mv>true</I4x4mv>\n      <I8x8mv>true</I8x8mv>\n      <P4x4mv>false</P4x4mv>\n      <AdaptiveDCT>true</AdaptiveDCT>\n      <SSIMCalculation>false</SSIMCalculation>\n      <StitchAble>false</StitchAble>\n      <QuantizerMatrix>Flat (none)</QuantizerMatrix>\n      <QuantizerMatrixType>0</QuantizerMatrixType>\n      <DeadZoneInter>21</DeadZoneInter>\n      <DeadZoneIntra>11</DeadZoneIntra>\n      <X26410Bits>true</X26410Bits>\n      <OpenGop>False</OpenGop>\n      <X264PullDown>0</X264PullDown>\n      <SampleAR>0</SampleAR>\n      <ColorMatrix>0</ColorMatrix>\n      <ColorPrim>0</ColorPrim>\n      <Transfer>0</Transfer>\n      <AQmode>1</AQmode>\n      <AQstrength>1.0</AQstrength>\n      <QPFile />\n      <Range>auto</Range>\n      <x264AdvancedSettings>true</x264AdvancedSettings>\n      <Lookahead>40</Lookahead>\n      <NoMBTree>true</NoMBTree>\n      <ThreadInput>true</ThreadInput>\n      <NoPsy>false</NoPsy>\n      <Scenecut>true</Scenecut>\n      <Nalhrd>0</Nalhrd>\n      <X264Aud>false</X264Aud>\n      <X264SlowFirstpass>false</X264SlowFirstpass>\n      <PicStruct>false</PicStruct>\n      <FakeInterlaced>false</FakeInterlaced>\n      <NonDeterministic>false</NonDeterministic>\n      <SlicesNb>0</SlicesNb>\n      <MaxSliceSyzeBytes>0</MaxSliceSyzeBytes>\n      <MaxSliceSyzeMBs>0</MaxSliceSyzeMBs>\n      <Profile>2</Profile>\n      <AVCLevel>L_UNRESTRICTED</AVCLevel>\n      <TuneFastDecode>false</TuneFastDecode>\n      <TuneZeroLatency>false</TuneZeroLatency>\n    </Settings>\n  </Job>\n  <RequiredJobNames>\n    <string>job4</string>\n  </RequiredJobNames>\n  <EnabledJobNames />\n  <Name>job5</Name>\n  <Status>WAITING</Status>\n  <Start>0001-01-01T00:00:00</Start>\n  <End>0001-01-01T00:00:00</End>\n</TaggedJob>']},
#'{AUDIO_ENCODE}': {'pname': 'BASIC', 'pvalue': 'aac_base', 'tmpl_list': ['<?xml version="1.0"?>\n<TaggedJob xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n  <EncodingSpeed />\n  <Job xsi:type="AudioJob">\n    <Input>@SRCPATH@</Input>\n    <Output>@SRCPATH@.tmp.mp4</Output>\n    <FilesToDelete />\n    <CutFile />\n    <Settings xsi:type="NeroAACSettings">\n      <PreferredDecoderString>NicAudio</PreferredDecoderString>\n      <DownmixMode>KeepOriginal</DownmixMode>\n      <BitrateMode>ABR</BitrateMode>\n      <Bitrate>125</Bitrate>\n      <AutoGain>false</AutoGain>\n      <SampleRateType>deprecated</SampleRateType>\n      <SampleRate>KeepOriginal</SampleRate>\n      <TimeModification>KeepOriginal</TimeModification>\n      <ApplyDRC>false</ApplyDRC>\n      <Normalize>100</Normalize>\n      <CustomEncoderOptions />\n      <Profile>Auto</Profile>\n      <Quality>0.5</Quality>\n      <CreateHintTrack>false</CreateHintTrack>\n    </Settings>\n    <Delay>0</Delay>\n    <SizeBytes>0</SizeBytes>\n    <BitrateMode>CBR</BitrateMode>\n  </Job>\n  <RequiredJobNames />\n  <EnabledJobNames />\n  <Name>job4</Name>\n  <Status>DONE</Status>\n  <Start>2015-04-15T08:05:24.356619+03:00</Start>\n  <End>2015-04-15T08:05:25.8208021+03:00</End>\n</TaggedJob>']},
#'{MUX_JOB}': {'pname': 'BASIC', 'pvalue': 'mkvmux', 'tmpl_list': ['<?xml version="1.0"?>\n<TaggedJob xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n  <EncodingSpeed />\n  <Job xsi:type="MuxJob">\n    <Input>@SRCPATH_VIDEO@</Input>\n    <Output>@SRCPATH@-mux@BITRATE@.mkv</Output>\n    <FilesToDelete />\n    <ContainerTypeString>MKV</ContainerTypeString>\n    <Codec />\n    <NbOfBFrames>0</NbOfBFrames>\n    <NbOfFrames>0</NbOfFrames>\n    <Bitrate>0</Bitrate>\n    <Overhead>4.3</Overhead>\n    <Settings>\n      <MuxedInput />\n      <MuxedOutput>@SRCPATH@-mux@BITRATE@.mkv</MuxedOutput>\n      <VideoInput>@SRCPATH_VIDEO@</VideoInput>\n      <AudioStreams>\n        <MuxStream>\n          <path>@SRCPATH_AUDIO@</path>\n          <delay>0</delay>\n          <bDefaultTrack>false</bDefaultTrack>\n          <bForceTrack>false</bForceTrack>\n          <language />\n          <name />\n        </MuxStream>\n      </AudioStreams>\n      <SubtitleStreams />\n      <Framerate>25.0</Framerate>\n      <ChapterFile />\n      <SplitSize xsi:nil="true" />\n      <DAR xsi:nil="true" />\n      <DeviceType>Standard</DeviceType>\n      <VideoName />\n      <MuxAll>false</MuxAll>\n    </Settings>\n    <MuxType>MKVMERGE</MuxType>\n  </Job>\n  <RequiredJobNames />\n  <EnabledJobNames />\n  <Name>job10</Name>\n  <Status>WAITING</Status>\n  <Start>0001-01-01T00:00:00</Start>\n  <End>0001-01-01T00:00:00</End>\n</TaggedJob>']}}

    # PROCESS {AVS_TEMPLATE}
    avsfname = fname + '.avs'
    detect_pname, encode_tname, content, adj, opts  = getEncodeTokens( '{AVS_TEMPLATE}' )

    if os.path.isfile(avsfname) and not cfg.get_opt( opts, 'AVS_OVERWRITE' ):
        print "AVS exists - do not overwrite"
    else:
        #find non empty AVS names
        extra_avs_sections = filter( len, cfg.get_opt( opts, 'EXTRA_AVS' ) )
        #collect their contents
        extra_avs_contents = map( lambda section: "#EXTRA:%s\n%s"%(section,cfg.config['EXTRA_AVS'].get(section,"")), extra_avs_sections )
        #add to all passes
        content = map(lambda basecontent: '\n'.join([basecontent]+extra_avs_contents), content )

        for idx in range(0,len(content)):
            avsfname = fname + (('.%d'%idx+1) if idx>0 else '' ) + '.avs'
            with open(avsfname,'wb') as f:
                f.write( str_encode(content[idx],'cp1251'))

    # PROCESS {INDEX_JOB}
    detect_pname, encode_tname, content, adj, opts  = getEncodeTokens( '{INDEX_JOB}', xml=True )
    addJobs( content )

    index_only = makeint( cfg.get_opt( opts, 'INDEX_ONLY' ) )
    if index_only>0:
        return

    # PREPARE ALL OTHER JOBS (to not leave unfinished if any error)
    video_tuple = getEncodeTokens( '{VIDEO_PASS}', xml=True, allowEmpty = True )
    audio_tuple = getEncodeTokens( '{AUDIO_ENCODE}', xml=True, allowEmpty = True )
    mux_tuple = getEncodeTokens( '{MUX_JOB}', xml=True )

    postponed = postponed_queue if index_only<0 else None

    detect_pname, encode_tname, content, adj, opts  = video_tuple
    required =[]
    res = addJobs( content, postponed = postponed )
    if len(res):
        keys['@SRCPATH_VIDEO@'] = _get_elem(content[-1].getroot(),'Output').text
        reqiured+=res

    detect_pname, encode_tname, content, adj, opts  = video_tuple
    res = addJobs( content, postponed = postponed )
    if len(res):
        keys['@SRCPATH_AUDIO@'] = _get_elem(content[-1].getroot(),'Output').text
        reqiured+=res

    detect_pname, encode_tname, content, adj, opts  = mux_tuple
    to_del = []
    if keys['@SRCPATH_VIDEO@']!=keys['@SRCPATH@']:
        to_del.append( keys['@SRCPATH_VIDEO@'] )
    if keys['@SRCPATH_AUDIO@']!=keys['@SRCPATH@']:
        to_del.append( keys['@SRCPATH_AUDIO@'] )

    for delpath in to_del:
        for c in content:
             _add_elem( _get_elem(c.getroot(),'FilesToDelete'), 'string', delpath )
    res = addJobs( content, postponed = postponed )

    joblist.save()



if __name__ == '__main__':
    main()


