"""Checks for a problem package's statements."""

from __future__ import annotations

import glob
import os
import traceback
from pathlib import Path

from .. import problem2html, problem2pdf
from ..diagnostics import Diagnostics
from ..formatversion import FormatVersion
from ..metadata import Metadata
from ..model import Statements


def check_statements(
    statements: Statements,
    metadata: Metadata,
    format_version: FormatVersion,
    probdir: Path,
    work_dir: Path,
    diag: Diagnostics,
) -> None:
    """Run all checks on a problem's statements."""
    for ifilename in glob.glob(os.path.join(str(probdir), 'data/sample/*.interaction')):
        if not metadata.is_interactive() and not metadata.is_multi_pass():
            diag.error(f'Problem is not interactive, but there is an interaction sample {ifilename}')
        with open(ifilename, 'r') as interaction:
            for i, line in enumerate(interaction):
                valid_new_pass = metadata.is_multi_pass() and line.strip() == '---'
                if len(line) == 0 or (line[0] != '<' and line[0] != '>' and not valid_new_pass):
                    diag.error(
                        f'Interaction {ifilename}: line {i + 1} does not start with < or > {"or ---" if metadata.is_multi_pass() else ""}'
                    )
                    break

    if not statements.by_language:
        if format_version is FormatVersion.LEGACY:
            allowed_statements = ', '.join(
                f'problem.{ext}, problem.<language>.{ext}' for ext in format_version.statement_extensions
            )
        else:
            allowed_statements = ', '.join(f'problem.<language>.{ext}' for ext in format_version.statement_extensions)

        diag.error(
            f'No problem statements found (expected file of one of following forms in directory {format_version.statement_directory}/: {allowed_statements})'
        )

    def _latex_heuristic(name: str) -> bool:
        return '\\' in name or '$' in name

    for lang, files in statements.by_language.items():
        if len(files) > 1:
            diag.error(f'Found multiple statements in the same language {lang}: {", ".join(file.name for file in files)}')

        if lang not in metadata.name:
            diag.error(f'No problem name given in language {lang}')
        elif not metadata.name[lang]:
            diag.error(f'Problem name in language {lang} is empty')
        elif not metadata.name[lang].strip():
            diag.error(f'Problem name in language {lang} contains only whitespace')
        elif format_version is FormatVersion.LEGACY and _latex_heuristic(metadata.name[lang]):
            diag.warning(f'Problem name in language {lang} looks like LaTeX. Consider using plainproblemname.')

        for file in files:
            try:
                options = problem2pdf.get_parser().parse_args([''])
                options.problem = probdir
                options.language = lang
                options.nopdf = True
                options.quiet = True
                if not problem2pdf.convert(options, file):
                    diag.error(
                        f'Could not compile problem statement for language "{lang}".  Run problem2pdf --language {lang} on the problem to diagnose.'
                    )
            except Exception as e:
                diag.error(f'Error raised when checking problem statement for language {lang}:\n{e}\n{traceback.format_exc()}')

            try:
                options = problem2html.get_parser().parse_args([''])
                options.problem = probdir
                options.destdir = os.path.join(work_dir, 'html')
                options.language = lang
                options.quiet = True
                problem2html.convert(options, file)
            except Exception as e:
                diag.error(
                    f'Could not convert problem statement to html for language "{lang}".  Run problem2html --language {lang} on the problem to diagnose.\n{e}\n{traceback.format_exc()}'
                )
