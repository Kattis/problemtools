import sys
import os
import os.path
from pathlib import Path
from plasTeX.DOM import Node
from plasTeX.Base import Command
from plasTeX.Base import DimenCommand
from plasTeX.Logging import getLogger

from problemtools import metadata

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
    return '%.2f%%' % (100 * float(nodes[0]))


# \problemheader
class problemheader(Command):
    args = 'title id:str'

    def invoke(self, tex):
        super().invoke(tex)
        timelimfile = os.path.join(os.path.dirname(tex.filename), '..', '.timelimit')
        if os.path.isfile(timelimfile):
            self.attributes['timelim'] = open(timelimfile, 'r').read()


# \sampletable
class sampletable(Command):
    args = 'header1 file1:str header2 file2:str'

    def read_sample_file(self, filename):
        return open(filename, 'r', encoding='utf-8').read()

    def invoke(self, tex):
        super().invoke(tex)
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

    def split_multipass(self, lines: list[str]) -> list[list[str]]:
        multipass_passes = []
        curr_pass: list[str] = []
        for line in lines:
            if line.startswith('---'):
                multipass_passes.append(curr_pass)
                curr_pass = []
            else:
                curr_pass.append(line)

        if curr_pass:
            multipass_passes.append(curr_pass)
        return multipass_passes

    def format_pass_content(self, block: list[str]) -> list[dict]:
        sections = []

        if self.attributes['is_interactive']:
            cur_msg: list[str] = []
            cur_mode = None

            def format_message(cur_mode: str, cur_msg: list[str]) -> dict:
                return {'mode': cur_mode, 'data': ''.join(cur_msg)}

            for line in block:
                if not line:
                    continue
                if line[0] not in ('<', '>'):
                    log.warning(f'Interaction had unknown prefix {line[0]}')
                    continue

                if line[0] == '<':
                    mode = 'read'
                elif line[0] == '>':
                    mode = 'write'

                if mode != cur_mode:
                    if cur_mode:
                        sections.append(format_message(cur_mode, cur_msg))
                    cur_msg = []
                cur_mode = mode
                cur_msg.append(line[1:])
            if cur_mode:
                sections.append(format_message(cur_mode, cur_msg))
        else:
            in_data = ''.join(line[1:] for line in block if line[0] == '>')
            out_data = ''.join(line[1:] for line in block if line[0] == '<')
            sections.append({'mode': 'batch_sample', 'in_data': in_data, 'out_data': out_data})
        return sections

    def read_sample_interaction(self, filename: Path) -> list[dict]:
        with open(filename, 'r', encoding='utf-8') as f:
            data = self.split_multipass(f.readlines())

        messages = []
        for index, block in enumerate(data):
            if self.attributes['is_multi_pass']:
                messages.append({'mode': 'newpass', 'data': str(index + 1)})
            messages.extend(self.format_pass_content(block))
        return messages

    def invoke(self, tex):
        super().invoke(tex)
        dir = os.path.dirname(tex.filename)
        file = Path(dir) / self.attributes['file']
        # A slightly messy way of finding out whether we're multipass and/or interactive
        problem_root = file.parent.parent.parent
        problem_metadata, _ = metadata.load_metadata(problem_root)
        self.attributes['is_multi_pass'] = problem_metadata.is_multi_pass()
        self.attributes['is_interactive'] = problem_metadata.is_interactive()

        if not self.attributes['is_interactive']:
            self.attributes['read'] = 'Sample Input'
            self.attributes['write'] = 'Sample Output'
            self.attributes['header'] = f'Sample Case {self.attributes["header"][2]}'

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
                except (OSError, IOError):
                    pass

        if img is None or not os.path.isfile(img):
            log.warning('Could not identify image "%s"' % f)

        self.imageoverride = img
        return res


# \illustration
class illustration(_graphics_command):
    args = 'width:double file:str description'

    def invoke(self, tex):
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
