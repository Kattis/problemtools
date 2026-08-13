from dataclasses import dataclass, field
from pathlib import Path

from ..languages import Language, Languages

#: Pseudo-language whose include files are added for every language.
DEFAULT_LANGUAGE = 'default'


@dataclass(frozen=True)
class IncludeFile:
    """A single include file.

    `path` is relative to the include directory for its language, e.g. for
    include/cpp/Vector/Vector.h, path is Vector/Vector.h.
    """

    path: Path
    data: bytes


@dataclass(frozen=True)
class LanguageIncludes:
    mainfile: str | None = None
    files: list[IncludeFile] = field(default_factory=list)


@dataclass(frozen=True)
class Includes:
    """All include files for a problem, keyed by language ID.

    The key DEFAULT_LANGUAGE holds files that are added to every language.
    """

    languages: dict[str, LanguageIncludes] = field(default_factory=dict)

    def get_includes_for_language(self, language: str) -> LanguageIncludes:
        """All includes relevant for `language`: the files registered for
        DEFAULT_LANGUAGE (which apply to every language) plus those registered
        for `language` itself, with the mainfile taken from `language`.
        """
        default_includes = self.languages.get(DEFAULT_LANGUAGE, LanguageIncludes())
        lang_includes = self.languages.get(language, LanguageIncludes())
        return LanguageIncludes(mainfile=lang_includes.mainfile, files=default_includes.files + lang_includes.files)


def load_includes(probdir: Path, language_config: Languages) -> Includes:
    include_dir = probdir / 'include'
    includes = Includes()
    if not include_dir.is_dir():
        return includes

    for lang_dir in sorted(include_dir.iterdir()):
        if lang_dir.is_dir():
            language = language_config.get(lang_dir.name)
            includes.languages[lang_dir.name] = _load_language_includes(lang_dir, language)
    return includes


def _load_language_includes(lang_dir: Path, language: Language | None) -> LanguageIncludes:
    paths = sorted(p for p in lang_dir.rglob('*') if p.is_file())
    files = [IncludeFile(path=path.relative_to(lang_dir), data=path.read_bytes()) for path in paths]

    mainfile = None
    if language is not None:
        source_files = language.get_source_files(paths)
        candidates = language.mainfile_candidates(source_files)
        if candidates:
            mainfile = str(Path(candidates[0]).relative_to(lang_dir))

    return LanguageIncludes(mainfile=mainfile, files=files)
