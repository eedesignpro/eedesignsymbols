"""Generate KiCad symbols from template drawings, one symbol per pin ordering.

Layering, deliberately:

- ``generators``: one module per part family, configuration over the shared
  machinery wherever the shape allows.
- ``templates``: the template drawings the generators copy from. Not Python.
- ``writing``: how a generator finds its templates and writes its output. A
  library with its own rules supplies its own route.
- ``symbol_fields`` and ``format_version``: two small KiCad helpers.
- ``bbox``: how much room a symbol takes on a sheet.
- ``preview_tools``: SVG renders and an HTML gallery of written symbols.
- ``version``: the provenance stamp this tool mints from its own git tree.
"""

__all__ = ["bbox", "generators", "version", "writing"]
