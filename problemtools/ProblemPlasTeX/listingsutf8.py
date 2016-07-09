from plasTeX.Base import Command
from plasTeX.Logging import getLogger

import cgi
import os

log = getLogger()

# Implementation of (parts) of listingsutf8 package since PlasTeX does
# not have one

class lstinputlisting(Command):
    args = '* [ options:dict ] file:str'

    def read_file(self, filename):
        data = open(filename, 'r').read().decode('utf8')
        data = cgi.escape(data)
        return data

    def invoke(self, tex):
        res = Command.invoke(self, tex)
        basetex = self.ownerDocument.userdata['base_tex_instance']
        f = self.attributes['file']
        # Maybe more paths to look in?
        paths = [os.path.dirname(basetex.filename)]
        # Locate file
        for p in paths:
            fname = os.path.join(p, f)
            if os.path.isfile(fname):
                self.attributes['data'] = self.read_file(fname)
                break
        if 'data' not in self.attributes:
            log.warning('Problem opening file "%s"', f)

        # TODO: handle language param in options
