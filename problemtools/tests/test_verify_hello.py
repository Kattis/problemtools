import pathlib
import problemtools.verifyproblem as verify


def test_load_hello():
    directory = pathlib.Path(__file__).parent / "hello"
    string = str(directory.resolve())

    args = verify.argparser().parse_args([string])
    verify.initialize_logging(args)

    with verify.Problem(string) as p:
        assert p.shortname == "hello"
        # pytest and fork don't go along very well, so just run aspects that work without run
        assert p.config.check(args)
        assert p.attachments.check(args)
        assert p.generators.check(args)
