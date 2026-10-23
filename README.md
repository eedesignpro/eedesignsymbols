# eedesignsymbols

Generate KiCad 10 schematic symbols from template drawings. The tool makes one
symbol for each pin ordering of a part family.

**Status: early.** The tool reads and writes KiCad files through
`eedesigncore` 0.38.0. No package index carries `eedesigncore` yet. Install it from
its source first, then install this package.

## What it does

A diode, a transistor, or an op-amp is drawn once, as a template. What differs
between real parts is which package pin carries which terminal. The tool copies
the template and gives each pin its number for one ordering. The drawing, the
pin positions, the pin names, and the electrical types do not change.

For example, the N-channel MOSFET template gives six symbols, one for each
order of gate, source, and drain:

```
_Q_NMOS_SYMGEN_TEMPLATE  ->  Q_NMOS_GSD_SYMGEN   (pin 1 = G, 2 = S, 3 = D)
_Q_NPN_SYMGEN_TEMPLATE   ->  Q_NPN_BCE_SYMGEN    (pin 1 = B, 2 = C, 3 = E)
```

The op-amp generator reads a configuration file. Each row names the pins to keep,
their numbers, and their electrical types, and the tool removes the other pins.

## Part families

| Command module | Terminals | Templates | Symbols |
|---|---|---|---|
| `mosfet` | G, S, D | N-channel, P-channel | 12 |
| `bjt` | B, C, E | NPN, PNP | 12 |
| `igbt` | G, C, E | N-channel | 6 |
| `jfet` | G, S, D | N-channel, P-channel | 12 |
| `diode` | A, K | six diode drawings | 6 |
| `diode` | A1, A2 | two bidirectional drawings | 2 |
| `led` | A, K and A, K, MP | LED, LED with mounting pad | 2 |
| `opamp.single` | per configuration row | single op-amp | 8 |

## The templates

The package ships 22 template drawings in `src/eedesignsymbols/templates/`. Each
file holds one symbol and is named for it, for example
`_Q_NMOS_SYMGEN_TEMPLATE.kicad_sym`. A template carries its terminal names as
its pin numbers, so it is not a usable part. Four templates have no generator
yet: the two GaN drawings, the Kelvin-source MOSFET, and the LED with a thermal
pad.

## Run a generator

```
python -m eedesignsymbols.generators.mosfet --dir <output folder>
```

Each output is one file, `<symbol name>.kicad_sym`, with the KiCad fields only:
`Reference`, `Value`, `Footprint`, `Datasheet`, `Description`, and the keywords of its
template. A rerun leaves a file alone when its content would not change.

- `--dir` names the output folder.
- `--templates` reads the template files from another folder.
- `--dry-run` reports what a run would write and writes nothing.
- `--no-preview` skips the HTML preview of the written symbols.

## Tests

```
python -m pytest
```

Some tests read reference symbol files that this copy does not carry. Those
tests skip.

## License

GNU General Public License, version 3 or later. See `LICENSE`.

Ten template drawings are adapted from symbols in the KiCad symbol library and are
licensed under CC BY-SA 4.0. `src/eedesignsymbols/templates/NOTICE` names them and gives
the attribution.

## Support

This code is provided as-is. SeeScan, Inc. makes no commitment to support it,
maintain it, or answer issues and pull requests.
