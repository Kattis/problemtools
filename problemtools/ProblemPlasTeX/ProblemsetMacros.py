# noqa: N999 -- module name matches the plasTeX macro file it implements, not PEP 8
import os
import os.path
import sys
from typing import Any

from plasTeX.Base import Command, DimenCommand
from plasTeX.DOM import Node
from plasTeX.Logging import getLogger

log = getLogger()
status = getLogger('status')


# Ugly hack: assume textwidth is 600pt.  True for Kattis but not in
# general.
class textwidth(DimenCommand):
    value = DimenCommand.new('600pt')


# Convert an expression of the form "X\textwidth" to 100*x%
# (Used in ugly hack to handle illustrations)
def clean_width(width: Any) -> Any:
    if not isinstance(width, Node):
        return width
    nodes = width.childNodes
    if len(nodes) != 2 or nodes[1].nodeName != 'textwidth':
        return width
    return '%.2f%%' % (100 * float(nodes[0]))


# \problemheader
class problemheader(Command):
    args = 'title id:str'

    def invoke(self, tex: Any) -> None:
        super().invoke(tex)
        timelimfile = os.path.join(os.path.dirname(tex.filename), '..', '.timelimit')
        if os.path.isfile(timelimfile):
            with open(timelimfile, 'r') as f:
                self.attributes['timelim'] = f.read()


# \sampletable
class sampletable(Command):
    args = 'header1 file1:str header2 file2:str'

    def read_sample_file(self, filename: str) -> str:
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read()

    def invoke(self, tex: Any) -> None:
        super().invoke(tex)
        dir = os.path.dirname(tex.filename)
        file1 = os.path.join(dir, self.attributes['file1'])
        file2 = os.path.join(dir, self.attributes['file2'])
        try:
            status.info(f' ( verbatim {file1} ')
            self.attributes['data1'] = self.read_sample_file(file1)
            status.info(f') ( verbatim {file2} ')
            self.attributes['data2'] = self.read_sample_file(file2)
            status.info(') ')
        except OSError:
            log.warning('\nProblem opening files "%s" and "%s"', file1, file2)


# \sampletableinteractive
class sampletableinteractive(Command):
    args = 'header read write file:str'

    def read_sample_interaction(self, filename: str) -> list[dict[str, str]]:
        with open(filename, 'r', encoding='utf-8') as f:
            data = f.read()
        messages: list[dict[str, str]] = []
        cur_msg: list[str] = []
        cur_mode = None
        for line in data.split('\n'):
            if not line:
                continue
            if line[0] == '<':
                mode = 'read'
            elif line[0] == '>':
                mode = 'write'
            else:
                continue
            line = line[1:]
            if mode != cur_mode:
                if cur_mode:
                    messages.append({'mode': cur_mode, 'data': '\n'.join(cur_msg)})
                cur_msg = []
            cur_msg.append(line)
            cur_mode = mode
        if cur_mode:
            messages.append({'mode': cur_mode, 'data': '\n'.join(cur_msg)})
        return messages

    def invoke(self, tex: Any) -> None:
        super().invoke(tex)
        dir = os.path.dirname(tex.filename)
        file = os.path.join(dir, self.attributes['file'])
        try:
            status.info(f' ( sampletableinteractive {file} ')
            self.attributes['messages'] = self.read_sample_interaction(file)
            status.info(') ')
        except OSError:
            log.warning('\nProblem opening file "%s"', file)


# Any command including a picture, such as \illustration and our
# re-implementation of \includegraphics.  (Based on plasTeX's
# \includegraphics implementation)
class _graphics_command(Command):
    def invoke(self, tex: Any) -> Any:
        res = super().invoke(tex)

        # Overcome plasTeX bug by looking for love in the right place
        assert self.ownerDocument is not None  # Keep mypy happy
        basetex = self.ownerDocument.userdata['base_tex_instance']
        f = self.attributes['file']
        ext = self.ownerDocument.userdata.getPath('packages/graphicx/extensions', ['.png', '.jpg', '.jpeg', '.gif', '.pdf'])
        paths = self.ownerDocument.userdata.getPath('packages/graphicx/paths', [os.path.dirname(basetex.filename)])
        img: str | None = None
        # Check for file using graphicspath
        for p in paths:
            for e in [''] + ext:
                fname = os.path.join(p, f + e)
                if os.path.isfile(fname):
                    img = os.path.abspath(fname)
                    break
            if img is not None:
                break

        # Check for file using kpsewhich
        if img is None:
            for e in [''] + ext:
                try:
                    img = os.path.abspath(basetex.kpsewhich(f + e))
                    break
                except OSError:
                    pass

        if img is None or not os.path.isfile(img):
            log.warning(f'Could not identify image "{f}"')

        self.imageoverride = img
        return res


# \illustration
class illustration(_graphics_command):
    args = 'width:double file:str description'

    def invoke(self, tex: Any) -> Any:
        res = _graphics_command.invoke(self, tex)
        self.style['width'] = '%.2f%%' % (100 * self.attributes['width'])
        return res


# Dummy for \fontencoding to suppress warnings
class fontencoding(Command):
    args = 'charset:str'


# Dummy for \selectfont to suppress warnings.
class selectfont(Command):
    pass


# Dummy for \ExecuteOptions to suppress warnings.
class ExecuteOptions(Command):
    pass


def init(tex: Any) -> None:
    # Dirty hack #25783 to get plasTeX to work properly:
    # any subprocess of the tex instance won't remember things like,
    # say, the name of the .tex file being processed, which is needed
    # for kpsewhich to work.  So we'll keep a pointer to the original
    # tex instance in the document's userdata.
    tex.ownerDocument.userdata['base_tex_instance'] = tex

    # Import the macros
    tex.ownerDocument.context.importMacros(vars(sys.modules[__name__]))

    # So apparently this is how to communicate to Plastex where to
    # search for modules... Eugch.
    sys.path = [os.path.dirname(__file__)] + sys.path
