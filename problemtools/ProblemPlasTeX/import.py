import codecs
import os
from plasTeX.Base import Command
from plasTeX.Logging import getLogger

log = getLogger()
status = getLogger('status')

# (Partial) implementation of import.sty because plasTeX does not ship
# with an implementation.  Only implement \import command which is the
# only one we'll use.
class import_sty(Command):
    macroName = 'import'
    args = 'dir:str file:str'

    def invoke(self, tex):
        a = self.parse(tex)
        path = os.path.join(a['dir'], a['file'])
        fullpath = tex.kpsewhich(path)
        status.info(' ( %s ' % fullpath)
        try:
            encoding = self.config['files']['input-encoding']
            tex.input(codecs.open(fullpath, 'r', encoding, 'replace'))
        except (OSError, IOError):
            log.warning('\nProblem opening file "%s"', fullpath)
        status.info(' ) ')
        return []
