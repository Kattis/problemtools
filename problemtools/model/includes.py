from dataclasses import dataclass, field
from pathlib import Path

from ..languages import Language, Languages
from .paths import RelativePath, relpath, resolve
from .program_files import ProgramFiles, load_program_files

#: Pseudo-language whose include files are added for every language.
DEFAULT_LANGUAGE = 'default'


@dataclass(frozen=True)
class LanguageIncludes:
    """Include files for a language.

    File paths are relative to the include directory for the language, e.g. for
    include/cpp/Vector/Vector.h, path is Vector/Vector.h.
    """

    mainfile: RelativePath | None = None
    files: ProgramFiles = field(default_factory=ProgramFiles)


@dataclass(frozen=True)
class Includes:
    """All include files for a problem, keyed by language ID.

    The key DEFAULT_LANGUAGE holds files that are added to every language.
    """

    languages: dict[str, LanguageIncludes] = field(default_factory=dict)

    def get_includes_for_language(self, language: str) -> LanguageIncludes:
        """All includes relevant for `language`: the files registered for
        DEFAULT_LANGUAGE (which apply to every language) plus those registered
        for `language` itself, with the mainfile taken from `language`. Where
        paths coincide, the file registered for `language` wins.
        """
        default_includes = self.languages.get(DEFAULT_LANGUAGE, LanguageIncludes())
        lang_includes = self.languages.get(language, LanguageIncludes())
        return LanguageIncludes(mainfile=lang_includes.mainfile, files=default_includes.files.merged(lang_includes.files))


def load_includes(probdir: Path, language_config: Languages) -> Includes:
    include_dir = resolve(probdir) / 'include'
    includes = Includes()
    if not include_dir.is_dir():
        return includes

    for lang_dir in sorted(include_dir.iterdir()):
        if lang_dir.is_dir():
            language = language_config.get(lang_dir.name)
            includes.languages[lang_dir.name] = _load_language_includes(lang_dir, language)
    return includes


def _load_language_includes(lang_dir: Path, language: Language | None) -> LanguageIncludes:
    files = load_program_files(lang_dir)

    mainfile: RelativePath | None = None
    if language is not None:
        source_files = language.get_source_files([f.path for f in files.files])
        candidates = language.mainfile_candidates(source_files)
        if candidates:
            mainfile = relpath(candidates[0])

    return LanguageIncludes(mainfile=mainfile, files=files)
