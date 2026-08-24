import os
import re
import shutil
import subprocess
from typing import Any, Final

from plasTeX.Filenames import Filenames
from plasTeX.Imagers import Image
from plasTeX.Logging import getLogger
from plasTeX.Renderers.PageTemplate import Renderer

from problemtools.template import TemplateError

log = getLogger()


# Adapted from plasTeX.Imagers.Imager class
class ImageConverter:
    fileExtension = '.png'
    imageAttrs = ''
    imageUnits = ''

    imageTypes: Final[list[str]] = ['.png', '.jpg', '.jpeg', '.gif']  # , '.svg']
    imageConversion: Final[dict[str, tuple[str, list[str]]]] = {
        '.pdf': ('.png', ['gs', '-dUseCropBox', '-sDEVICE=pngalpha', '-r300', '-o'])
    }

    def __init__(self, document: Any) -> None:
        self.config = document.config
        self.ownerDocument = document

        # Cache of already seen images
        self.staticimages: dict[str, Image] = {}

        # Filename generator
        self.newFilename = Filenames(
            self.config['images'].get('filenames'),
            None,
            variables={'jobname': document.userdata.get('jobname', '')},
            extension=self.fileExtension,
            invalid={},
        )

    def close(self) -> None:
        return

    def getImage(self, node: Any) -> Image | None:
        name = getattr(node, 'imageoverride', None)
        if name is None:
            log.error(f'Image handler called for non-image node "{node.source}"')
            return None

        if name in self.staticimages:
            return self.staticimages[name]

        oldext = os.path.splitext(name)[1]
        path = self.newFilename()

        try:
            directory = os.path.dirname(path)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory)
            if oldext in self.imageConversion:
                # Need to convert image
                newext = self.imageConversion[oldext][0]
                path = os.path.splitext(path)[0] + newext
                cmd = self.imageConversion[oldext][1] + [path, name]
                result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
                if result.returncode:
                    log.error(
                        'Failed to convert %s image "%s" to %s.\n%s', oldext, name, newext, result.stderr.decode(errors='replace')
                    )
            else:
                # Just copy it
                path = os.path.splitext(path)[0] + oldext
                shutil.copyfile(name, path)
            img = Image(path, self.ownerDocument.config['images'])
            self.staticimages[name] = img
            return img

        except Exception as msg:
            log.warning(f'{msg} in image "{name}".')
        return None


class ProblemRenderer(Renderer):
    """Renderer for ProblemHTML documents"""

    fileExtension = '.html'
    # Overrides plasTeX's Renderer.imageTypes/vectorImageTypes, which are untyped instance
    # attributes (assigned as bare `= []` with no ClassVar/Final) - mypy treats overriding them
    # with ClassVar or Final as a Liskov violation, so we can't annotate these as constant.
    imageTypes: list[str] = ['.png', '.jpg', '.jpeg', '.gif']  # noqa: RUF012
    vectorImageTypes: list[str] = ['.svg']  # noqa: RUF012

    def render(self, document: Any, postProcess: Any = None) -> None:
        templatepaths = [
            os.path.join(os.path.dirname(__file__), '../templates/html'),
            os.path.join(os.path.dirname(__file__), '../../templates/html'),
            '/usr/lib/problemtools/templates/html',
        ]
        templatepath = None
        for p in templatepaths:
            if os.path.isdir(p):
                templatepath = p
                break
        if templatepath is None:
            raise TemplateError('Could not find templates needed for conversion to HTML')

        # Ugly but unfortunately PlasTeX is quite inflexible when it comes to
        # configuring where to search for template files
        os.environ['ProblemRendererTEMPLATES'] = templatepath

        # Gigantic ugliness to cope with PlasTeX problem that prevents
        # plastex from resetting list of invalid filenames when doing multiple renderings.
        f = Filenames('blah.html', {}, {}, 'html')
        f.invalid.clear()

        # Setup our own mini-imager which just does copying and converts pdfs to png
        self.imager = ImageConverter(document)

        Renderer.render(self, document)

    def processFileContent(self, document: Any, s: str) -> str:
        s = Renderer.processFileContent(self, document, s)

        # Force XHTML syntax on empty tags
        s = re.compile(r'(<(?:hr|br|img|link|meta)\b.*?)\s*/?\s*(>)', re.IGNORECASE | re.DOTALL).sub(r'\1 /\2', s)

        # Remove empty paragraphs
        s = re.compile(r'<p>\s*</p>', re.IGNORECASE).sub(r'', s)

        # Add a non-breaking space to empty table cells
        s = re.compile(r'(<(td|th)\b[^>]*>)\s*(</\2>)', re.IGNORECASE).sub(r'\1&nbsp;\3', s)

        return s
