"""Op-amp generators: single now, dual later.

Unlike the permutation generators in the parent package, an op-amp
generator adds and removes pins and their graphics per part, rather than
only renumbering a fixed set. See ``single.py``'s module docstring for the
copy-edit rule, and ``config.py`` for the config schema that drives it.

Deliberately imports nothing here, matching ``eedesignsymbols.generators``
itself: importing ``single`` eagerly would make ``python -m
eedesignsymbols.generators.opamp.single`` re-import it as ``__main__`` and warn.
"""
