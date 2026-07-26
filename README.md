# Phil Kelly's Manx Dictionary — data

Phil Kelly's English–Manx / Manx–English dictionary, converted from his
TshwaneLex XML export to JSON. Dictionary content © Phil Kelly.

| File | What it is |
|---|---|
| `source/Jan26.xml` | Master: TshwaneLex export received January 2026 |
| `tools/convert.py` | The conversion (Python 3, stdlib only) |
| `english-manx.json`, `manx-english.json` | Rich format: everything in the export |
| `english.json`, `manx.json` | Legacy flat format, drop-in for existing consumers |

Regenerate everything with:

```sh
python3 tools/convert.py
```

## The export

The XML is one `<Language>` block holding both directions concatenated:
English→Manx first, ending at the bookkeeping row `zzz - © Phil Kelly`, then
Manx→English, ending at a dated marker (`zzz - Jan 2026`). The converter
splits on the first marker (`--split-marker` if a future export renames it)
and fails loudly on any element or attribute it has not seen before, so a
future export with new fields cannot silently lose data.

## Rich format

`{"meta": {...}, "entries": [...]}`, one entry per line, document order,
empty fields omitted. Marker rows are kept (listed in `meta.markerRows`).

```json
{
  "headword": "aah",
  "homonymNumber": 1,
  "partOfSpeech": ["fem"],
  "usageLabels": ["pl -yn"],
  "etymology": "O.Ir. áth",
  "deriv": "Ir. áth",
  "notes": "Phill. aiaght",
  "senses": [
    {
      "senseNumber": 1,
      "partOfSpeech": ["noun"],
      "translations": ["drift", "ford"],
      "definitions": ["(ny)"],
      "examples": [
        {"text": "…", "translation": "…", "source": "Bible"}
      ],
      "senses": [],
      "references": []
    }
  ],
  "references": [{"lemmaId": 925180, "type": 6}],
  "created": "2008-04-30 13:29:14",
  "modified": "2022-02-07 09:16:58"
}
```

(Composite illustration — real entries carry only the fields they have.)

Field notes:

- **`partOfSpeech`** (lemma- and sense-level, comma-values split into arrays):
  on the English side this is a conventional POS (`noun`, `adjective`, …).
  On the Manx side it mostly encodes **gender and grammatical form** —
  `fem` (10,352 entries), `masc.`, `genitive`, `voc.`, `emph.`, `comp/sup`,
  `Imperative`, … A sense-level value overrides the lemma-level one.
- **`usageLabels`**: plural suffixes of the headword (`pl -yn`, `pl -syn`,
  `pl -ghyn`, `pl -aghyn`).
- **`deriv` / `etymology`**: cognates and origins (`Ir.`, `Sc.G.`, `O.Ir.`,
  `L.` …).
- **`notes`**: miscellany — Phillips-manuscript spellings (`Phill. …`),
  parishes for place-names, glosses.
- **`definitions`**: mostly short disambiguators such as `(ny)`, `(to)`.
- **`examples`**: `text` is in the headword's language; `translation` is
  often absent (especially for Bible citations). `source` values include
  `Bible`, `DF`, `JJK`, `Carn`, `Dhoor`, `PB1610`, …
- **`references`**: cross-references. `lemmaId`/`type` are
  TshwaneLex-internal database IDs **not resolvable from this export** (the
  export carries no lemma IDs). Preserved verbatim; resolving them would
  need a future export that includes each lemma's own ID.
- **`senses.senses`**: occasional nested sub-senses (alternative translation
  groups or attached quotations).

Known data quirks, preserved faithfully: one empty-headword lemma with no
content, a handful of placeholder lemmas with no translations (they become
`[]` in the legacy files, as in previous releases), and untrimmed
whitespace inside some values.

## Legacy format

Same shape as the 2021 release (and what `cregeen-nvh`'s `phil-kelly`
round-trip emits / `manx-corpus-search` vendors as `Resources/*.json`): a
minified `{headword: [translation, ...]}` map with no trailing newline.
Derived from the rich entries by lowercasing headwords, merging homonyms and
case-collisions in document order, flattening nested senses, and keeping
marker rows and zero-translation entries — matching the previous release's
behaviour so consumers need no code changes.
