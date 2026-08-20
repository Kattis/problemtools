import os
import re
import shutil
from unittest import TestCase

import pytest

from problemtools import languages


class Language_test(TestCase):
    @staticmethod
    def __language_dict():
        return {
            'name': 'A Language',
            'priority': 100,
            'files': '*.foo *.bar',
            'shebang_files': '*.foo',
            'shebang': '.*',
            'compile': 'echo {path} {files} {binary}',
            'run': '{binary} {memlim}',
        }

    def test_create(self):
        languages.Language('langid', self.__language_dict())

    def test_update(self):
        lang = languages.Language('langid', self.__language_dict())

        lang.update({'priority': -1})
        assert lang.priority == -1

        lang.update({'name': 'New name'})
        assert lang.name == 'New name'

        lang.update({'files': '*'})
        assert lang.files == ['*']

        lang.update({'shebang': 'new.*end'})
        assert lang.shebang is not None and lang.shebang.match('newfilend')

        with pytest.raises(languages.LanguageConfigError):
            # ambiguous entry point
            lang.update({'compile': '{mainfile}'})
        lang.update({'compile': 'newcompile'})
        assert lang.compile == 'newcompile'

        with pytest.raises(languages.LanguageConfigError):
            # no entry point
            lang.update({'run': 'newrun'})
        lang.update({'run': 'newrun {mainclass}'})
        assert lang.run == 'newrun {mainclass}'

    def test_invalid_id(self):
        vals = self.__language_dict()
        with pytest.raises(TypeError):
            languages.Language(None, vals)  # type: ignore
        with pytest.raises(TypeError):
            languages.Language(42, vals)  # type: ignore
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('åäö', vals)
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('_java_', vals)
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('Capital', vals)

    def test_missing_name(self):
        vals = self.__language_dict()
        del vals['name']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_invalid_name(self):
        vals = self.__language_dict()
        vals['name'] = ['A List']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_missing_priority(self):
        vals = self.__language_dict()
        del vals['priority']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_invalid_priority(self):
        vals = self.__language_dict()
        vals['priority'] = 2.3
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)
        vals['priority'] = '100'
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_missing_files(self):
        vals = self.__language_dict()
        del vals['files']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_invalid_files(self):
        vals = self.__language_dict()
        vals['files'] = ['*.cc', '*.cpp']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_without_shebang(self):
        vals = self.__language_dict()
        del vals['shebang']
        del vals['shebang_files']
        languages.Language('id', vals)

    def test_invalid_shebang(self):
        vals = self.__language_dict()
        vals['shebang'] = '(Not an RE'
        with pytest.raises(re.error):
            languages.Language('id', vals)

    def test_shebang_requires_shebang_files(self):
        vals = self.__language_dict()
        del vals['shebang_files']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_shebang_files_requires_shebang(self):
        vals = self.__language_dict()
        del vals['shebang']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_invalid_shebang_files(self):
        vals = self.__language_dict()
        vals['shebang_files'] = ['*.foo', '*.bar']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_get_source_files_does_not_require_readable_files(self):
        """get_source_files only inspects file names -- unlike
        get_source_files_for_detection, it must work even for files that
        don't exist, since it's used on a program whose language is
        already known."""
        lang = languages.Language('id', self.__language_dict())
        missing = '/nonexistent/path/does_not_exist.foo'

        assert lang.get_source_files([missing]) == [missing]
        with pytest.raises(OSError):
            lang.get_source_files_for_detection([missing])

    def test_without_compile(self):
        vals = self.__language_dict()
        del vals['compile']
        languages.Language('id', vals)

    def test_invalid_compile(self):
        vals = self.__language_dict()
        vals['compile'] = ['gcc', '{files}']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)
        vals['compile'] = 'echo {nonexistent}'
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_missing_run(self):
        vals = self.__language_dict()
        del vals['run']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_invalid_run(self):
        vals = self.__language_dict()
        vals['run'] = ['python3', '{mainfile}']
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)
        vals['run'] = 'echo {nonexistent}'
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    def test_good_entrypoints(self):
        vals = self.__language_dict()

        vals['compile'] = 'echo {binary}'
        vals['run'] = 'echo {binary}'
        languages.Language('id', vals)

        vals['compile'] = 'echo {mainfile}'
        vals['run'] = 'echo {mainfile}'
        languages.Language('id', vals)

        vals['compile'] = 'echo {mainclass}'
        vals['run'] = 'echo {mainclass}'
        languages.Language('id', vals)

    def test_bad_entrypoints(self):
        vals = self.__language_dict()

        # Two different entry points
        vals['run'] = 'echo {mainfile}'
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

        # No entry point
        vals['run'] = 'echo COMPILE'
        vals['compile'] = 'echo RUN'
        with pytest.raises(languages.LanguageConfigError):
            languages.Language('id', vals)

    @staticmethod
    def __subs(**overrides):
        values = {
            'path': '/tmp/prog',
            'files': 'main.foo',
            'binary': '/tmp/prog/run',
            'mainfile': '/tmp/prog/main.foo',
            'mainclass': 'main',
            'Mainclass': 'Main',
            'memlim': 256,
        }
        values.update(overrides)
        return languages.CommandSubstitution(**values)

    def test_check_installed_ok(self):
        # compile is 'echo ...' (found on PATH); run is '{binary} {memlim}',
        # i.e. the program we just produced, so there's nothing external to
        # check there.
        lang = languages.Language('id', self.__language_dict())
        assert lang.check_installed() is None

    def test_check_installed_does_not_check_produced_entry_point(self):
        # No compile step, and run is just the (self-contained) source file
        # -- no external program is needed at all.
        vals = self.__language_dict()
        del vals['compile']
        vals['run'] = '{mainfile}'
        lang = languages.Language('id', vals)
        assert lang.check_installed() is None

    def test_check_installed_missing_compiler(self):
        vals = self.__language_dict()
        vals['compile'] = 'definitely_not_a_real_compiler_xyz {files} {binary}'
        lang = languages.Language('id', vals)
        msg = lang.check_installed()
        assert msg is not None
        assert 'compiler' in msg
        assert 'definitely_not_a_real_compiler_xyz' in msg

    def test_check_installed_missing_absolute_path(self):
        vals = self.__language_dict()
        vals['compile'] = '/nonexistent/path/to/compiler {files} {binary}'
        lang = languages.Language('id', vals)
        assert lang.check_installed() is not None

    def test_check_installed_missing_runtime(self):
        # No compile step -- the runtime must still be checked.
        vals = self.__language_dict()
        del vals['compile']
        vals['run'] = 'definitely_not_a_real_runtime_xyz {mainfile}'
        lang = languages.Language('id', vals)
        msg = lang.check_installed()
        assert msg is not None
        assert 'runtime' in msg
        assert 'definitely_not_a_real_runtime_xyz' in msg

    def test_get_compile_command_none_without_compile_step(self):
        vals = self.__language_dict()
        del vals['compile']
        lang = languages.Language('id', vals)
        assert lang.get_compile_command(self.__subs()) is None

    def test_get_compile_command_resolves_executable(self):
        lang = languages.Language('id', self.__language_dict())
        subs = self.__subs()
        command = lang.get_compile_command(subs)
        assert command == [shutil.which('echo'), subs.path, subs.files, subs.binary]

    def test_get_run_command_resolves_executable(self):
        vals = self.__language_dict()
        vals['compile'] = 'echo {mainfile}'
        vals['run'] = 'echo {mainfile}'
        lang = languages.Language('id', vals)
        subs = self.__subs()
        assert lang.get_run_command(subs) == [shutil.which('echo'), subs.mainfile]

    def test_get_run_command_leaves_produced_binary_untouched(self):
        # run is '{binary} {memlim}' in the base dict -- the first token is
        # the program we just compiled, not something to resolve via PATH.
        lang = languages.Language('id', self.__language_dict())
        subs = self.__subs()
        assert lang.get_run_command(subs) == [subs.binary, str(subs.memlim)]

    def test_get_compile_command_splits_multiple_files(self):
        # {files} is a single space-separated string, but each file must
        # end up as its own argument rather than one combined string.
        lang = languages.Language('id', self.__language_dict())
        subs = self.__subs(files='main.foo helper1.bar helper2.bar')
        command = lang.get_compile_command(subs)
        assert command == [shutil.which('echo'), subs.path, 'main.foo', 'helper1.bar', 'helper2.bar', subs.binary]


__EXAMPLES_PATH = os.path.join(os.path.dirname(__file__), 'languages_examples')


def examples_path(test_file):
    return os.path.join(__EXAMPLES_PATH, test_file)


class Languages_test(TestCase):
    def test_empty_languages(self):
        lang = languages.Languages()
        assert lang.languages == {}
        assert lang.detect_language(['foo.cpp', 'foo.c', 'foo.py', 'foo.java']) is None

    def test_duplicate_prio(self):
        lang = languages.Languages()
        config = {
            'c': {
                'name': 'C',
                'priority': 42,
                'files': '*.c',
                'compile': '/usr/bin/gcc -g -O2 -std=gnu99 -static -o {binary} {files} -lm',
                'run': '{binary}',
            },
            'cpp': {
                'name': 'C++',
                'priority': 42,
                'files': '*.cc *.C *.cpp *.cxx *.c++',
                'compile': '/usr/bin/g++ -g -O2 -std=gnu++11 -static -o {binary} {files}',
                'run': '{binary}',
            },
        }

        with pytest.raises(languages.LanguageConfigError):
            lang.update(config)

    def test_invalid_format(self):
        lang = languages.Languages()
        # Dict of strings instead of dict of dict
        conf1 = {'c': 'C'}
        # List instead of dict
        conf2 = [
            {
                'name': 'C',
                'priority': 1,
                'files': '*.c',
                'compile': '/usr/bin/gcc -g -O2 -std=gnu99 -static -o {binary} {files} -lm',
                'run': '{binary}',
            },
            {
                'name': 'C++',
                'priority': 2,
                'files': '*.cc *.C *.cpp *.cxx *.c++',
                'compile': '/usr/bin/g++ -g -O2 -std=gnu++11 -static -o {binary} {files}',
                'run': '{binary}',
            },
        ]
        conf3 = None
        with pytest.raises(languages.LanguageConfigError):
            lang.update(conf1)
        with pytest.raises(languages.LanguageConfigError):
            lang.update(conf2)
        with pytest.raises(languages.LanguageConfigError):
            lang.update(conf3)

    def test_empty(self):
        lang = languages.Languages()
        lang.update({})
        assert lang.languages == {}

    def test_zoo(self):
        langs = languages.Languages()

        zoo = {
            'zoo': {'name': 'Zoo', 'priority': 10, 'files': '*.zoo', 'run': '{binary}'},
            'zoork': {
                'name': 'Zoork',
                'priority': 20,
                'files': '*.zoo',
                'shebang_files': '*.zoo',
                'shebang': '>.*Zoork',
                'run': '{binary}',
            },
            'zoopp': {'name': 'Zoo++', 'priority': 0, 'files': '*.zoo *.zpp', 'run': '{binary}'},
        }

        langs.update(zoo)

        lang = langs.detect_language([examples_path(x) for x in ['src1.zoo']])
        assert lang.lang_id == 'zoo'

        lang = langs.detect_language([examples_path(x) for x in ['src2.zoo']])
        assert lang.lang_id == 'zoork'

        lang = langs.detect_language([examples_path(x) for x in ['src2.zoo', 'src3.zpp']])
        assert lang.lang_id == 'zoopp'

    def test_shebang_gate_only_affects_detection_not_actual_source_files(self):
        """Regression test: once a language has won detection, a helper
        file matching its "files" glob must not be dropped just because it
        individually lacks the shebang that broke the tie against another
        language (see py2nosheb.py below)."""
        langs = languages.Languages()
        langs.update(
            {
                'py2': {
                    'name': 'Python 2',
                    'priority': 60,
                    'files': '*.py *.py2',
                    'shebang_files': '*.py',
                    'shebang': r'^#!.*python2\b',
                    'run': '{mainfile}',
                },
                'py3': {
                    'name': 'Python 3',
                    'priority': 50,
                    'files': '*.py *.py3',
                    'run': '{mainfile}',
                },
            }
        )

        files = [examples_path(x) for x in ['py2main.py', 'py2helper.py2', 'py2nosheb.py']]

        # py2 evidence: py2main.py (shebang matches) + py2helper.py2
        # (unconditional, not gated) = 2.  py3 evidence: py2main.py +
        # py2nosheb.py (both unconditional) = 2.  Tie -> priority decides.
        lang = langs.detect_language(files)
        assert lang.lang_id == 'py2'

        # All three files -- including the shebang-less helper -- belong
        # to the now-settled py2 program.
        assert set(lang.get_source_files(files)) == set(files)
