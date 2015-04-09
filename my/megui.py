import re, os.path
import my.util

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

re_job = re.compile('^job([0-9]+)\.xml$', flags = re.IGNORECASE )
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
