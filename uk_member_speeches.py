#!/usr/bin/env python3

# Script to walk through downloads of Hansard in XML files from TheyWorkForYou.com and sort these into files for each MP.
# Run from the command line specifying an input and output directory, eg 'python3 uk_member_speeches.py --input-dir twfy/xml --output-dir members'

import argparse, glob, os, re, xml.etree.ElementTree as ET

def sanitise(t): return re.sub(r"[^A-Za-z0-9_\-]", "_", t.strip().replace(" ", "_"))
def split_hansard(inp, out):
    os.makedirs(out, exist_ok=True)
    handles = {}
    def h(mid, mname):
        key = f"{mid}_{mname}"
        if key not in handles:
            f = open(os.path.join(out, f"{key}.xml"), "w", encoding="utf-8")
            f.write('<?xml version="1.0" encoding="utf-8"?>\n'
                    f'<speeches member_id="{mid}" member_name="{mname}">\n')
            handles[key] = f
        return handles[key]

    for fn in glob.iglob(os.path.join(inp, "**", "*.xml"), recursive=True):
        for _, elem in ET.iterparse(fn, events=("end",)):
            if elem.tag == "speech":
                pid = elem.attrib.get("person_id") or ""
                mid = pid.split("/")[-1] if "/" in pid else (pid or "unknown")
                mname = sanitise(elem.attrib.get("speakername", "Unknown"))
                h(mid, mname).write(ET.tostring(elem, encoding="unicode", method="xml") + "\n")
                elem.clear()          # clear only AFTER writing the whole speech

    for f in handles.values():
        f.write("</speeches>\n"); f.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True)
    p.add_argument("--output-dir", required=True)
    a = p.parse_args()
    split_hansard(a.input_dir, a.output_dir)
