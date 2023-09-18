"""
This module contains functionality for reading and using configuration
of programming languages.
"""
import fnmatch
import re
import string

from . import config

class LanguageConfigError(Exception):
    """Exception class for errors in language configuration."""
    pass




class Language(object):
    """
    Class representing a single language.
    """

    __KEYS = ['name', 'priority', 'files', 'shebang', 'compile', 'run']
    __VARIABLES = ['path', 'files', 'binary', 'mainfile', 'mainclass', 'Mainclass', 'memlim']

    def __init__(self, lang_id, lang_spec):
        """Construct language object

        Args:
            lang_id (str): language identifier
            lang_spec (dict): dictionary containing the specification
                of the language.
        """
        if not re.match('[a-z][a-z0-9]*', lang_id):
            raise LanguageConfigError('Invalid language ID "%s"' % lang_id)
        self.lang_id = lang_id
        self.name = None
        self.priority = None
        self.files = None
        self.shebang = None
        self.compile = None
        self.run = None
        self.update(lang_spec)


    def get_source_files(self, file_list):
        """Given a list of files, determine which ones would be considered
        source files for the language.

        Args:
            file_list (list of str): list of file names
        """
        return [file_name for file_name in file_list
                if (any(fnmatch.fnmatch(file_name, glob)
                        for glob in self.files)
                    and
                    self.__matches_shebang(file_name))]


    def update(self, values):
        """Update a language specification with new values.

        Args:
            values (dict): dictionary containing new values for some
                subset of the language properties.
        """

        # Check that all provided values are known keys
        for unknown in set(values)-set(Language.__KEYS):
            raise LanguageConfigError(
                'Unknown key "%s" specified for language %s'
                % (unknown, self.lang_id))

        for (key, value) in values.items():
            # Check type
            if key == 'priority':
                if not isinstance(value, int):
                    raise LanguageConfigError(
                        'Language %s: priority must be integer but is %s.'
                        % (self.lang_id, type(value)))
            else:
                if not isinstance(value, str):
                    raise LanguageConfigError(
                        'Language %s: %s must be string but is %s.'
                        % (self.lang_id, key, type(value)))

            # Save the value
            if key == 'shebang':
                # Compile shebang RE
                self.shebang = re.compile(value)
            elif key == 'files':
                # Split glob patterns
                self.files = value.split()
            else:
                # Other keys, just copy the value
                self.__dict__[key] = value

        self.__check()


    def __check(self):
        """Check that the language specification is valid (all mandatory
        fields provided, all metavariables used in compile/run
        commands valid, and uniquely defined entry point.
        """
        # Check that all mandatory fields are provided
        if self.name is None:
            raise LanguageConfigError(
                'Language %s has no name' % self.lang_id)
        if self.priority is None:
            raise LanguageConfigError(
                'Language %s has no priority' % self.lang_id)
        if self.files is None:
            raise LanguageConfigError(

        'Language %s has no files glob' % self.lang_id)
        if self.run is None:
            raise LanguageConfigError(
                'Language %s has no run command' % self.lang_id)

        # Check that all variables appearing are valid
        variables = Language.__variables_in_command(self.run)
        if self.compile is not None:
            variables = variables | Language.__variables_in_command(self.compile)
        for unknown in variables - set(Language.__VARIABLES):
            raise LanguageConfigError(
                'Unknown variable "{%s}" used for language %s'
                % (unknown, self.lang_id))

        # Check for uniquely defined entry point
        entry = variables & set(['binary', 'mainfile', 'mainclass', 'Mainclass'])
        if len(entry) == 0:
            raise LanguageConfigError(
                'No entry point variable used for language %s' % self.lang_id)
        if len(entry) > 1:
            raise LanguageConfigError(
                'More than one entry point type variable used for language %s'
                % self.lang_id)


    @staticmethod
    def __variables_in_command(cmd):
        """List all meta-variables appearing in a string."""
        formatter = string.Formatter()
        return set(field for _, field, _, _ in formatter.parse(cmd)
                   if field is not None)


    def __matches_shebang(self, filename):
        """Check if a file matches the shebang rule for the language."""
        if self.shebang is None:
            return True
        with open(filename, 'r') as f_in:
            shebang_line = f_in.readline()
        return self.shebang.search(shebang_line) is not None






class Languages(object):
    """A set of languages."""

    def __init__(self, data=None):
        """Create a set of languages from a dict.

        Args:
            data (dict): dictonary containing configuration.
                If None, resulting set of languages is empty.
                See documentation of update() method below for details.
        """
        self.languages = {}
        if data is not None:
            self.update(data)


    def detect_language(self, file_list):
        """Auto-detect language for a set of files.

        Args:
            file_list (list of str): list of file names

        Returns:
            Language object for the detected language or None if the
            list of files did not match any language in the set.
        """
        result = None
        src = []
        prio = 1e99
        for lang in self.languages.values():
            lang_src = lang.get_source_files(file_list)
            if (len(lang_src), lang.priority) > (len(src), prio):
                result = lang
                src = lang_src
                prio = lang.priority
        return result

    def get(self, lang_id):
        if not isinstance(lang_id, str):
            raise LanguageConfigError(
                'Config file error: language IDs must be strings, but %s is %s.'
                % (lang_id, type(lang_id)))
        return self.languages.get(lang_id, None)

    def update(self, data):
        """Update the set with language configuration data from a dict.

        Args:
            data (dict): dictionary containing configuration.
                If this dictionary contains (possibly partial) configuration
                for a language already in the set, the configuration
                for that language will be overridden and updated.
        """
        if not isinstance(data, dict):
            raise LanguageConfigError(
                'Config file error: content must be a dictionary, but is %s.'
                % (type(data)))

        for (lang_id, lang_spec) in data.items():
            if not isinstance(lang_id, str):
                raise LanguageConfigError(
                    'Config file error: language IDs must be strings, but %s is %s.'
                    % (lang_id, type(lang_id)))

            if not isinstance(lang_spec, (dict, Language)):
                raise LanguageConfigError(
                    'Config file error: language spec must be a dictionary, but spec of language %s is %s.'
                    % (lang_id, type(lang_spec)))


            if isinstance(lang_spec, Language):
                self.languages[lang_id] = lang_spec
            elif lang_id not in self.languages:
                self.languages[lang_id] = Language(lang_id, lang_spec)
            else:
                self.languages[lang_id].update(lang_spec)

        priorities = {}
        for (lang_id, lang) in self.languages.items():
            if lang.priority in priorities:
                raise LanguageConfigError(
                    'Languages %s and %s both have priority %d.'
                    % (lang_id, priorities[lang.priority], lang.priority))
            priorities[lang.priority] = lang_id


def load_language_config():
    """Load language configuration.

    Returns:
        Languages object for the set of languages.
    """
    return Languages(config.load_config('languages.yaml'))
