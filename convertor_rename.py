# PREPARE SONY MTS TO CORRECT CONVERSION (SYNCED AUDIO/VIDEO) USING AVIDEMUX
#	copy video + convert audio -> NAME.ts

# For my computer "use QT4 version" checkbox should be on

import sys,os
import my.util

def Rename( path ):
	newname = path.replace("..",".")
	if path!=newname:
		print path, newname
		os.rename( path, newname )

dirname = sys.argv[1]
if not os.path.exists( dirname ) and dirname.endswith('"'):
    dirname = dirname[:-1]
res = my.util.scan_dir( dirname, recursive=False, pattern="*.mkv")
for path in res:
    Rename( path )

