import os.path
import glob
import tempfile
import shutil
from pathlib import Path


class Template:
    """Deals with the temporary .tex file template needed to render a LaTeX problem statement

    Our problemset.cls latex class was originally written to make it easy to
    render a problemset pdf from a bunch of problems for a contest. When we
    want to render a pdf for a single problem, we need to dump a small,
    temporary tex file in the parent directory (essentially a minified
    problemset with just one problem). This class deals with creating and
    cleaning up that template. The template has to be written in the parent
    directory of problem_root.

    Usage:
        with Template(problem_root, texfile) as templ:
            texfile = templ.get_file_name()
            os.chdir(os.path.dirname(texfile))
            subprocess.call(['pdflatex', texfile])
    """

    def __init__(self, problem_root: Path, texfile: Path, language: str, force_copy_cls=False):
        assert texfile.suffix == '.tex', f'Template asked to render {texfile}, which does not end in .tex'
        assert texfile.is_relative_to(problem_root), f'Template called with tex {texfile} outside of problem {problem_root}'

        self.problem_root = problem_root
        self.statement_directory = texfile.relative_to(problem_root).parent
        self.statement_filename = texfile.name
        self.templatefile = 'template.tex'
        self.clsfile = 'problemset.cls'
        self.language = language

        templatepaths = [
            os.path.join(os.path.dirname(__file__), 'templates/latex'),
            os.path.join(os.path.dirname(__file__), '../templates/latex'),
            '/usr/lib/problemtools/templates/latex',
        ]
        try:
            self.templatepath = next(
                (p for p in templatepaths if os.path.isdir(p) and os.path.isfile(os.path.join(p, self.templatefile)))
            )
        except StopIteration:
            raise Exception('Could not find directory with latex template "%s"' % self.templatefile)

        sample_dir = problem_root / 'data' / 'sample'
        if sample_dir.is_dir():
            self.samples = sorted({file.stem for file in sample_dir.iterdir() if file.suffix in ['in', 'interaction']})
        else:
            self.samples = []

        self.problemset_cls = problem_root.parent / 'problemset.cls'
        self.copy_cls = True
        if self.problemset_cls.is_file() and not force_copy_cls:
            print(f'{self.problemset_cls} exists, will not copy it -- in case of weirdness this is likely culprit')
            self.copy_cls = False

    def __enter__(self):
        if self.copy_cls:
            shutil.copyfile(os.path.join(self.templatepath, self.clsfile), self.problemset_cls)

        (templfd, self.filename) = tempfile.mkstemp(suffix='.tex', dir=self.problem_root.parent)
        templout = os.fdopen(templfd, 'w')
        templin = open(os.path.join(self.templatepath, self.templatefile))
        data = {
            'directory': self.problem_root.name,
            'statement_directory': self.statement_directory,
            'statement_filename': self.statement_filename,
            'language': self.language,
        }
        for line in templin:
            try:
                templout.write(line % data)
            except KeyError:
                # This is a bit ugly I guess
                for sample in self.samples:
                    data['sample'] = sample
                    templout.write(line % data)
                if self.samples:
                    del data['sample']
        templout.close()
        templin.close()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.problemset_cls is not None and self.copy_cls and os.path.isfile(self.problemset_cls):
            os.remove(self.problemset_cls)
        if self.filename is not None:
            for f in glob.glob(os.path.splitext(self.filename)[0] + '.*'):
                if os.path.isfile(f):
                    os.remove(f)

    def get_file_name(self) -> str:  # We should later change this to a Path
        assert os.path.isfile(self.filename)
        return self.filename
