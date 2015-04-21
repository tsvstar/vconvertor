import re, os.path
import util

#https://docs.python.org/2/library/xml.etree.elementtree.html
import xml.etree.ElementTree as ET

megui_path = None


re_job = re.compile('^(job[0-9]+)\.xml$', flags = re.IGNORECASE )
re_jobtext = re.compile('job([0-9]+)', flags = re.IGNORECASE )

# found in child(recursively) first element with given tag
def _get_elem( xml, name ):
    for elem in xml.iter(name):
        return elem
    return None

def DBG_info( val ):
    util.DBG_info( val.replace('\n','~'))

# add to "xml" a new element with "name" and "text"
# with keeping pretty-print formatting
def _add_elem( xml_owner, name, text ):
    DBG_info( "xmlowner=%s; [-2]=%s; [-1]=%s" % ( xml_owner,
                                              None if len(xml_owner)<2 else xml_owner[-2],
                                              None if len(xml_owner)<1 else xml_owner[-1],
                                            )

            )
    util.DBG_info( util.debugDump(xml_owner) )
    if len(xml_owner)>1:
        last = xml_owner[-1].tail
        main = xml_owner[-2].tail
    elif len(xml_owner)>0:
        last = xml_owner[-1].tail
        main = xml_owner.text
    else:
        last = xml_owner.tail
        main = xml_owner.tail + '__'

    DBG_info("  last='%s'(%d), main='%s'(%d) (len=%d)" % (last, len(last), main, len(main), len(xml_owner)))

    elem = ET.SubElement(xml_owner, name)
    if text is not None:
        elem.text = text
    ##print ( "_add_elem(%s)=%s: '%s' '%s' %d" %(name,text, main,last, len(xml_owner)) ).replace('\n','^')
    if len(xml_owner)>1:
        xml_owner[-2].tail = main
        DBG_info("  set[-2](%s).tail='%s'(%d)"%(xml_owner[-1], main,len(main)))
    elif len(xml_owner)<=1:
        ##print ("change owner text from '%s' to '%s' " % (xml_owner.text, main) ).replace('\n','^')
        #if len(xml_owner.text.strip())==0:     # Uncomment this to keep text when add child, but default behavior is clean text if first child added
            xml_owner.text = main
            DBG_info("  set xmlowner(%s).text='%s'(%d)"%(xml_owner, main,len(main)))
    elem.tail = last
    DBG_info("  set elem(%s).tail='%s'(%d)"%(elem, last,len(last)))
    return elem

def _add_elem_notnil( xml_owner, name, text ):
    for key,val in xml_owner.items():
        if key.startswith('{') and key.endswith('}nil') and val=='true':
            del xml_owner.attrib[key]
    return _add_elem( xml_owner, name, text )

def print_xml_tree ( xml, level='' ):
    print level, xml.tag, '|', xml.attrib, '|', xml.text
    for child in xml:
        try: print_xml( child, level+'> ')
        except: pass

def print_xml_plain( root ):
    for xml in root.iter():
        print '', xml.tag, '|', xml.attrib, '|', xml.text

def print_xml_childs( xml, prefix='' ):
    for child in xml:
        print prefix, child.tag, '|', child.attrib, '|', child.text

"""=========================================================================="""

class JobList(object):
    def __init__( self ):
        self.fname = os.path.join( megui_path, 'joblists.xml' )
        self.jobsdir = os.path.join( megui_path, 'jobs' )
        self.tree = ET.parse(self.fname)

        self.joblist = _get_elem( self.tree.getroot(), 'mainJobList' )
        self.dirty = False
        self.findMaxJobNum()

    def __del__(self):
        self.save()
    def __enter__(self, *kw,**kww):
        pass
    def __exit__(self, *kw,**kww):
        self.save()

    # return as ordered by appearance list
    def getJobList(self):
        return map( lambda c: c.text, self.joblist )

    def findMaxJobNum(self):
        self.jobnum = 0
        for c in self.joblist:
            m = re_jobtext.match( c.text )
            if m:
                val = int(m.group(1))
                if val>self.jobnum:
                    self.jobnum = val

    def save(self):
        self.tree.write(self.fname, 'utf-8', xml_declaration=True )
        self.dirty = False

    def appendJob( self, jobname ):
        _add_elem( self.joblist, 'string', jobname )
        self.dirty = True

    def addPostponed( self, queue ):
        for jobname, targetname, xmlContent in queue:
            xmlContent.write(targetname)
            self.appendJob(jobname)

    def addJobXML( self, xmlContent, required=[], postponed = None ):
        self.jobnum += 1
        jobname = "job%04d" % self.jobnum
        _get_elem(xmlContent,'Name').text   = jobname
        _get_elem(xmlContent,'Status').text = 'WAITING'
        _get_elem(xmlContent,'Start').text  = '0001-01-01T00:00:00'
        _get_elem(xmlContent,'End').text    = '0001-01-01T00:00:00'
        reqElement = _get_elem(xmlContent,'RequiredJobNames')
        for j in reqElement:
            reqElement.remove(j)
        for j in required:
            job = 'job%04d'%(self.jobnum+j) if isinstance(j,int) else j
            _add_elem( reqElement, 'string', job )
        targetname = os.path.join( self.jobsdir, jobname+'.xml' )
        if not isinstance( postponed, list ):
            xmlContent.write(targetname,encoding='utf-8') #, xml_declaration=True)
            self.appendJob(jobname)
        else:
            postponed.append( [ jobname, targetname, xmlContent ] )
        return jobname

    def delJob( self, jobname ):
        todel = []
        if isinstance(jobname,basestring):
            jobname = [ jobname ]
        for elem in self.joblist:
            if elem.text in jobname:
                todel.append(elem)
        for elem in todel:
            self.joblist.remove(elem)
            self.dirty = True


def load_jobdir( joblist, delAbsent = True, verbose = True ):
    job_path = joblist.jobsdir
    megui_jobs = joblist.getJobList()
    files = util.scan_dir( job_path, recursive = False, pattern = 'job*', verbose = False )
    lst_missed = []
    to_del = []
    for f in sorted( files ):
        f = os.path.basename( f )
        m = re_job.match( f )
        if m:
            if m.group(1) not in megui_jobs:
                lst_missed.append(m.group(0))
                joblist.appendJob(m.group(1))
    joblist.findMaxJobNum()
    if delAbsent:
        lst = map(lambda f: os.path.basename(f), files)
        for job in megui_jobs:
            if job+".xml" not in lst:
                to_del.append(job)
        if len(to_del):
            joblist.delJob(to_del)

    if verbose:
        if len(lst_missed):
            util.say( "Missed job found: %s", ', '.join(lst_missed) )
        if len(to_del):
            util.say( "Remove absent job: %s", ', '.join(to_del) )


#ET.fromstring(country_data_as_string)
#tree = ET.parse('country_data.xml')
#root = tree.getroot()

