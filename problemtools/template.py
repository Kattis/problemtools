import os.path
import tempfile
import shutil
from pathlib import Path


class Template:
    """Deals with the temporary .tex file template needed to render a LaTeX problem statement

    Our problemset.cls latex class was originally written to make it easy to
    render a problemset pdf from a bunch of problems for a contest. When we
    want to render a pdf for a single problem, we essentially create a minified
    problemset with a single problem.

    This class creates a temporary directory where it writes a .tex file and a
    problemset.cls file. Run latex on that tex file to render the problem statement.
    The temporary directory and its contents are removed on exit.

    We still support the user providing their own problemset.cls in the parent
    directory of the problem. This will likely be removed at some point (I don't
    think anyone uses this). It can be turned off by setting ignore_parent_cls=True

    Usage:
        with Template(problem_root, texfile) as templ:
            texfile_path = templ.get_file_name()
            os.chdir(os.path.dirname(texfile_path))
            subprocess.call(['pdflatex', texfile_path])
            # Copy the resulting pdf elsewhere before closing the context
    """

    TEMPLATE_FILENAME = 'template.tex'
    CLS_FILENAME = 'problemset.cls'

    def __init__(self, problem_root: Path, texfile: Path, language: str, ignore_parent_cls=False):
        assert texfile.suffix == '.tex', f'Template asked to render {texfile}, which does not end in .tex'
        assert texfile.is_relative_to(problem_root), f'Template called with tex {texfile} outside of problem {problem_root}'

        self.problem_root = problem_root
        self.statement_directory = texfile.relative_to(problem_root).parent
        self.statement_filename = texfile.name
        self.language = language

        self._tempdir: tempfile.TemporaryDirectory | None = None
        self.filename: Path | None = None

        templatepaths = map(
            Path,
            [
                os.path.join(os.path.dirname(__file__), 'templates/latex'),
                os.path.join(os.path.dirname(__file__), '../templates/latex'),
                '/usr/lib/problemtools/templates/latex',
            ],
        )
        try:
            templatepath = next(p for p in templatepaths if p.is_dir() and (p / self.TEMPLATE_FILENAME).is_file())
        except StopIteration:
            raise Exception('Could not find directory with latex template "%s"' % self.TEMPLATE_FILENAME)
        self.templatefile = templatepath / self.TEMPLATE_FILENAME

        sample_dir = problem_root / 'data' / 'sample'
        if sample_dir.is_dir():
            self.samples = sorted({file.stem for file in sample_dir.iterdir() if file.suffix in ['.in', '.interaction']})
        else:
            self.samples = []

        problemset_cls_parent = problem_root.parent / 'problemset.cls'
        if not ignore_parent_cls and problemset_cls_parent.is_file():
            print(f'{problemset_cls_parent} exists, using it -- in case of weirdness this is likely culprit')
            self.clsfile = problemset_cls_parent
        else:
            self.clsfile = templatepath / self.CLS_FILENAME

    def __enter__(self):
        self._tempdir = tempfile.TemporaryDirectory(prefix='problemtools-')
        temp_dir_path = Path(self._tempdir.name)

        shutil.copyfile(self.clsfile, temp_dir_path / self.CLS_FILENAME)

        self.filename = temp_dir_path / 'main.tex'
        with open(self.filename, 'w') as templout, open(self.templatefile) as templin:
            data = {
                'problemparent': str(self.problem_root.parent.resolve()),
                'directory': self.problem_root.name,
                'statement_directory': self.statement_directory.as_posix(),
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
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self._tempdir:
            self._tempdir.cleanup()

    def get_file_name(self) -> str:  # We should later change this to a Path
        assert self.filename and self.filename.is_file()
        return str(self.filename)
