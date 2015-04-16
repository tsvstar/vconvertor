import re, os.path
import my.util

#https://docs.python.org/2/library/xml.etree.elementtree.html
import xml.etree.ElementTree as ET

megui_path = None

re_job = re.compile('^(job[0-9]+)\.xml$', flags = re.IGNORECASE )
re_jobtext = re.compile('job([0-9]+)', flags = re.IGNORECASE )

def _get_elem( xml, name ):
    for elem in xml.iter(name):
        return elem
    return None

def print_xml ( xml, level='' ):
    print level, xml.tag, '|', xml.attrib, '|', xml.text
    for child in xml:
        try: print_xml( child, level+'> ')
        except: pass


def print_xml1( root ):
    for xml in root.iter():
        print '', xml.tag, '|', xml.attrib, '|', xml.text


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
    def getJobList(self):
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
        self.tree.write(self.fname, 'utf-8', xml_declaration=True )
        self.dirty = False

    def appendJob( self, jobname ):
        job = ET.SubElement(self.joblist, 'string')
        job.text = jobname
        job.tail='\n  '             # pretty-print formatting
        if len(self.joblist)>1:
            self.joblist[-2].tail = '\n    '
        self.dirty = True

    def addPostponed( self, queue ):
        for jobname, targetname, xmlContent in queue:
            xmlContent.write(targetname)
            appendJob(jobname)

    def addJobXML( self, xmlContent, required=[], postponed = None ):
        jobnum += 1
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
        targetname = os.path.join( megui_path, jobname+'.xml' )
        if not isinstance( postponed, list ):
            xmlContent.write(targetname)
            appendJob(jobname)
        else:
            postponed.append( [ jobname, targetname, xmlContent ] )
        return jobname

    def delJob( self, jobname ):
        todel = []
        for elem in self.joblist:
            if elem.text==jobname:
                todel.append(elem)
        for elem in todel:
            self.joblist.remove(elem)
            self.dirty = True


def load_jobdir( joblist, verbose = True ):
    job_path = os.path.join(megui_path,'jobs')
    megui_jobs = joblist.getJobList()
    files = my.util.scan_dir( job_path, recursive = False, pattern = 'job*', verbose = False )
    for f in sorted( files ):
        f = os.path.basename( f )
        m = re_job.match( f )
        if m:
            if m.group(1) not in megui_jobs:
                if verbose:
                    print "Missed job found: %s" % m.group(0)
                joblist.appendJob(m.group(1))
    joblist.findMaxJobNum()

#ET.fromstring(country_data_as_string)
#tree = ET.parse('country_data.xml')
#root = tree.getroot()

