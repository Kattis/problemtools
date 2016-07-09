"""
This module contains functionality for reading and using configuration
of programming languages.
"""
import fnmatch
import re
import os
import string
import types
import yaml.parser


class LanguageConfigError(Exception):
    """Exception class for errors in language configuration."""
    pass




class Language(object):
    """
    Class representing a single language.
    """

    __KEYS = ['name', 'priority', 'files', 'shebang', 'compile', 'run']
    __VARIABLES = ['path', 'files', 'binary', 'mainfile', 'mainclass', 'memlim']

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

        for (key, value) in values.iteritems():
            # Check type
            if key == 'priority':
                if type(value) != types.IntType:
                    raise LanguageConfigError(
                        'Language %s: priority must be integer but is %s.'
                        % (self.lang_id, type(value)))
            else:
                if type(value) != types.StringType:
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
        entry = variables & set(['binary', 'mainfile', 'mainclass'])
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

    def __init__(self):
        """Create an empty set of languages."""
        self.languages = {}


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


    def update(self, config_file):
        """Update the set with language configuration data from a file.

        Args:
            config_file (str): name of file containing configuration.
                If this file contains (possibly partial) configuration
                for a language already in the set, the configuration
                for that language will be overridden and updated.
        """
        try:
            with open(config_file, 'r') as config:
                data = yaml.safe_load(config.read())
                if data is None:
                    data = {}
        except yaml.parser.ParserError, err:
            raise LanguageConfigError(
                'Config file %s: failed to parse: %s' % (config_file, err))

        if type(data) is not types.DictType:
            raise LanguageConfigError(
                'Config file %s: content must be a dictionary, but is %s.'
                % (config_file, type(data)))

        for (lang_id, lang_spec) in data.iteritems():
            if type(lang_id) is not types.StringType:
                raise LanguageConfigError(
                    'Config file %s: language IDs must be strings, but %s is %s.'
                    % (config_file, lang_id, type(lang_id)))

            if type(lang_spec) is not types.DictType:
                raise LanguageConfigError(
                    'Config file %s: language spec must be a dictionary, but spec of language %s is %s.'
                    % (config_file, lang_id, type(lang_spec)))

            if lang_id not in self.languages:
                self.languages[lang_id] = Language(lang_id, lang_spec)
            else:
                self.languages[lang_id].update(lang_spec)

        priorities = {}
        for (lang_id, lang) in self.languages.iteritems():
            if lang.priority in priorities:
                raise LanguageConfigError(
                    'Languages %s and %s both have priority %d.'
                    % (lang_id, priorities[lang.priority], lang.priority))
            priorities[lang.priority] = lang_id



def load_language_config(paths):
    """Load language configuration from a list of possible files.

    Args:
        paths (list of str): list of file names, paths to
            configuration files.  Files in the list that do not exist
            will be silently ignored.  If the same language is defined
            in more than one file, the one appearing last in the list
            takes precedence.

    Returns:
        Languages object for the set of languages in the given config
        files.
    """
    res = Languages()
    for path in paths:
        if os.path.isfile(path):
            res.update(path)
    return res


def load_language_config_default_paths():
    """Load language configuration from the problemtools default locations.

    Returns:
        Languages object for the set of languages defined by the
        default config files.
    """
    return load_language_config([os.path.join(os.path.dirname(__file__),
                                              'languages.yaml')])
