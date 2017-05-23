#encoding=cp1251
# Batch rename 
#   - Usage: convertor_rename.py DIRNAME [-R]
#   - rename rule is determined by Rename() callback

import sys,os
import my.util

def Rename( path ):
	p, name = os.path.split(path)
	name2 = name
	if name[0]=='[' and name[5]==']':
           name2 = name[6:] 
        print name2
        name2 = name2.replace('.mp4-mux2000','') 
        name2 = name2.replace('IMG_20151221_154639_1450705649081','') 
	newname = os.path.join( p, name2 )
	#newname = path.replace("..",".")
	if path!=newname:
		print p, name, name2
		if os.path.exists( newname ):
		   print "Ignore because of already exist"
		else:
		   os.rename( path, newname )

dirname = sys.argv[1]
if not os.path.exists( dirname ) and dirname.endswith('"'):
    dirname = dirname[:-1]
res = my.util.scan_dir( dirname, recursive=('-R' in sys.argv), pattern="*.mkv")
for path in res:
    Rename( path )


