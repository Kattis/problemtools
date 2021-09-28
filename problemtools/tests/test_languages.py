# -*- coding: utf-8 -*-
from unittest import TestCase
import pytest
import os
import re

from problemtools import languages


class Language_test(TestCase):
    @staticmethod
    def __language_dict():
        return {'name': 'A Language',
                'priority': 100,
                'files': '*.foo *.bar',
                'shebang': '.*',
                'compile': 'echo {path} {files} {binary}',
                'run': '{binary} {memlim}'
                }

    def test_create(self):
        lang = languages.Language('langid', self.__language_dict())

    def test_update(self):
        lang = languages.Language('langid', self.__language_dict())

        lang.update({'priority': -1})
        assert lang.priority == -1

        lang.update({'name': 'New name'})
        assert lang.name == 'New name'

        lang.update({'files': '*'})
        assert lang.files == ['*']

        lang.update({'shebang': 'new.*end'})
        assert lang.shebang.match('newfilend')

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
            languages.Language(None, vals)
        with pytest.raises(TypeError):
            languages.Language(42, vals)
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
        languages.Language('id', vals)


    def test_invalid_shebang(self):
        vals = self.__language_dict()
        vals['shebang'] = '(Not an RE'
        with pytest.raises(re.error):
            languages.Language('id', vals)


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



__EXAMPLES_PATH = os.path.join(os.path.dirname(__file__),
                              'languages_examples')


def examples_path(test_file):
    return os.path.join(__EXAMPLES_PATH, test_file)


class Languages_test(TestCase):
    def test_empty_languages(self):
        lang = languages.Languages()
        assert lang.languages == {}
        assert lang.detect_language(
            ['foo.cpp', 'foo.c', 'foo.py','foo.java']) is None


    def test_duplicate_prio(self):
        lang = languages.Languages()
        config = {'c': {'name': "C",
                        'priority': 42,
                        'files': "*.c",
                        'compile': "/usr/bin/gcc -g -O2 -std=gnu99 -static -o {binary} {files} -lm",
                        'run': "{binary}"},
                  'cpp': {'name': "C++",
                          'priority': 42,
                          'files': "*.cc *.C *.cpp *.cxx *.c++",
                          'compile': "/usr/bin/g++ -g -O2 -std=gnu++11 -static -o {binary} {files}",
                          'run': "{binary}"}}

        with pytest.raises(languages.LanguageConfigError):
            lang.update(config)


    def test_invalid_format(self):
        lang = languages.Languages()
        # Dict of strings instead of dict of dict
        conf1 = {'c': 'C'}
        # List instead of dict
        conf2 = [{'name': "C",
                  'priority': 1,
                  'files': "*.c",
                  'compile': "/usr/bin/gcc -g -O2 -std=gnu99 -static -o {binary} {files} -lm",
                  'run': "{binary}"},
                 {'name': "C++",
                  'priority': 2,
                  'files': "*.cc *.C *.cpp *.cxx *.c++",
                  'compile': "/usr/bin/g++ -g -O2 -std=gnu++11 -static -o {binary} {files}",
                  'run': "{binary}"}]
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

        zoo = {'zoo': {'name': "Zoo",
                       'priority': 10,
                       'files': "*.zoo",
                       'run': "{binary}"},
               'zoork': {'name': "Zoork",
                         'priority': 20,
                         'files': "*.zoo",
                         'shebang': ">.*Zoork",
                         'run': "{binary}"},
               'zoopp': {'name': "Zoo++",
                         'priority': 0,
                         'files': "*.zoo *.zpp",
                         'run': "{binary}"}
               }

        langs.update(zoo)

        lang = langs.detect_language([examples_path(x) for x in ['src1.zoo']])
        assert lang.lang_id == 'zoo'

        lang = langs.detect_language([examples_path(x) for x in ['src2.zoo']])
        assert lang.lang_id == 'zoork'

        lang = langs.detect_language([examples_path(x) for x in ['src2.zoo', 'src3.zpp']])
        assert lang.lang_id == 'zoopp'
