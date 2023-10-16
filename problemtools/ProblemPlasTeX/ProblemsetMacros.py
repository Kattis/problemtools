import sys
import os
import os.path
import io
from plasTeX.DOM import Node
from plasTeX.Base import Command
from plasTeX.Base import DimenCommand
from plasTeX.Logging import getLogger
import plasTeX.Packages.graphics as graphics

log = getLogger()
status = getLogger('status')

# Ugly hack: assume textwidth is 600pt.  True for Kattis but not in
# general.
class textwidth(DimenCommand):
    value = DimenCommand.new('600pt')


# Convert an expression of the form "X\textwidth" to 100*x%
# (Used in ugly hack to handle illustrations)
def clean_width(width):
    if not isinstance(width, Node):
        return width
    nodes = width.childNodes
    if len(nodes) != 2 or nodes[1].nodeName != 'textwidth':
        return width
    return '%.2f%%' % (100*float(nodes[0]))


# \problemheader
class problemheader(Command):
    args = 'title id:str'

    def invoke(self, tex):
        res = Command.invoke(self, tex)
        timelimfile = os.path.join(os.path.dirname(tex.filename),
                                   '..', '.timelimit')
        if os.path.isfile(timelimfile):
            self.attributes['timelim'] = open(timelimfile, 'r').read()


# \sampletable
class sampletable(Command):
    args = 'header1 file1:str header2 file2:str'

    def read_sample_file(self, filename):
        return io.open(filename, 'r', encoding='utf-8').read()

    def invoke(self, tex):
        res = Command.invoke(self, tex)
        dir = os.path.dirname(tex.filename)
        file1 = os.path.join(dir, self.attributes['file1'])
        file2 = os.path.join(dir, self.attributes['file2'])
        try:
            status.info(' ( verbatim %s ' % file1)
            self.attributes['data1'] = self.read_sample_file(file1)
            status.info(') ( verbatim %s ' % file2)
            self.attributes['data2'] = self.read_sample_file(file2)
            status.info(') ')
        except (OSError, IOError):
            log.warning('\nProblem opening files "%s" and "%s"', file1, file2)


# \sampletableinteractive
class sampletableinteractive(Command):
    args = 'header read write file:str'

    def read_sample_interaction(self, filename):
        data = io.open(filename, 'r', encoding='utf-8').read()
        messages = []
        cur_msg = []
        cur_mode = None
        for line in data.split('\n'):
            if not line: continue
            if line[0] == '<': mode = 'read'
            elif line[0] == '>': mode = 'write'
            else: continue
            line = line[1:]
            if mode != cur_mode:
                if cur_mode: messages.append({'mode': cur_mode,
                                              'data': '\n'.join(cur_msg)})
                cur_msg = []
            cur_msg.append(line)
            cur_mode = mode
        if cur_mode: messages.append({'mode': cur_mode,
                                      'data': '\n'.join(cur_msg)})
        return messages

    def invoke(self, tex):
        res = Command.invoke(self, tex)
        dir = os.path.dirname(tex.filename)
        file = os.path.join(dir, self.attributes['file'])
        try:
            status.info(' ( sampletableinteractive %s ' % file)
            self.attributes['messages'] = self.read_sample_interaction(file)
            status.info(') ')
        except (OSError, IOError):
            log.warning('\nProblem opening file "%s"', file)


# Any command including a picture, such as \illustration and our
# re-implementation of \includegraphics.  (Based on plasTeX's
# \includegraphics implementation)
class _graphics_command(Command):
    def invoke(self, tex):
        res = Command.invoke(self, tex)

        # Overcome plasTeX bug by looking for love in the right place
        basetex = self.ownerDocument.userdata['base_tex_instance']
        f = self.attributes['file']
        ext = self.ownerDocument.userdata.getPath(
                      'packages/graphicx/extensions',
                      ['.png', '.jpg', '.jpeg', '.gif', '.pdf'])
        paths = self.ownerDocument.userdata.getPath(
                        'packages/graphicx/paths', [os.path.dirname(basetex.filename)])
        img = None
        # Check for file using graphicspath
        for p in paths:
            for e in ['']+ext:
                fname = os.path.join(p, f+e)
                if os.path.isfile(fname):
                    img = os.path.abspath(fname)
                    break
            if img is not None:
                break

        # Check for file using kpsewhich
        if img is None:
            for e in ['']+ext:
                try:
                    img = os.path.abspath(basetex.kpsewhich(f+e))
                    break
                except (OSError, IOError):
                    pass

        if not os.path.isfile(img):
            log.warning('Could not identify image "%s"' % f)

        self.imageoverride = img
        return res


# \illustration
class illustration(_graphics_command):
    args = 'width:double file:str description'

    def invoke(self, tex):
        res = _graphics_command.invoke(self, tex)
        self.style['width'] = '%.2f%%' % (100*self.attributes['width'])
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


def init(tex):
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
