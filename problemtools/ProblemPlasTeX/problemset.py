from typing import Any


# plasTeX always looks for a Python implementation of a package before falling
# back to the LaTeX one, and warns when it has to fall back. We want the LaTeX
# implementation (with ProblemsetMacros overriding parts of it), so provide this
# stub which loads problemset.cls explicitly to avoid the warning.
def ProcessOptions(options: dict, document: Any) -> None:
    tex = document.userdata['base_tex_instance']
    tex.loadPackage('problemset.cls', options)
