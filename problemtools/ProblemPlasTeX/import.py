# noqa: N999 -- module name matches the plasTeX \import macro it implements, not PEP 8
import os
from typing import Any

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

    def invoke(self, tex: Any) -> Any:
        a = self.parse(tex)
        path = os.path.join(a['dir'], a['file'])
        fullpath = tex.kpsewhich(path)
        status.info(f' ( {fullpath} ')
        try:
            encoding = self.config['files']['input-encoding']
            tex.input(open(fullpath, 'r', encoding=encoding, errors='replace'))  # noqa: SIM115
        except OSError:
            log.warning('\nProblem opening file "%s"', fullpath)
        status.info(' ) ')
        return []
