#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import print_function
import sys
import os
import glob
import tempfile
import shutil
from argparse import ArgumentParser
from multiprocessing import Pool, cpu_count

from .verifyproblem import ProblemAspect, Problem, is_RTE, argparser_basic_arguments, initialize_logging

VISUALIZER_EXTENSIONS = ['png', 'jpg', 'jpeg', 'svg']


def argparser():
    parser = ArgumentParser(description='Generate test data for a problem package in the Kattis problem format.')
    parser.add_argument('-g', '--generate',
                        action='store_true',
                        help='generate test data')
    parser.add_argument('-c', '--clean',
                        action='store_true',
                        help='clean up generated files')
    parser.add_argument('-C', '--clean_all',
                        action='store_true',
                        help='clean up generated and unrecognized files')
    parser.add_argument('-n', '--dry_run',
                        action='store_true',
                        help='don\'t actually do anything')
    parser.add_argument('-j', '--parallelism',
                        type=int,
                        default=None,
                        help='level of parallelism')
    argparser_basic_arguments(parser)
    parser.add_argument('problemdir', nargs='+')
    return parser


def clean(prob, args):
    base_path = os.path.join(prob.probdir, 'data')

    testcases = {
        case['path']: case
        for case in prob.generators._testcases
    }

    def walk(name, path):
        case_count = 0
        cases = set()
        empty = True
        for fname in sorted(os.listdir(path)):
            curpath = os.path.join(path, fname)
            nice_path = os.path.relpath(curpath, base_path)
            if '.' in fname:
                fname, ext = fname.split('.', 1)
            else:
                ext = ''
            curname = '%s/%s' % (name, fname)

            if os.path.isdir(curpath):
                next_empty, next_cases = walk(curname, curpath)
                case_count += next_cases
                if next_empty:
                    if not args.dry_run:
                        os.rmdir(curpath)
                else:
                    empty = False
            else:
                remove = args.clean_all
                is_case = False
                if (fname, ext) == ('testdata', 'yaml'):
                    # TODO: Handle this
                    remove = False
                elif curname in testcases:
                    is_case = True
                    case = testcases[curname]
                    if ext == 'in':
                        remove = not case['manual']
                    elif ext == 'ans':
                        remove = case['solution'] is not None
                    elif ext in VISUALIZER_EXTENSIONS:
                        remove = case['visualizer'] is not None

                if remove:
                    prob.generators.msg('Removing %s' % nice_path)
                    if not args.dry_run:
                        os.unlink(curpath)
                    if is_case and curname not in cases:
                        cases.add(curname)
                        case_count += 1
                else:
                    empty = False

        return empty, case_count

    cases_cleaned = 0
    for directory in prob.generators._data_directories:
        path = os.path.join(base_path, directory)
        if os.path.isdir(path):
            cases_cleaned += walk('data/%s' % directory, path)[1]
    return cases_cleaned


class GenerateState:
    prob = None
    args = None

def generate_case(case_idx):
    prob = GenerateState.prob
    args = GenerateState.args
    case = prob.generators._testcases[case_idx]

    steps = [
        ('input', True, None, '.in'),
        ('solution', False, '.in', '.ans'),
        ('visualizer', False, '.in', None),
    ]

    try:
        tmp_dir = tempfile.mkdtemp(prefix='gencase', dir=prob.tmpdir)
        staging_dir = os.path.join(tmp_dir, 'staging')
        os.mkdir(staging_dir)
        out_dir = os.path.join(*([prob.probdir] + case['path'].split('/')[:-1]))
        name = case['path'].split('/')[-1]
        ok = args.dry_run or os.path.isdir(out_dir)
        for (gen_type, mandatory, in_ext, out_ext) in steps:
            if not ok:
                break
            prog = case.get(gen_type)
            if prog is None:
                ok = not mandatory
                continue
            prog, pargs = prog
            prog = prob.generators._generators.get(prog)
            if prog is None:
                ok = not mandatory
                continue

            if gen_type == 'input':
                prob.generators.msg('Generating %s' % case['path'].replace('data/', '', 1))

            staging_count = len(os.listdir(staging_dir))

            if isinstance(prog, str):
                if out_ext is not None:
                    shutil.copyfile(prog, os.path.join(staging_dir, name + out_ext))
            else:
                errfile = os.path.join(tmp_dir, 'error')
                params = {'args': pargs, 'errfile': errfile}
                if in_ext is not None:
                    params['infile'] = os.path.join(staging_dir, name + in_ext)
                if out_ext is not None:
                    outfile = os.path.join(tmp_dir, 'output')
                    params['outfile'] = outfile

                # TODO: Change working directory
                status, _ = prog.run(**params)
                if is_RTE(status):
                    ok = not mandatory
                    stderr = None
                    if os.path.isfile(errfile):
                        with open(errfile, 'r') as f:
                            stderr = f.read()
                    prob.generators.error('Generator of type %s crashed with status %s' % (gen_type, status), stderr)
                    continue

                if out_ext is not None:
                    dest = os.path.join(staging_dir, name + out_ext)
                    if not os.path.isfile(dest):
                        shutil.copyfile(outfile, dest)

            if len(os.listdir(staging_dir)) == staging_count:
                prob.generators.warning('Generator of type %s generated no files' % gen_type)

        if ok:
            for fname in os.listdir(staging_dir):
                if '.' not in fname:
                    continue
                curname, ext = fname.split('.', 1)
                if curname == name and ext in ['in', 'ans'] + VISUALIZER_EXTENSIONS:
                    fpath = os.path.join(staging_dir, fname)
                    if os.path.isfile(fpath) and not args.dry_run:
                        shutil.copyfile(fpath, os.path.join(out_dir, fname))
        return ok
    finally:
        shutil.rmtree(tmp_dir)


def generate(prob, args):

    # Create directory structure
    created = set()
    for case in prob.generators._testcases:
        path = os.path.join(*([prob.probdir] + case['path'].split('/')[:-1]))
        if path not in created:
            created.add(path)
            if not os.path.isdir(path) and not args.dry_run:
                try:
                    os.makedirs(path)
                except Exception as e:
                    prob.generators.error('Could not create path %s' % path, e)

    # Generate test cases in parallel
    GenerateState.prob = prob
    GenerateState.args = args
    pool = Pool(args.parallelism)
    res = pool.map_async(generate_case, range(len(prob.generators._testcases)))
    while not res.ready():
        # Use async polling for better KeyboardInterrupt handling
        res.wait(1)
    return sum(res.get())


def main():
    args = argparser().parse_args()
    args.parts = ['generators']
    if args.clean_all:
        args.clean = True
    if not args.clean:
        args.generate = True
    args.compile_generators = args.generate
    if args.parallelism is None:
        args.parallelism = cpu_count()
    initialize_logging(args)

    total_errors = 0
    for problemdir in args.problemdir:
        print('Loading problem %s' % os.path.basename(os.path.realpath(problemdir)))
        with Problem(problemdir) as prob:
            prob.check(args)

            def p(x):
                return '' if x == 1 else 's'

            status = ''
            if args.clean:
                cnt = clean(prob, args)
                status += '%d case%s cleaned, ' % (cnt, p(cnt))
            if args.generate:
                cnt = generate(prob, args)
                status += '%d case%s generated, ' % (cnt, p(cnt))

            [errors, warnings] = [ProblemAspect.errors, ProblemAspect.warnings]
            print("%s processed: %s%d error%s, %d warning%s" % (prob.shortname, status, errors, p(errors), warnings, p(warnings)))
            total_errors += errors

    sys.exit(1 if total_errors > 0 else 0)

if __name__ == '__main__':
    main()
