from plasTeX.Base import Command
from plasTeX.Logging import getLogger

import os
import io

log = getLogger()

# Implementation of (parts) of listingsutf8 package since PlasTeX does
# not have one


class lstinputlisting(Command):
    args = '* [ options:dict ] file:str'

    def read_file(self, filename) -> str:
        return io.open(filename, 'r', encoding='utf-8').read()

    def invoke(self, tex) -> None:
        super().invoke(tex)
        assert self.ownerDocument is not None  # Keep mypy happy
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
