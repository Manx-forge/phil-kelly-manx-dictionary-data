#!/usr/bin/env python3
"""Convert Phil Kelly's Manx dictionary from TshwaneLex XML to JSON.

The XML export contains a single <Language> block holding both dictionary
directions concatenated: English->Manx first, then Manx->English. The last
English lemma is a bookkeeping marker row (--split-marker, default
"zzz - © Phil Kelly"); everything after it is the Manx->English dictionary,
whose own final row is a dated marker (e.g. "zzz - Jan 2026").

Outputs, per direction:
  english-manx.json / manx-english.json
      Rich format: every lemma in document order with all non-empty fields
      (part of speech, homonym number, usage labels / plural suffixes,
      derivations, etymology, notes, senses, examples with sources,
      definitions, cross-references). Marker rows are included and listed
      in meta.markerRows.
  english.json / manx.json
      Legacy flat format, drop-in compatible with the previous release:
      {lowercased headword: [translation, ...]}, homonyms and case-collisions
      merged in document order, nested senses flattened, zero-translation
      lemmas kept as empty arrays, marker rows kept, minified, no trailing
      newline.

The parser is deliberately strict: any element, attribute, or text content
not seen in the Jan 2026 export raises an error, so a future export with new
fields fails loudly instead of silently losing data.
"""

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Exact attribute sets observed in the export. TshwaneLex always writes every
# attribute (empty string when unset), so we require set equality.
EXPECTED_ATTRS = {
    "Dictionary": set(),
    "Language": set(),
    "Lemma": {"Incomplete", "LemmaSign", "HomonymNumber", "Pronunciation",
              "Deriv", "Etymology", "Notes", "Frequency", "Modified",
              "Created", "UsageLabel", "PartOfSpeech"},
    "Sense": {"SenseNumber", "UsageLabel", "PartOfSpeech"},
    "TE": {"TE"},
    "Example": {"Example", "Translation", "Source"},
    "Definition": {"Definition"},
    "References": set(),
    "reflemma": {"lemmaid", "type"},
    "refsense": {"senseid"},
    "Combination": {"Term", "Pronunciation", "Deriv", "Etymology",
                    "Frequency", "UsageLabel", "PartOfSpeech"},
}

ALLOWED_CHILDREN = {
    "Dictionary": {"Language"},
    "Language": {"Lemma"},
    "Lemma": {"Sense", "References"},
    "Sense": {"TE", "Example", "Definition", "Sense", "References",
              "Combination"},
    "TE": set(),
    "Example": set(),
    "Definition": set(),
    "References": {"reflemma"},
    "reflemma": {"refsense"},
    "refsense": set(),
    "Combination": {"Sense"},
}

# Comma-joined multi-value fields, e.g. PartOfSpeech="noun,adjective".
def multi(value):
    return value.split(",")


class Strict(Exception):
    pass


def check(el, context):
    expected = EXPECTED_ATTRS.get(el.tag)
    if expected is None:
        raise Strict(f"unexpected element <{el.tag}> in {context}")
    if set(el.attrib) != expected:
        raise Strict(f"<{el.tag}> attributes {sorted(el.attrib)} != expected "
                     f"{sorted(expected)} in {context}")
    if el.text and el.text.strip():
        raise Strict(f"unexpected text content in <{el.tag}> in {context}")
    if el.tail and el.tail.strip():
        raise Strict(f"unexpected tail text after <{el.tag}> in {context}")
    allowed = ALLOWED_CHILDREN[el.tag]
    for child in el:
        if child.tag not in allowed:
            raise Strict(f"unexpected <{child.tag}> inside <{el.tag}> "
                         f"in {context}")


def put(d, key, value):
    if value:
        d[key] = value


def build_references(el, context):
    check(el, context)
    refs = []
    for r in el:
        check(r, context)
        ref = {"lemmaId": int(r.get("lemmaid")), "type": int(r.get("type"))}
        sense_ids = []
        for rs in r:
            check(rs, context)
            sense_ids.append(int(rs.get("senseid")))
        put(ref, "senseIds", sense_ids)
        refs.append(ref)
    return refs


def build_sense(el, context, counts):
    check(el, context)
    counts["senses"] += 1
    sense = {"senseNumber": int(el.get("SenseNumber"))}
    put(sense, "partOfSpeech", multi(el.get("PartOfSpeech")) if el.get("PartOfSpeech") else None)
    put(sense, "usageLabels", multi(el.get("UsageLabel")) if el.get("UsageLabel") else None)
    translations, definitions, examples, subsenses, references, combinations = \
        [], [], [], [], [], []
    for child in el:
        if child.tag == "TE":
            check(child, context)
            translations.append(child.get("TE"))
            counts["translations"] += 1
        elif child.tag == "Definition":
            check(child, context)
            definitions.append(child.get("Definition"))
            counts["definitions"] += 1
        elif child.tag == "Example":
            check(child, context)
            example = {}
            put(example, "text", child.get("Example"))
            put(example, "translation", child.get("Translation"))
            put(example, "source", child.get("Source"))
            examples.append(example)
            counts["examples"] += 1
        elif child.tag == "Sense":
            subsenses.append(build_sense(child, context, counts))
        elif child.tag == "References":
            new_refs = build_references(child, context)
            references.extend(new_refs)
            counts["references"] += len(new_refs)
        elif child.tag == "Combination":
            check(child, context)
            combination = {}
            put(combination, "term", child.get("Term"))
            for attr, key in (("Pronunciation", "pronunciation"),
                              ("Deriv", "deriv"), ("Etymology", "etymology"),
                              ("Frequency", "frequency"),
                              ("PartOfSpeech", "partOfSpeech"),
                              ("UsageLabel", "usageLabels")):
                put(combination, key, child.get(attr))
            combination["senses"] = [build_sense(s, context, counts)
                                     for s in child]
            combinations.append(combination)
            counts["combinations"] += 1
    put(sense, "translations", translations)
    put(sense, "definitions", definitions)
    put(sense, "examples", examples)
    put(sense, "senses", subsenses)
    put(sense, "references", references)
    put(sense, "combinations", combinations)
    return sense


def build_lemma(el, counts):
    context = f'lemma "{el.get("LemmaSign", "?")}"'
    check(el, context)
    entry = {"headword": el.get("LemmaSign")}
    if el.get("HomonymNumber"):
        entry["homonymNumber"] = int(el.get("HomonymNumber"))
    put(entry, "partOfSpeech", multi(el.get("PartOfSpeech")) if el.get("PartOfSpeech") else None)
    put(entry, "usageLabels", multi(el.get("UsageLabel")) if el.get("UsageLabel") else None)
    for attr, key in (("Incomplete", "incomplete"),
                      ("Pronunciation", "pronunciation"), ("Deriv", "deriv"),
                      ("Etymology", "etymology"), ("Notes", "notes"),
                      ("Frequency", "frequency")):
        put(entry, key, el.get(attr))
    senses, references = [], []
    for child in el:
        if child.tag == "Sense":
            senses.append(build_sense(child, context, counts))
        elif child.tag == "References":
            new_refs = build_references(child, context)
            references.extend(new_refs)
            counts["references"] += len(new_refs)
    put(entry, "senses", senses)
    put(entry, "references", references)
    entry["created"] = el.get("Created")
    entry["modified"] = el.get("Modified")
    return entry


def parse(path, split_marker):
    sections = {"english-manx": [], "manx-english": []}
    section_counts = {name: {"senses": 0, "translations": 0, "examples": 0,
                             "definitions": 0, "references": 0,
                             "combinations": 0}
                      for name in sections}
    current = "english-manx"
    markers_seen = 0
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag != "Lemma":
            continue
        entry = build_lemma(el, section_counts[current])
        sections[current].append(entry)
        if el.get("LemmaSign") == split_marker:
            markers_seen += 1
            if markers_seen > 1:
                raise Strict(f'split marker "{split_marker}" appears more '
                             f"than once")
            current = "manx-english"
        el.clear()
    if markers_seen != 1:
        raise Strict(f'split marker "{split_marker}" not found; pass the '
                     f"correct --split-marker for this export")
    last = sections["manx-english"][-1]["headword"]
    if not last.startswith("zz"):
        print(f'warning: last Manx lemma "{last}" does not look like a '
              f"marker row", file=sys.stderr)
    return sections, section_counts


def legacy_map(entries):
    result = {}
    for entry in entries:
        translations = [t for sense in entry.get("senses", [])
                        for t in flatten_translations(sense)]
        result.setdefault(entry["headword"].lower(), []).extend(translations)
    return result


def flatten_translations(sense):
    for t in sense.get("translations", []):
        yield t
    for sub in sense.get("senses", []):
        yield from flatten_translations(sub)
    for combination in sense.get("combinations", []):
        for sub in combination.get("senses", []):
            yield from flatten_translations(sub)


def write_rich(path, meta, entries):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{\n"meta": ')
        fh.write(json.dumps(meta, ensure_ascii=False, indent=2))
        fh.write(',\n"entries": [\n')
        for i, entry in enumerate(entries):
            fh.write(json.dumps(entry, ensure_ascii=False,
                                separators=(",", ":")))
            fh.write(",\n" if i < len(entries) - 1 else "\n")
        fh.write("]\n}\n")


def write_legacy(path, mapping):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(mapping, ensure_ascii=False,
                            separators=(",", ":")))


def diff_legacy(old, new, label):
    added = [k for k in new if k not in old]
    removed = [k for k in old if k not in new]
    changed = [k for k in new if k in old and new[k] != old[k]]
    print(f"  {label}: {len(old)} -> {len(new)} keys "
          f"(+{len(added)} added, -{len(removed)} removed, "
          f"~{len(changed)} changed)")
    for name, keys in (("added", added), ("removed", removed),
                       ("changed", changed)):
        if keys:
            sample = ", ".join(repr(k) for k in keys[:5])
            print(f"    {name} e.g.: {sample}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("xml", nargs="?", default=ROOT / "source" / "Jan26.xml",
                    type=Path)
    ap.add_argument("--split-marker", default="zzz - © Phil Kelly",
                    help="LemmaSign of the last English->Manx row")
    args = ap.parse_args()

    sha256 = hashlib.sha256(open(args.xml, "rb").read()).hexdigest()
    sections, section_counts = parse(args.xml, args.split_marker)

    titles = {
        "english-manx": "Phil Kelly's English–Manx Dictionary",
        "manx-english": "Phil Kelly's Manx–English Dictionary",
    }
    directions = {"english-manx": {"from": "en", "to": "gv"},
                  "manx-english": {"from": "gv", "to": "en"}}
    legacy_names = {"english-manx": "english.json",
                    "manx-english": "manx.json"}

    for name, entries in sections.items():
        counts = section_counts[name]
        markers = [e["headword"] for e in entries
                   if e["headword"].startswith("zz")]
        meta = {
            "title": titles[name],
            "direction": directions[name],
            "credit": "Phil Kelly",
            "source": args.xml.name,
            "sourceSha256": sha256,
            "markerRows": markers,
            "counts": {"entries": len(entries), **counts},
        }
        write_rich(ROOT / f"{name}.json", meta, entries)
        print(f"{name}.json: {len(entries)} entries, "
              f"{counts['senses']} senses, "
              f"{counts['translations']} translations, "
              f"{counts['examples']} examples, "
              f"{counts['definitions']} definitions, "
              f"{counts['references']} references")

        legacy = legacy_map(entries)
        legacy_path = ROOT / legacy_names[name]
        try:
            old = json.load(open(legacy_path, encoding="utf-8"))
        except FileNotFoundError:
            old = None
        write_legacy(legacy_path, legacy)
        empty = [k for k, v in legacy.items() if not v]
        print(f"{legacy_path.name}: {len(legacy)} keys, "
              f"{sum(len(v) for v in legacy.values())} translations, "
              f"{len(empty)} empty ({', '.join(repr(k) for k in empty)})")
        if old is not None:
            diff_legacy(old, legacy, f"vs previous {legacy_path.name}")

    # Independent re-read: totals must match what the strict parse counted.
    for name in sections:
        with open(ROOT / f"{name}.json", encoding="utf-8") as fh:
            data = json.load(fh)
        assert len(data["entries"]) == len(sections[name])
    print("verification: both rich files re-parse with matching entry counts")


if __name__ == "__main__":
    main()
