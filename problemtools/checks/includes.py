"""Checks for a problem package's include files."""

from pathlib import Path

from ..diagnostics import Diagnostics, pluralize
from ..formatversion import FormatVersion
from ..languages import Languages
from ..model import DEFAULT_LANGUAGE, Includes


def check_includes(includes: Includes, language_config: Languages, format_version: FormatVersion, diag: Diagnostics) -> None:
    """Run all checks on a problem's include files."""
    real_langs = [lang for lang in includes.languages if lang != DEFAULT_LANGUAGE]
    has_default = DEFAULT_LANGUAGE in includes.languages
    if real_langs or has_default:
        overriding = sum(1 for lang in real_langs if includes.languages[lang].mainfile is not None)
        msg = f'Checking include files for {pluralize(len(real_langs), "language")}'
        if has_default:
            msg += ' and a default set'
        if overriding:
            msg += f' ({pluralize(overriding, "overriding entrypoint")})'
        diag.msg(msg)

    _check_default_and_unknown_languages(includes, language_config, format_version, diag)
    _check_ambiguous_mainfile(includes, language_config, diag)
    _check_default_sets_mainfile(includes, language_config, diag)
    _check_default_path_collision(includes, diag)


def _check_default_and_unknown_languages(
    includes: Includes, language_config: Languages, format_version: FormatVersion, diag: Diagnostics
) -> None:
    for lang_id in includes.languages:
        if lang_id == DEFAULT_LANGUAGE:
            if format_version is FormatVersion.LEGACY:
                diag.error(f'Include files for language "{DEFAULT_LANGUAGE}" are not supported in the legacy problem format')
        elif language_config.get(lang_id) is None:
            diag.warning(f'Include files found for unknown language "{lang_id}"')


def _default_include_paths(includes: Includes) -> list[Path]:
    default_includes = includes.languages.get(DEFAULT_LANGUAGE)
    return [f.path for f in default_includes.files] if default_includes else []


def _check_default_path_collision(includes: Includes, diag: Diagnostics) -> None:
    """Flag file name collisions between the default language and other languages"""
    if default_paths := set(_default_include_paths(includes)):
        for lang_id, lang_includes in includes.languages.items():
            if lang_id == DEFAULT_LANGUAGE:
                continue
            colliding = sorted(str(f.path) for f in lang_includes.files if f.path in default_paths)
            if colliding:
                names = ', '.join(colliding)
                diag.error(f'Include files for language "{lang_id}" collide with "{DEFAULT_LANGUAGE}" include files: {names}')


def _check_ambiguous_mainfile(includes: Includes, language_config: Languages, diag: Diagnostics) -> None:
    """Flag languages whose own include files have more than one plausible mainfile."""
    for lang_id, lang_includes in includes.languages.items():
        if lang_id == DEFAULT_LANGUAGE:
            continue
        language = language_config.get(lang_id)
        if language is None:
            continue

        candidates = language.mainfile_candidates([f.path for f in lang_includes.files])
        if len(candidates) > 1:
            names = ', '.join(str(candidate) for candidate in candidates)
            diag.error(f'Include files for language "{lang_id}" have multiple possible mainfiles: {names}')


def _check_default_sets_mainfile(includes: Includes, language_config: Languages, diag: Diagnostics) -> None:
    """Flag "default" include files that look like a mainfile for some language."""
    if default_paths := _default_include_paths(includes):
        for lang_id, language in language_config.languages.items():
            candidates = language.mainfile_candidates(default_paths)
            if candidates:
                names = ', '.join(str(candidate) for candidate in candidates)
                diag.error(f'Include files for language "{DEFAULT_LANGUAGE}" set a mainfile for language "{lang_id}": {names}')
