import plasTeX.Packages.graphics as graphics
from ProblemsetMacros import _graphics_command, clean_width

# Reimplementation of graphicx package because plasTeX is broken and
# annoying.

class includegraphics(_graphics_command):
    args = '* [ options:dict ] file:str'
    packageName = 'graphicx'
    captionable = True

    def invoke(self, tex):
        res = _graphics_command.invoke(self, tex)
        options = self.attributes['options']
        if options is not None:
            height = options.get('height')
            if height is not None:
                self.style['height'] = height
            width = options.get('width')
            if width is not None:
                self.style['width'] = clean_width(width)
        return res

class DeclareGraphicsExtensions(graphics.DeclareGraphicsExtensions):
    packageName = 'graphicx'

class graphicspath(graphics.graphicspath):
    packageName = 'graphicx'
