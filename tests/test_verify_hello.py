import pathlib
import problemtools.verifyproblem as verify


def test_load_hello():
    directory = pathlib.Path(__file__).parent / 'hello'
    string = str(directory.resolve())

    args = verify.argparser().parse_args([string])
    verify.initialize_logging(args)
    context = verify.Context(args, None)

    with verify.Problem(string, args) as p:
        p.load()
        assert p.shortname == 'hello'
        # pytest and fork don't go along very well, so just run aspects that work without run
        assert p.config.check(context)
        assert p.attachments.check(context)
        assert p.is_pass_fail()
        assert not p.is_scoring()
        assert not p.is_interactive()
        assert not p.is_multi_pass()
        assert not p.is_submit_answer()


def test_load_twice():
    directory = pathlib.Path(__file__).parent / 'hello'
    string = str(directory.resolve())

    args = verify.argparser().parse_args([string])
    with verify.Problem(string, args) as p:
        p.load()
        p.load()
