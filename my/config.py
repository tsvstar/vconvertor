import re, os.path
import util
from util import DBG_info, DBG_trace, DBG_trace2, say

"""
==========================================================
           MODULE TO LOAD CONFIG:

 * ParseArgv()
 * class ConfigLoader(object):
        load complex config with sections and names to config
 * class PatternTemplate(object):
        parse string to tokens by template
 * class Encoding(object):
        ???

 * Auxilary:
    - split_pair()
    - CfgError  exception
    - StrictError exception
=========================================================
"""


# auxilary function:
#  split value to strictly pair (if no separator found, then second value is None)
#  + split both
def split_pair( s, sep, strip = True ):
    a = s.split( sep, 1 )
    if strip:
        a = map( lambda x: x.strip(), a )
    if len(a) < 2 :
        a += [None]
    return a

# Prepare windows taken ARGV.
#    >> script "drive:\path\to\dir\" key
#  incorrectly treated as single arg 'drive:\path\to\dir" key'

re_quote = re.compile('\"')
re_argv = re.compile('[ \"]')

# RETURN: pre, main, post
def _re_find( re, s ):
    m = re.search(s)
    if not m:
        return s, '', ''
    return s[:m.start(0)], m.group(0), s[m.end(0):]


# MANUAL PARSING OF ARGV
# ("Far Manager" give dir as "path\to\dir\" and in this case all argv after that parsed incorrectly)
def prepareARGV( argv ):

    # get cmdline unparsed
    import ctypes
    func = ctypes.windll.kernel32.GetCommandLineA
    func.restype = ctypes.c_char_p
    cmd = ctypes.windll.kernel32.GetCommandLineA()

    scriptpath = argv[0].replace('\\\\','\\') + '"'
    cmd = cmd.split(scriptpath,1)[1]    # cut off [python, mainscript]
    cmd = util.str_decode(cmd)
    DBG_trace("COMMAND_LINE = %s", [cmd])

    argv = [ argv[0] ]
    quoteFlag = False
    while len(cmd):

        if not quoteFlag:
            # Regular processing (first or after space)
            cmd = cmd.strip()
            pre, sym, cmd = _re_find( re_argv, cmd )
            argv.append(pre)

            if sym!='"':        # EOL or space - regular arg
                continue

            pre, sym, cmd = _re_find( re_quote, cmd )  # lookup closing quote
            argv[-1] += ( pre if pre!='' else '"' )     # add quoted value ("" means just ")
            quoteFlag = True
        else:
            # Continue to process after quoted value (quoteFlag==True)
            pre, sym, cmd = _re_find( re_argv, cmd )

            argv[-1]+=pre

            if sym!='"':            # EOL or space - finish this arg
                quoteFlag = False
                continue

            pre, sym, cmd = _re_find( re_quote, cmd )  # lookup closing quote
            argv[-1] += ( pre if pre!='' else '"' )     # add quoted value ("" means just ")

    argv = filter( len, argv )
    DBG_info("argv: %s", repr(argv))
    return argv


# Simple argument parser with unknown list of options (all --key are treated as option,
#       all other as arguments).
# ARGUMENTS:
#       argv - source list of sys.argv
#       optlist - dict of specific(accumulative) options.
#                   optlist[OPTNAME] = default_value (0 or [])
# RETURN VALUE:
#       ( options_dict, arguments_list )
def ParseArgv( argv, optdict = {} ):
    optdict = dict( map(lambda i: [i[0].lower(),i[1]],optdict.iteritems()) )

    keys = dict(optdict)    # found --options
    to_process = []         # not matched to -- arguments
    for v in argv:
        v1 = v.lstrip()

        if v1.startswith("--"):                         # a) --option
            v1 = v1[2:]
            v1lower = v1.lower()
            if  v1lower in optdict:                     # a1) accumulative --options
                if isinstance(optdict[v1lower],int):
                    keys[v1lower] += 1
                else:
                    keys[v1lower].append(v1lower)
            else:
                v1, v2 = split_pair( v1, '=' )   # a2) simple --options
                keys[v1.upper()] = v2

        else:                                           # b) argument
            if v.endswith('"'):
                v = v[:-1]
            to_process.append(v)
    DBG_trace("ParseArgv(): keys=%s, to_process=%s", [repr(keys), repr(to_process)] )
    return keys, to_process



"""
====================================
            ERRORS
====================================
"""
class CfgError(Exception):
    def __init__( self, lineno, message ):
        super(CfgError,self).__init__( message )
        self.lineno = lineno

class StrictError(Exception):
    def __init__( self, message = None ):
        super(StrictError,self).__init__( message )

"""
====================================
        AUXILARY CLASS
  - contain encoding template info
====================================
"""

class EncTemplate(object):
    def __init__(self ):
        self.content = []
        self.adjustments = util.MyOrderedDict()
        self.path = []

    def __str__(self):
        return "<%s at %x: [%s]: content=%d>" % ( type(self), id(self), '->'.join(self.path), len(self.content) )
    def __repr__(self):
        return self.__str__()



"""
===============================================================
            MAIN CLASS TO LOAD CONFIG

Able to process config with different kind of sections. Sections
could have name.

------------------------------
[OPTION_SECTION]
OPTION1=value1      #comment
OPTION2{spec}=value2.1
#OPTION2{spec2}=value2.2
OPTION2{spec3}=value2.3

[TEXT_SECTION] = name1
something here

[TEXT_SECTION] = name2
and something another more

[PATTERN_SECTION]
PATTERNNAME1 => PATTERN1
PATTERNNAME2 => PATTERN2
------------------------------

* How to use:
    cfg = ConfigLoader()
    cfg.opt = {...}
    cfg.sections = {...}


===============================================================
"""

class ConfigLoader(object):

    ### Ctor ###
    """ CTOR """
    def __init__( self, isDebug = False ):
        self.opt = {}           # DEFINITION OF VALID OPTIONS:      opt[optionName] = [ processor, default_value ]
        self.sections = {}      # DEFINITION OF VALID SECTIONS:     sections[sectype] = [ datatype, isname_required, proccessor]
        self.pattern_template = {}  # HOW TO PARSE PATTERN BY TYPE: pattern_template[section_type] = template
        self.templates = {}     # TEMPLATES PATTERN:                templates[templ_name] = loaded_template or None(exists but not loaded yet)

        self.fname = ''
        self.config = {}        # RESULT:                           config[sectiontype][sectionname] = content (dict or plain str)

        self.isDebug = isDebug


    """ *********** SECTION CALLBACK PROCESSORS ********************

          callback( self, sec_type, sec_name, line )
            sec_type - type of section                    ([SECTION])
            sec_name - name of section. None if not given ([SECTION] = name )
            line     - current line to process

          NOTE: called line by line

       ************************************************************* """


    """ * Process option section:
          format:
             a) OPTION=VALUE    # comment
                --> self.config[sec_type][sec_name][OPTION] = VALUE

             b) OPTION{extra}=VALUE    # comment
                --> self.config[sec_type][sec_name][OPTION] = {OPTIONAL_EXTRA: VALUE,.. }
    """
    def load_opt_processor( self, sec_type, sec_name, line, checkOpt = True, optNameUpper = True ):
        line = line.split('#',1)[0]     # cutoff comments
        name, value = split_pair( line, '=', strip = True  )
        if value is None:
            if name=='':
                return
            raise CfgError( -1, "Malformed line (no '=' sign)")

        name = name.rstrip()
        if name.startswith('@') and name.endswith('@'):
            name, subname = '@', name.upper()+'}'       #   @name@ -> ['@']['@name@']
        else:
            name, subname = split_pair(name,'{')        #   name{key} -> [name][key]
            if optNameUpper:
                name = name.upper()
        if checkOpt and name not in self.opt:
            raise CfgError( -1, "Unknown option %s" % name )
        ##print "%s|%s" % (name, subname)

        CUR_SECTION = self.config[sec_type][sec_name]       # reference (because mutable type)

        if subname is None:
            # there is no specification -> simple value
            keyexist = ( name in CUR_SECTION )
            CUR_SECTION[name] = value
        else:
            # specification is given -> remember in dictionary
            cur_value = CUR_SECTION.setdefault( name, {} )
            if ( not isinstance( CUR_SECTION[name], dict ) ):
                CUR_SECTION[name] = { None: cur_value }

            subname = subname[:-1]                      # cutoff tail '}'
            keyexist = ( subname in CUR_SECTION[name] )
            CUR_SECTION[name][subname] = value

            name = "%s{%s}" % ( name, subname )         # make human readable name

        if keyexist:
            raise CfgError( -1, "{Warning} Option %s is defined twice" % name )

    def load_opttmpl_processor( self, sec_type, sec_name, line ):
        self.load_opt_processor( sec_type, sec_name, line, checkOpt = False, optNameUpper = False )

    """ * Process plain text section.
          format:
            plain text
            --> self.config[sec_type][sec_name] = list_of_lines
    """
    def load_text_processor( self, sec_type, sec_name, line ):
        self.config[sec_type][sec_name] += [line]

    """ * Process pattern section.
          format:
                PATTERNNAME => VALUE    # comment
                --> self.config[sec_type][sec_name] = VALUE
    """
    def load_pattern_processor( self, sec_type, sec_name, line ):
        line = line.split('#',1)[0]                 # cutoff comments
        name, value = split_pair( line, '=>', strip = True )
        ##print 'PROCESS ', name, '=', value, '=', line.strip()		##DEBUG
        if value is None:
            if name=='':
                return
            raise CfgError( -1, "Malformed line (no '=>' sign)")

        CUR_SECTION = self.config[sec_type][sec_name]       # reference (because mutable type)
        if name in CUR_SECTION:
            CUR_SECTION[name] = value
            raise CfgError( -1, "{Warning} Pattern %s is defined twice" % name )
        CUR_SECTION[name] = value


    """ *********** INTERNALL AUXILARY FUNCTIONS ********************
       ************************************************************* """

    # process error ( +suppres dupes +raise StrictError if needed )
    def _print_cfg_error( self, e ):
        if e.lineno not in self.cfg_errors:
            say( "%s:%d - %s", [ self.fname, e.lineno, str(e) ] )
            self.cfg_errors.add( e.lineno )
        if ( self.strictError or
             util.makebool( self.config.setdefault('',{}).setdefault(None,{}).get('STRICT',0) ) ):
            raise StrictError()


    # PROCESS SECTION
    #     sec_type   - section type
    #     sec_name   - section name (optional. none if not given)
    #     content    - list of lines
    #     lineno     - lineno of section first line (declaration [SECTION])
    def _process_section( self, sec_type, sec_name, content, lineno ):

        data_type, isname_required, processor = self.sections[sec_type]

        DBG_trace( "ConfigLoader._process_section (%s|%s): %s" , (sec_type,sec_name, str(self.sections[sec_type]) ) )

        if sec_name =='' and isname_required:
            raise CfgError ( lineno, "Section %s have no name - skip it" % sec_type )

        ###print "lineno=%d\n%s" % (lineno,content)			##DEBUG

        # exclude header
        if sec_type!='':
            lineno -= 1
            content = content[1:]

        # prepare
        self.config.setdefault( sec_type, dict() )

        if sec_name in self.config[sec_type]:
            # name exists - only empty allowed to append
            if sec_name!='' and sec_name is not None:
                raise CfgError ( lineno, "Section %s with name '%s' is already defined - skip it" % ( sec_type, sec_name ) )
        else:
            # name not exists - create section
            self.config[sec_type][sec_name] = dict() if (data_type == 'dict') else list()

        # Main cycle
        for l in content:
            try:
                ##print lineno, '===', l.strip()			##DEBUG
                processor( self, sec_type, sec_name, l )
            except CfgError as e:
                e.lineno = lineno
                self._print_cfg_error(  e )
            finally:
                lineno += 1


    """ ****************       OPERATIONS       ********************
       ************************************************************* """

    """ --- existed options from optdict2 replace options in optdict1 --- """
    @staticmethod
    def replace_opt( optdict1, optdict2 ):
        for k,v in optdict2.iteritems():
            if isinstance(v,dict):
                if optdict1.get(k,'')=='':
                    optdict1[k] ={}
                optdict1[k].update(v)
            elif isinstance(v,basestring):
                if len(v) and v[0] in ['+','|']:
                    optdict1[k] +=v
                else:
                    optdict1[k] = v
            elif v is not None:
                optdict1[k] = v
        return optdict1

    """ --- getter: get value of option "optname" from dictionary "optdic" ---"""
    def get_opt( self, optdict, optname, subname=None ):
        if optname not in self.opt:
            say("INTERNAL FAILURE: unknown option %s", optname )
            return None
        if subname is None:
            src_value = optdict.get( optname, None )
        else:
            src_value = optdict.get( optname, {} ).get(subname, None)

        rv = self.opt[optname]( '' if src_value is None else src_value )
        DBG_trace( "__getopt(%s,%s) = %s (%s)", (optname, subname, src_value, str(rv) ) )
        return rv



    """ ****************       MAIN ENTRY       ********************

         Load config (based on "self" config templates) to self.config
            fname       = filename to get (if not "content" given)
            strictError = if True, then any config missconsistence raise StrictError()
            content     = text content to parse

       ************************************************************* """

    def load_config( self, fname, strictError = False, content = None ):
        self.fname = fname
        self.cfg_errors = set()
        self.strictError = strictError

        DBG_trace( "ConfigLoader.load_config(%s)", fname )

        if content is None:
            try:
                with open(fname,'rt') as f:
                    content = f.readlines()
            except Exception as e:
                say( "Error: can't load '%s' config", fname )
                return

        section_re = re.compile("^\[([A-Z\_]+)\] *(\= *([A-Za-z0-9\_]+))?")

        lineno = 1
        prev = [ '', None, [], 1 ]        # [0section_type, 1section_name, 2content, 3startline]
        for l in content:
            try:
                if len( l.strip() )==0:                 # skip empty lines
                    continue
                ##print lineno, l.strip()				##DEBUG

                if l[0]!='[':                           # if not section header - just continue to accumulate lines
                    continue

                # this is the section header - process finished and reset control array to new sections
                m = section_re.match(l)
                if m is None:
                    raise CfgError( lineno, "Malformed section header" )
                elif m.group(1) not in self.sections.keys():
                    raise CfgError( lineno, "Unknown section type %s"%m.group(1) )
                self._process_section( *prev )
                DBG_trace( "detect section at %d: %s|%s", ( lineno, m.group(1),m.group(3) ) )
                prev = [ m.group(1), m.group(3), [], lineno + 2 ]		# +1 to compensate [section line], +1 because numeration from 1

            except CfgError as e:
                self._print_cfg_error( e )
                say( l.strip() )
            finally:                                    # on each line: remember content and increase lineno
                prev[2].append(l)
                lineno += 1

        ##print "WRITE ", lineno, len(prev[2]), l.strip()		##DEBUG
        try:
            # process final section
            self._process_section( *prev )
        except CfgError as e:
            self._print_cfg_error( e )


    """ **************** TEMPLATE (FILE) PROCESSING  ***************
            load to cache templates (files).
            special value '','*', 'copy' are exists

            CONFIG:
                self.tpath - template directory
       ************************************************************* """

    """
        PURPOSE: get template "tname"
                (load template from templatedir + cache it )
                    If fatal = True - then error on load cause Exception)
        RETURN: content of template
    """
    def _load_template( self, tname, fatal ):
        ##print "load>",self.tpath, tname    #@tsv
        out = util.unicformat( "ConfigLoader._load_template( %s, %s )", [self.tpath,tname] )
        # found in cache
        if tname in self.templates:
            DBG_trace( u"%s - FROM CACHE (%s)", [ out, type(self.templates[tname]) ] )
            return self.templates[tname]
        DBG_trace(out)

        self.templates[tname] = None
        # empty value (no template)
        if tname in [None,'','*']:
            return None

        if tname in ['copy']:
            return ''

        # load file
        try:
            ##print "load>",self.tpath, tname    #@tsv
            fname = os.path.join( self.tpath, tname )
            ##print "+++",fname                   #@tsv
            with open( fname, 'r') as f:
                self.templates[tname] = f.read()
            DBG_trace( "LOADED %s ", fname )
        except Exception as e:
            DBG_trace( "FAIL TO LOAD %s - %s", [fname,str(e)] )
            if fatal:
                raise
        return self.templates[tname]

    """
        PURPOSE: load one or multi-pass template
                 (tname or [tname.1pass, tname.2pass, ...] )
        RETURN: ordered list of templates content.
                    None on error(not found) -- if fatal = False
                    raise Exception          -- if fatal = True
    """
    def load_multi_templates( self, tname, tmpl, fatal = False, aliases = {} ):
        DBG_trace("load_multi_templates(%s) %s / aliases:%s",[ tname, tmpl, aliases.keys() ])
        tmpl.path.append(tname)

        if tname in [None,'','*']:
            return tmpl
        #if tname in ['copy']:   #??? WHAT IS THIS ???
        #    return ['']

        if tname in aliases:
            talias = aliases[tname]
            tname_new, tadj = split_pair(talias,'{')
            if tadj is not None:
                if not tadj.endswith('}'):
                    raise StrictError("No closing '}' for template alias '%s'"%tname_new)
                adj = filter( len, map( util.vstrip, (tadj[:-1]).split(',') ) )
                for a in adj:
                    aname, avalue = split_pair(a,'=')
                    tmpl.adjustments.setdefault( aname, avalue )        # top templates adjustments have priority
            return self.load_multi_templates(tname_new, tmpl, fatal, aliases )

        while True:
            v = self._load_template('%s.%dpass' % (tname,len(tmpl.content)+1), fatal = False )
            if v is None:
                break
            tmpl.content.append( v )

        if len(tmpl.content):
            return tmpl

        try:
            v = self._load_template( tname, fatal = fatal )
        except Exception as e:
            raise StrictError( util.unicformat("Fail to load template %s%s:%s", [ tname, " (%s)"%('->'.join(tmpl.path)) if len(tmpl.path)>1 else '', str(e) ] ) )
        if v is None:
            #raise StrictError("No template found '%s'"%loa)
            return None
        tmpl.content = [v]
        return tmpl

"""
===============================================================
            PATTERN PARSING FUNCTION

PURPOSE: Easy parse string to tokens.
         * Parsed string must exactly match template.
         * Token value can't contain separator which is placed right after it

EXAMPLE:
    t = PatternTemplate( 'DETECT', '{CONTAINER}|VIDEO|{WIDTH}x{HEIGHT}@{FPS}|{V_BRATE} {V_BRATE_TYPE}'
    d = t.parse_pattern('mp4|VIDEO|320x250@25.3|33.15 Mbps here')
    --> d = { 'CONTAINER':'mp4', 'WIDTH': '320', 'HEIGHT':'250', 'FPS':'25.3', 'V_BRATE':'33.15', 'VBRATE_TYPE': 'Mbps here' }


===============================================================
"""

class PatternTemplate(object):
    isDebug = False

    # Constructor:
    #   section - name of section (only to printable info)
    #   template - name of parsed token
    def __init__( self, section, template ):
        self.section = section
        self.ar_sep, self.ar_tokens, self.ar_optional = self._compile_pattern_template(template)
        DBG_trace2("section %s", section )
        DBG_trace2("ar_sep %s", [self.ar_sep] )
        DBG_trace2("ar_tokens %s", [self.ar_tokens] )
        DBG_trace2("ar_optional %s", [self.ar_optional] )

    # auxilary: cut value till sep
    # RETURN VALUE: [ 0value, 1string_after_value, 2pos_where_value_found ]
    @staticmethod
    def _check_sep( sep, s ):
        if len(sep)<=0:          # no separator
            return s, None, 0
        if s is None:           # no string left to parse
            return None, s, 0
        foundat = s.find(sep)
        if foundat<0:
            return s, None, foundat
        value = s[:foundat].strip()
        return value, s[foundat+len(sep):], foundat

    # auxilary: find tokens and
    # RETURN VALUE: [ list_of_separators, list_of_tokennames]
    @staticmethod
    def _compile_pattern_template( template ):
        token = re.compile("\{\??[A-Za-z0-9_]+\}")

        #sanity check - are separators exists between all tokens?
        ar_sep = token.split( template )
        ar_tokens = token.findall( template )
        ar_optional = set()
        for idx in range( 1, max( len(ar_tokens), len(ar_sep)-1 ) ):
            if ar_sep[idx]=='':
                raise Exception("Malformed template given: no separator before %s token" % ar_tokens[idx])
            if ar_tokens[idx].startswith('{?'):
                ar_tokens[idx] = '{%s' % ar_tokens[idx][2:]
                ar_optional.add(idx)

        return ar_sep, ar_tokens,ar_optional

    # auxilary: DEBUG???
    @staticmethod
    def PrintParsedList( parsedlist ):
        rv = '\n'
        for pname,pval in parsedlist.items():
            pval1 = pval.copy()
            del pval1['_']
            rv += "%s = %s\n%s\n" % ( pname, pval['_'], str(pval1) )
        return rv


    """ main function:
            config      - string to parse
            strictError - if True, then raise exception on error
            silent      - if True, do not produce any message
            allowOptional - if True, then optional tokens could be missed in input string

    """
    def parse_pattern( self, config, strictError = False, silent = False, allowOptional = True ):

        # parse pattern
        parsed = {}
        #print config
        DBG_trace("parse_pattern()")
        for pname in config:
            # store printable value
            parsed.setdefault( pname, {} )['_'] = config[pname]

            try:
                # check/cut first separator
                s = config[pname]
                if len(self.ar_sep[0])!=0:
                    if not s.startswith( self.ar_sep[0] ):
                        raise CfgError ( 0, "start not from expected string('%s')" % self.ar_sep[0] )
                    s = s[ len(self.ar_sep[0]): ]

                # parse tokens
                DBG_trace( "  pname=%s, STR=%s", [ pname, config[pname] ] )
                skip = set()
                for idx in range(0,len(self.ar_tokens)):
                    if idx in skip:
                        value = ''
                        DBG_trace2( "    SKIP_OPTIONAL")
                    else:
                        value, s_new, foundat = self._check_sep( self.ar_sep[idx+1], s )

                        # check next tokens for next optionality. if yes and found separator after it earlier then current, then  - skip such
                        if allowOptional:
                            idx1 = idx+1
                            if idx1 in self.ar_optional:
                                DBG_trace2( "    CHECK_OPTIONALITY AFTER: ... SEP=%s; VALUE=%s; S=%s; FOUND=%d; TO=%s", ( self.ar_sep[idx+1], value,s_new,foundat,self.ar_tokens[idx]) )
                            while idx1<len(self.ar_tokens):
                                if idx1 not in self.ar_optional:
                                    break
                                value1, s_new1, foundat1 = self._check_sep( self.ar_sep[idx1+1], s )
                                DBG_trace2( "    CHECK_OPTIONAL: %s... SEP=%s; VALUE=%s; S=%s; FOUND=%d; TO=%s", ( (idx1-idx),self.ar_sep[idx1+1], value1,s_new1,foundat1,self.ar_tokens[idx1]) )
                                if foundat1>=0 and foundat1<foundat:
                                    for x in range(idx+1,idx1+1): skip.add(x)
                                    value, s_new, foundat = value1, s_new1, foundat1
                                    DBG_trace2( "    MATCH_OPTIONAL %s", [skip])
                                idx1 += 1

                        s = s_new

                    if value in ['*','?']:
                        value = None
                    DBG_trace2( "    SEP=%s; VALUE=%s; S=%s; FOUND=%d; TO=%s", (self.ar_sep[idx+1], value,s,foundat,self.ar_tokens[idx]) )
                    parsed[pname][self.ar_tokens[idx]] = value
                    if strictError and foundat<0:
                        raise CfgError ( 0, "is truncated at token %s\nProbably separator or value missed." % self.ar_tokens[idx] )
            except CfgError as e:
                sayfunc = say if not silent else DBG_trace
                e = str(e).split('\n')
                sayfunc( "Pattern '%s'%s %s: %s", ( pname, (' (%s category)' % self.section if self.section is not None else ''), e[0], config[pname] ) )
                if len(e)>1:
                    sayfunc( '%s', '\n'.join(e[1:]) )
                if strictError:
                    raise StrictError()
                del parsed[pname]
                continue
            DBG_trace( "  %s--->%s", ( pname, str(parsed[pname]) ) )
        return parsed



"""
===============================================================
            LOOKING UP ENCODING

Helper class, which scans given pattern from given form up to
more common to find one with defined value

EXAMPLE for 'sony:720' and suffix '.old':
    [sony:720.old] -> sony:720 -> [sony.old] -> [sony]

===============================================================
"""
class Encoding(object):

    # CONSTRUCTOR
    #
    #   p_encode - dict of patterns  ( [patternname] = "value{optional_adj}" )
    #   cfg      - ConfigLoader() object to load found templates
    #   tmpl_aliases - dict of aliases
    #   suffix   - system suffix     ( example: old, new, '')
    #   verbose  - unused
    def __init__( self, p_encode, cfg, tmpl_aliases, suffix, verbose = False ):
        self.path = []
        self.p_encode = p_encode
        self.cfg = cfg
        self.tmpl_aliases = tmpl_aliases if isinstance(tmpl_aliases,dict) else {}
        self.suffix_list = [ '.'+suffix, '' ] if len(suffix) else ['']
        ##self.verbose = verbose

    # FIND VALID TOKEN
    #
    # ARGUMENTS:
    #   pname        = name of encoding pattern         (example - sony:480,..)
    #   p_token_name = name of token.just for message   (example - INDEX_JOB)
    #   isPositiveInteger = True if value should be exactly integer >0
    #
    # RETURN VALUE:
    #   [pname_real, pvalue, adjustments, template_content]
    #   - pname_real  = name of matched pattern (None - nothing found)
    #   - pvalue      = full matched value
    #   - adjustments = None or LIST of pairs [ name, value{could be None}]
    #   - template_content = LIST of preloaded content of corresponend templates (could be several for multipass)

    # NOTE:
    #   1) Adjustment catched separatelly up to found main value
    #       So we can have values like "?{adj1=val1,adj2}".
    def get_encode_pattern( self, pname1, p_token_name, isPositiveInteger ):

        rv_adjustment = None
        rv_defaultname = None

        DBG_trace("get_encode_pattern(%s,%s)", [pname1,p_token_name])
        DBG_trace2(" ENTER>rv_adj\t%s", rv_adjustment )

        lst1 = pname1.split(':')
        ##print lst1     #@tsv
        for idx in range(0,len(lst1)):      # 1. outer loop: iterate up to root pattern ( sony:480:abc -> sony:480 -> sony )
            ##print lst1[:-idx]         #@tsv
            pname2 = pname1 if not idx else ':'.join(lst1[:-idx])

            for suffix in self.suffix_list: # 2. inner loop: try with and without suffix

                    pname3 = pname2 + suffix

                    DBG_trace("  idx=%d\tpname2=%s\tpname3=%s\tv=%s\trvadj=%s", (idx,pname2,pname3,self.p_encode.get(pname3,{}).get(p_token_name,'??'),rv_adjustment) )

                    if ( pname3 not in self.p_encode ): # if no such pattern found

                        if ( idx > 0 ):                 # a) truncated name - that is optional try
                            self.path.append('[?]'+pname3)
                            continue
                        if ( len(suffix) ):             # b) suffix is optional try
                            self.path.append('[?]'+pname3)
                            continue
                        """
                        if ( isServiceClass and len(suffix) ):  # b) service_pattern with suffix - also optional try
                            continue
                        """
                        self.path.append(pname3)        # c) all other cases - are required
                        raise StrictError("No '%s' encoding pattern defined" % pname3 )


                    self.path.append(pname3)

                    value = self.p_encode[pname3].get(p_token_name,None)          # get value and split with adjustment
                    if value is None:
                        continue
                    value, adj = split_pair( value, '{' )
                    DBG_trace2('    value=%s\tadj=%s',(value,adj))         #@tsv
                    if adj is not None and adj[-1]!='}':
                        raise StrictError("No enclosing bracket for token '%s' at pattern '%s': %s" %
                                             ( p_token_name, pname3, self.p_encode[pname3] ) )

                    if isPositiveInteger:               # specific processing {BITRATE} token. this is integer
                        brate = util.makeint(value)
                        if brate <= 0:
                            continue
                        return ( pname3, brate, None, EncTemplate() )

                                                                # do not replace already getted adjustment
                    if ( (rv_adjustment is None) and (adj is not None) ):
                        adj = map( lambda s: split_pair(s,'='), adj[:-1].split(',') )
                        rv_adjustment = filter( lambda a: len(a[0]), adj )

                    template_name = value
                    if template_name == '' and rv_defaultname is not None:
                        rv_defaultname = pname3

                    DBG_trace2("     rv_adj=%s", rv_adjustment )       #@tsv
                    if template_name in [None,'*','?']:
                        continue

                    tcontent_list = self.cfg.load_multi_templates( template_name, EncTemplate(), aliases = self.tmpl_aliases )
                    if tcontent_list is None:
                        raise StrictError("Fail to load template '%s' for token '%s' at pattern '%s'" % ( template_name, p_token_name, pname3 ))
                    DBG_trace("    RETURN: pname3=%s,\tvalue=%s\trv_adjustment=%s,\ttconent_list\n", [ pname3, value, rv_adjustment] )  #@tsv
                    return pname3, value, rv_adjustment, tcontent_list

        DBG_trace("    RETURN DEFAULT: rv_defaultname=%s,\t''\trv_adjustment=%s,\t[]\n", [ rv_defaultname, rv_adjustment] )  #@tsv
        return rv_defaultname, '', rv_adjustment, EncTemplate()


    @staticmethod
    def getAdjPrintable( adjList ):
        if isinstance(adjList,dict):
            adj = adjList.items()
        elif isinstance(adjList,list):
            adj = adjList
        else:
            return ''
        ar_joined_pairs = map(lambda a: a[0] if a[1] is None else '='.join(a), adj)
        return "{%s}" % ( ', '.join(ar_joined_pairs) )
