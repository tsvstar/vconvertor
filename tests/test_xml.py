import my.config as _mycfg
import xml.etree.ElementTree as ET


import my.megui, my.util
from my.megui import _get_elem, _add_elem

def main()
    cfg = _mycfg.ConfigLoader( isDebug = True )

    #@tsv
    content = cfg.load_template('x264base.1pass')
    content = ET.ElementTree(ET.fromstring(content))
    print content
    root = content.getroot()

    e = _get_elem(root,'Zones')
    _add_elem(e,'first_child','txt1')
    print e.tag, e.text, "'%s'"%e.tail

    e = _get_elem(root,'Output')
    _add_elem(e,'first_child','txt11')
    _add_elem(e,'second_child','txt11')

    e = _get_elem(root,'Settings')
    for k in dir(e):
        print k, getattr(e,k)
    _add_elem(e,'last_child','txt2')
    content.write('C:/MY/GITHUB/vconvertor/out.xml')


main()