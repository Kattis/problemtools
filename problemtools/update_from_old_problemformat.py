# -*- coding: utf-8 -*-

from __future__ import print_function
from optparse import OptionParser
import glob
import os
import yaml


def update(problemdir):
    probyaml = os.path.join(problemdir, 'problem.yaml')
    if not os.path.isfile(probyaml):
        raise Exception('Could not find %s' % probyaml)
    config = yaml.safe_load('%s' % open(probyaml, 'r').read())

    stmts = glob.glob(os.path.join(problemdir, 'problem_statement/problem.tex'))
    stmts.extend(glob.glob(os.path.join(problemdir, 'problem_statement/problem.[a-z][a-z].tex')))
    yaml_changed = False

    if 'name' in config:
        print('Move problem name "%s" to these problem statement files: %s' % (config['name'], stmts))
        
        for f in stmts:
            stmt = open(f, 'r').read()
            if stmt.find('\\problemname{') != -1:
                print('   Statement %s already has a problemname, skipping' % f)
                continue
            newstmt = '\problemname{%s}\n\n%s' % (config['name'], stmt)
            open(f, 'w').write(newstmt)
        del config['name']
        yaml_changed = True

    if 'validator' in config:
        validator_flags = config['validator'].split()
        validation = 'default'
        if validator_flags[0] == 'custom':
            validation = 'custom'
            validator_flags = validator_flags[1:]
        validator_flags = ' '.join(validator_flags)
        print('Old validator option exists, moving to validation: %s, validator_flags: %s' % (validation, validator_flags))
        config['validation'] = validation
        if validator_flags != '':
            config['validator_flags'] = validator_flags
        del config['validator']
        yaml_changed = True

    if yaml_changed:
        open(probyaml, 'w').write(yaml.dump(config, default_flow_style = False, allow_unicode = True))


if __name__ == '__main__':
    parser = OptionParser(usage="usage: %prog problems")
    (options, args) = parser.parse_args()
    if not args:
        parser.print_help()
        
    for dir in args:
        try:
            print('Updating %s' % dir)
            update(dir)
        except Exception as e:
            print('Update FAILED: %s' % e)

