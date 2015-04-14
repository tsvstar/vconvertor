import re, os.path
import my.util

#https://docs.python.org/2/library/xml.etree.elementtree.html
import xml.etree.ElementTree as ET

megui_path = None

re_job = re.compile('^job([0-9]+)\.xml$', flags = re.IGNORECASE )
re_jobtext = re.compile('job([0-9]+)', flags = re.IGNORECASE )

def _get_elem( xml, name ):
    for elem in xml.iter(name):
        return elem
    return None

class JobList(object):
    def __init__( self ):
        self.fname = os.path.join( megui_path, 'joblists.xml' )
        self.tree = ET.parse(self.fname)

        self.joblist = _get_elem( self.tree.getroot(), 'mainJobList' )
        self.dirty = False
        self.findMaxJobNum()
        #for child in self.joblist:
        #    print child.tag, '|', child.attrib, '|', child.text

    def __del__(self):
        self.save()
    def __enter__(self, *kw,**kww):
        pass
    def __exit__(self, *kw,**kww):
        self.save()

    # return as ordered by appearance list
    def getJoblist(self):
        return map( lambda c: c.text, self.joblist )

    def findMaxJobNum(self):
        self.jobnum = 0
        for c in self.joblist:
            m = re_jobtext.match( c.text )
            if m:
                val = int(m.group(1))+1
                if val>self.jobnum:
                    self.jobnum = val

    def save(self):
        self.tree.write(self.fname, 'utf-8')
        self.dirty = False

    def addJob( self, jobname ):
        job = ET.SubElement(self.joblist, 'string')
        job.text = jobname
        self.dirty = True

    def addJobXML( self, xmlContent, required=[] ):
        jobname = "job%04d" % jobnum
        _get_elem(xmlContent,'Name').text   = jobname
        _get_elem(xmlContent,'Status').text = 'WAITING'
        _get_elem(xmlContent,'Start').text  = '0001-01-01T00:00:00'
        _get_elem(xmlContent,'End').text    = '0001-01-01T00:00:00'
        reqElement = _get_elem(xmlContent,'RequiredJobNames')
        for j in reqElement:
            reqElement.remove(j)
        for j in required:
            elem = ET.SubElement(reqElement, 'string')
            elem.text = 'job%04d'%(jobnum+j)
        jobnum += 1
        targetname = os.path.join( megui_path, jobname+'.xml' )
        xml.write(targetname)

    def delJob( self, jobname ):
        todel = []
        for elem in self.joblist:
            if elem.text==jobname:
                todel.append(elem)
        for elem in todel:
            self.joblist.remove(elem)
            self.dirty = True


#ET.fromstring(country_data_as_string)
#tree = ET.parse('country_data.xml')
#root = tree.getroot()


"""
==========================================================

   PROCESSING MEGUI CONFIGS

DRAFT REWRITED FROM PHP
TO CHECK
TO REFACTOR(use xml? library)

=========================================================
"""


megui_path = None

joblist_content = [ '', '', '']     # pre, jobs, post
jobs = []		                     # Ordered content of '<mainJobList>' in'joblists.xml' (string numeric value)
max_jobnumber = 0
dirty = False

re_jobxml = re.compile('<string>job([0-9]+)</string>$', flags = re.IGNORECASE )

def get_path():
    job_path = os.path.join( megui_path, 'jobs')
    joblist_path = os.path.join( megui_path, 'joblists.xml')
    return job_path, joblist_path

def _add_loaded_job( m ):
        if m:
            jobs.append( m.group(1) )
            max_jobnumber = max( [max_jobnumber, int(m.group(1))] )


def _load_joblist_xml( handler, verbose = True ):

    joblist_content = [ '', '', '' ]     # pre, jobs, post
    job_path, joblist_path = get_path()

    # load joblist.xml
    with open( joblist_path, 'r' ) as f:
        lines = f.readlines()
    stage = 0
    for l in lines:
        if l.find("mainJobList")>=0:
            if l.find("<mainJobList />")>=0:
                stage = 2
            elif l.find("<mainJobList>")>=0:
                stage = 1
            elif l.find("</mainJobList>")>=0:
                stage = 2
            else:
                joblist_content[stage] += l
            continue


        joblist_content[stage] += l
        if stage!=1:
            continue
        m = re_jobxml.search()
        handler( m )

def _load_jobdir( handler, verbose = True ):
    job_path, joblist_path = get_path()
    files = my.util.scan_dir( job_path, recursive = False, pattern = 'job*', verbose = False )
    for f in sorted( files ):
        f = os.path.basename( f )
        m = re_job.match( f )
        if m:
            if m.group(1) not in megui_jobs:
                dirty = True
                if verbose:
                    print "Missed job found: job%s.xml" % m.group(1)
                handler(m)

def load_jobs( verbose = True ):
    megui_jobs = []
    max_jobnumber = 0
    _load_joblist_xml( _add_loaded_job, verbose = verbose )
    _load_jobdir( _add_loaded_job, verbose = verbose )

def save_jobs( enforce = False ):

    if not dirty and not enforce:
        return

    job_path, joblist_path = get_path()
    _load_joblist_xml( lambda m: None, verbose = False )

    # load joblist.xml
    with open( joblist_path, 'w' ) as f:
        f.write( joblist_content[0] )
        ar = map( lambda n: "    <string>job%s</string>"%n, jobs )
        f.write( '  <mainJobList>\n%s\n  <mainJobList>\n' % ('\n'.join(ar) ) )
        f.write( joblist_content[2] )
    dirty = False


def add_job( content ):
    job_path, joblist_path = get_path()

    dirty = True
    max_jobnumber += 1
    num = "%04d" % max_jobnumber
    jobs.append(num)

    fname = os.path.join( job_path, "job%s.xml" % num )
    with open( fname, 'w' ) as f:
        f.write( content )
