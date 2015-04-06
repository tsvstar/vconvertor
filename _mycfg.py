import re, os.path

# util function
def split_pair( s, sep, strip = True ):
    a = s.split( sep, 1 )
    if strip:
        a = map( lambda x: x.strip(), a )
    if len(a) < 2 :
        a += [None]
    return a


class CfgError(Exception):
    def __init__( self, lineno, message ):
        super(CfgError,self).__init__( message )
        self.lineno = lineno

class StrictError(Exception):
    def __init__( self, message = 'Strict Error' ):
        super(StrictError,self).__init__( message )

class ConfigLoader(object):

    ### Ctor ###
    def __init__( self, isDebug = False ):
        self.opt = {}           # DEFINITION OF VALID OPTIONS: opt[optionName] = [ processor, default_value ]
        self.sections = {}      # DEFINITION OF VALID SECTIONS: sections[sectype] = [ datatype, isname_required, proccessor]
        self.pattern_template = {}  # HOW TO PARSE PATTERN BY TYPE: pattern_template[section_type] = template
        self.templates = {}     # TEMPLATES PATTERN: templates[template_name] = loaded template or None if it exists but not loaded yet

        self.fname = ''
        self.config = {}        # config[sectiontype][sectionname] = content (dict or plain str)

        self.isDebug = isDebug

    ### Processors ###
    def load_opt_processor( self, sec_type, sec_name, line ):
        line = line.split('#',1)[0]     # cutoff comments
        name, value = split_pair( line, '=', strip = True  )
        if value is None:
            if name=='':
                return
            raise CfgError( -1, "Malformed line (no '=' sign)")

        name, subname = split_pair(name,'{')
        name = name.upper()
        if name not in self.opt:
            raise CfgError( -1, "Unknown option %s" % name )

        #print "%s|%s" % (name, subname)

        if subname is None:
            keyexist = ( name in self.config[sec_type][sec_name] )
            self.config[sec_type][sec_name][name] = value
        else:
            if ( name not in self.config[sec_type][sec_name]
                 or not isinstance( self.config[sec_type][sec_name][name], dict ) ):
                self.config[sec_type][sec_name][name] = {}

            subname = subname[:-1]
            keyexist = ( subname in self.config[sec_type][sec_name][name] )
            self.config[sec_type][sec_name][name][subname] = value

            name = "%s{%s}" % ( name, subname )

        if keyexist:
            raise CfgError( -1, "{Warning} Option %s is defined twice" % name )

    def load_text_processor( self, sec_type, sec_name, line ):
        self.config[sec_type][sec_name] += [line]

    def load_pattern_processor( self, sec_type, sec_name, line ):
        line = line.split('#',1)[0]     # cutoff comments
        name, value = split_pair( line, '=>', strip = True )
        if value is None:
            if name=='':
                return
            raise CfgError( -1, "Malformed line (no '=>' sign)")

        if name in self.config[sec_type][sec_name]:
            self.config[sec_type][sec_name][name] = value
            raise CfgError( -1, "{Warning} Pattern %s is defined twice" % name )
        self.config[sec_type][sec_name][name] = value

    ### Aux function ###
    def print_cfg_error( self, e ):
        if e.lineno not in self.cfg_errors:
            print "%s:%d - %s" % ( self.fname, e.lineno, str(e) )
            self.cfg_errors.add( e.lineno )
        if self.strictError:
            raise StrictError()

    ### Aux function ###
    def _write_section( self, lineno, sec_type, sec_name, content ):

        data_type, isname_required, processor = self.sections[sec_type]

        if self.isDebug:
            print "Write section (%s|%s): %s" % (sec_type,sec_name, str(self.sections[sec_type]) )

        if sec_name =='' and isname_required:
            raise CfgError ( lineno, "Section %s have no name - skip it" % sec_type )

        # exclude header
        if sec_type!='':
            lineno -= 1
            content = content[1:]

        # prepare
        if sec_type not in self.config:
            self.config[sec_type] = dict()

        if sec_name in self.config[sec_type]:
            # name exists - only empty allowed to append
            if sec_name!='' and sec_name is not None:
                raise CfgError ( lineno, "Section %s with name '%s' is already defined - skip it" % ( sec_type, sec_name ) )
        else:
            # name not exists - create section
            if data_type == 'dict':
                self.config[sec_type][sec_name] = dict()
            else:
                self.config[sec_type][sec_name] = []


        # Main cycle
        for l in content[1:]:
            try:
                processor( self, sec_type, sec_name, l )
            except CfgError as e:
                e.lineno = lineno
                self.print_cfg_error(  e )
            finally:
                lineno += 1

    # existed options from optdict2 replace options in optdict1
    @staticmethod
    def replace_opt( optdict1, optdict2 ):
        for k,v in optdict2.iteritems():
            if v is not None:
                optdict1[k] = v

    ### MAIN ENTRY ###
    def load_config( self, fname, strictError = False, content = None ):
        self.fname = fname
        self.cfg_errors = set()
        self.strictError = strictError

        if self.isDebug:
            print "load_config(%s)" % fname

        if content is None:
            try:
                with open(fname,'rt') as f:
                    content = f.readlines()
            except Exception as e:
                print "Error: can't load '%s' config" % fname
                return

        section_re = re.compile("^\[([A-Z\_]+)\] *(\= *([A-Za-z0-9\_]+))?")

        lineno = 1
        prev = [ '', None, [] ]        # [section_type, section_name, content]
        for l in content:
            try:
                if len( l.strip() )==0:
                    continue
                if l[0]=='[':
                    m = section_re.match(l)
                    if m is None:
                        raise CfgError( lineno, "Malformed section header" )
                    elif m.group(1) not in self.sections.keys():
                        raise CfgError( lineno, "Unknown section type %s"%m.group(1) )
                    self._write_section( lineno - len(prev), *prev )
                    if self.isDebug:
                        print "detect section at %d: %s|%s" % ( lineno, m.group(1),m.group(3) )
                    prev = [ m.group(1), m.group(3), [] ]
            except CfgError as e:
                self.print_cfg_error( e )
                print l.strip()
            finally:
                prev[2].append(l)
                lineno += 1
        try:
            self._write_section( lineno - len(prev), *prev )
        except CfgError as e:
            self.print_cfg_error( e )

    ### TEMPLATE LOAD ###
    def load_template( self, tpath, tname, fatal = True ):
        if tname in self.templates:
            return self.templates[tname]
        self.templates[tname] = None
        if tname in [None,'','*']:
            return None

        try:
            fname = os.path.join( tpath, tname )
            with open( fname, 'r') as f:
                self.templates[tname] = f.read()
        except:
            if fatal:
                raise
        return self.templates[tname]


        print "load_template( %s )" % fname

########## PATTERN PARSING FUNCTION ##############

class PatternTemplate(object):
    isDebug = False

    def __init__( self, template ):
        self.ar_sep, self.ar_tokens = self._compile_pattern_template(template)

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
        if value in ['*','?']:
            value = None
        return value, s[foundat+len(sep):], foundat

    @staticmethod
    def _compile_pattern_template( template ):
        token = re.compile("\{[A-Za-z0-9_]+\}")

        #sanity check - are separators exists between all tokens?
        ar_sep = token.split( template )
        ar_tokens = token.findall( template )
        for idx in range( 1, max( len(ar_tokens), len(ar_sep)-1 ) ):
            if ar_sep[idx]=='':
                raise Exception("Malformed template given: no separator before %s token" % ar_tokens[idx])

        return ar_sep, ar_tokens


    def parse_pattern( self, config, strictError = False, silent = False ):

        # parse pattern
        parsed = {}
        #print config
        for pname in config:
            # store printable value
            parsed.setdefault( pname, {} )['_'] = config[pname]

            try:
                # check/cut first separator
                s = config[pname]
                if len(self.ar_sep[0])!=0:
                    if not s.startswith( self.ar_sep[0] ):
                        raise CfgError ( 0, "Pattern start not from expected string('%s')"%self.ar_sep[0])
                    s = s[ len(self.ar_sep[0]): ]

                # parse tokens
                if self.isDebug: print "STR=%s"%config[pname]
                for idx in range(0,len(self.ar_tokens)):
                    value, s, foundat = self._check_sep( self.ar_sep[idx+1], s )
                    if self.isDebug: print "SEP=%s; VALUE=%s; S=%s; FOUND=%d; TO=%s" % (self.ar_sep[idx+1], value,s,foundat,self.ar_tokens[idx])
                    parsed[pname][self.ar_tokens[idx]] = value
                    if strictError and foundat<0:
                        raise CfgError ( 0, "Pattern is truncated at token %s"%self.ar_tokens[idx])
            except CfgError as e:
                if not silent:
                    print "%s: %s" % ( str(e), config[pname] )
                if strictError:
                    raise StrictError()
                del parsed[pname]
                continue
        return parsed


    # TODO:optimized cycle - mostly separators are '|'
    """
    def parse_pattern_optimized( config, compiled_template, strictError = False ):
        ar_parse = []
        for t in template.split('|'):
            ar_parse.append( [ token.split(t), token.findall(t) ] )

        # parse pattern
        parsed = {}
        for key in config:
            parsed[key]['_'] = config[key]      # store printable value
            p = config[key].split('|')

            for idx in range(0,len(p)):
                sep, tok = ar_parse[idx]
                if len(tok)<2 and sep[0]=='' and sep[-1]=='':
                    #simple case - no extra separator inside
                    parsed[tok[0]] = p[idx].strip()
                    continue

                # complex case - some extra separator inside
                s = p[idx]
                value, s = _check_sep( sep[0], s )
                for idx_tok in range( 1, len(tok) )

            # add absent tokens
            for t in ar_tokens:
                if t not in parsed[key]:
                    parsed[key][t]=None
        """

