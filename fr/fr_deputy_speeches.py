#!/usr/bin/env python3
"""
aggregate_deputy_speeches.py
---------------------------------
Read CRI XML files from the Assemblée nationale and create
one XML file per deputy that concatenates all of their speeches.

usage:
    python aggregate_deputy_speeches.py /path/to/cri_files/ -o deputy_speeches
    python aggregate_deputy_speeches.py /path/to/data/ -o output/ --recursive
    python aggregate_deputy_speeches.py /path/to/data/ --dry-run
"""

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from unicodedata import normalize

################################################################################
# Utility helpers
################################################################################
def slugify(text: str) -> str:
    """
    Make a safe filename from a deputy's name.
    E.g. 'Éric Coquerel' -> 'Eric_Coquerel'
    """
    text = normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s]+", "_", text)

def find_xml_files(input_dir: Path, recursive: bool = False) -> list:
    """
    Find all XML files in the input directory.
    If recursive=True, searches subdirectories too.
    """
    if recursive:
        xml_files = list(input_dir.rglob("*.xml"))
    else:
        xml_files = list(input_dir.glob("*.xml"))

    return sorted(xml_files)

def parse_args():
    p = argparse.ArgumentParser(
        description="Aggregate all speeches per deputy into separate XML files")
    p.add_argument("input_dir", 
                   help="Directory containing CRI XML files")
    p.add_argument("-o", "--output-dir", default="deputy_speeches",
                   help="Directory where individual deputy XMLs will be stored")
    p.add_argument("--recursive", "-r", action="store_true",
                   help="Search subdirectories recursively for XML files")
    p.add_argument("--use-id", action="store_true",
                   help="Use <orateur id='...'> when available (avoids homonyms)")
    p.add_argument("--pattern", default="*.xml",
                   help="File pattern to match (default: *.xml)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what files would be processed without actually processing them")
    p.add_argument("--min-words", type=int, default=5,
                   help="Minimum number of words in a speech to include it (default: 5)")
    return p.parse_args()

################################################################################
# Core extraction logic
################################################################################
def extract_speeches(xml_path: Path, use_id=False, min_words=5):
    """
    Yields (key, name, date, time, text) for each speech in one CRI file.
    key = deputy identifier (id if available and --use-id, else the name).
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"    ⚠️  Error parsing {xml_path.name}: {e}")
        return
    except Exception as e:
        print(f"    ⚠️  Error reading {xml_path.name}: {e}")
        return

    # Extract session date from metadata
    session_date = None
    date_elem = root.find(".//{http://schemas.assemblee-nationale.fr/referentiel}dateSeance")
    if date_elem is not None and date_elem.text:
        # Format: 20210201160000 -> 2021-02-01
        date_str = date_elem.text[:8]
        session_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

    if not session_date:
        # Fallback to filename if available (e.g., CRSANR5L16S2021O1N144.xml)
        session_date = xml_path.stem

    speech_count = 0

    # Find all paragraphe elements that contain speeches
    for paragraphe in root.findall(".//{http://schemas.assemblee-nationale.fr/referentiel}paragraphe"):
        # Get the orateurs (speakers) for this paragraph
        orateurs_elem = paragraphe.find("{http://schemas.assemblee-nationale.fr/referentiel}orateurs")
        texte_elem = paragraphe.find("{http://schemas.assemblee-nationale.fr/referentiel}texte")

        if orateurs_elem is None or texte_elem is None:
            continue

        # Look for orateur elements within orateurs
        orateur_elems = orateurs_elem.findall("{http://schemas.assemblee-nationale.fr/referentiel}orateur")

        if not orateur_elems:
            continue

        # Process each speaker (usually just one per paragraph)
        for orateur in orateur_elems:
            nom_elem = orateur.find("{http://schemas.assemblee-nationale.fr/referentiel}nom")
            id_elem = orateur.find("{http://schemas.assemblee-nationale.fr/referentiel}id")
            qualite_elem = orateur.find("{http://schemas.assemblee-nationale.fr/referentiel}qualite")

            if nom_elem is None or not nom_elem.text:
                continue

            name = nom_elem.text.strip()

            # Skip if this is the president or procedural speakers
            if any(x in name.lower() for x in ['président', 'présidence']):
                continue

            # Get speaker ID if available and requested
            speaker_id = None
            if id_elem is not None and id_elem.text:
                speaker_id = id_elem.text.strip()

            # Create key for grouping speeches
            if use_id and speaker_id:
                key = speaker_id
            else:
                key = name

            # Extract the speech text
            speech_text = "".join(texte_elem.itertext()).strip()

            # Filter out very short speeches (likely procedural)
            if len(speech_text.split()) < min_words:
                continue

            # Get timing if available
            speech_time = texte_elem.get("stime", "")

            # Add quality/title if available
            title = ""
            if qualite_elem is not None and qualite_elem.text:
                title = qualite_elem.text.strip()

            speech_count += 1
            yield key, name, title, session_date, speech_time, speech_text

    if speech_count > 0:
        print(f"    ✓ Found {speech_count} speeches")
    else:
        print(f"    ⚠️  No speeches found")

################################################################################
# Write one XML file per deputy
################################################################################
def write_deputy_xml(output_dir: Path, deputy_name: str, speeches: list):
    """
    speeches = list of dicts {'title':..., 'date':..., 'time':..., 'text':...}
    """
    root = ET.Element("deputy", {
        "name": deputy_name, 
        "total_speeches": str(len(speeches)),
        "generated": datetime.now().isoformat()
    })

    # Sort speeches by date
    speeches.sort(key=lambda x: x["date"])

    for sp in speeches:
        attrib = {"date": sp["date"]}
        if sp["time"]:
            attrib["time"] = sp["time"]
        if sp["title"]:
            attrib["title"] = sp["title"]

        speech_el = ET.SubElement(root, "speech", attrib)
        speech_el.text = sp["text"]

    fname = slugify(deputy_name) + ".xml"
    out_path = output_dir / fname

    # Pretty print the XML
    ET.indent(root, space="  ", level=0)
    tree = ET.ElementTree(root)
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path

################################################################################
# Main routine
################################################################################
def main():
    args = parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"❌ Input directory does not exist: {input_dir}")
        return 1

    if not input_dir.is_dir():
        print(f"❌ Input path is not a directory: {input_dir}")
        return 1

    output_dir = Path(args.output_dir)

    # Find XML files
    print(f"🔍 Searching for XML files in: {input_dir}")
    if args.recursive:
        print("   (including subdirectories)")

    if args.pattern != "*.xml":
        xml_files = list(input_dir.rglob(args.pattern) if args.recursive else input_dir.glob(args.pattern))
    else:
        xml_files = find_xml_files(input_dir, args.recursive)

    if not xml_files:
        print(f"❌ No XML files found in {input_dir}")
        if not args.recursive:
            print("   💡 Try using --recursive to search subdirectories")
        return 1

    print(f"📁 Found {len(xml_files)} XML files")

    if args.dry_run:
        print("\n🔍 DRY RUN - Files that would be processed:")
        for xml_file in xml_files:
            rel_path = xml_file.relative_to(input_dir)
            print(f"   • {rel_path}")
        print(f"\n📊 Total: {len(xml_files)} files")
        print(f"📁 Output would go to: {output_dir}")
        return 0

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect speeches per deputy
    speeches_by_deputy = defaultdict(list)   # key → list[dict]
    display_name       = {}                  # key → human-readable name
    processed_files = 0
    total_speeches = 0

    print(f"\n📖 Processing XML files...")
    for xml_file in xml_files:
        rel_path = xml_file.relative_to(input_dir)
        print(f"  📄 {rel_path}")

        file_speeches = 0
        for key, name, title, date, time, text in extract_speeches(xml_file, use_id=args.use_id, min_words=args.min_words):
            speeches_by_deputy[key].append({
                "title": title,
                "date": date, 
                "time": time, 
                "text": text
            })
            display_name[key] = name
            file_speeches += 1
            total_speeches += 1

        if file_speeches > 0:
            processed_files += 1

    if not speeches_by_deputy:
        print("\n❌ No speeches found in any files!")
        print("💡 Try reducing --min-words or check the XML structure")
        return 1

    print(f"\n📊 Summary:")
    print(f"   • Processed: {processed_files}/{len(xml_files)} files")
    print(f"   • Total speeches: {total_speeches}")
    print(f"   • Unique deputies: {len(speeches_by_deputy)}")

    print(f"\n💾 Writing deputy files to {output_dir}...")
    for key, speeches in speeches_by_deputy.items():
        out_path = write_deputy_xml(output_dir, display_name[key], speeches)
        print(f"  ✅ {display_name[key]:<40} → {out_path.name:<50} ({len(speeches):>3} speeches)")

    print(f"\n🎉 Done! Created {len(speeches_by_deputy)} deputy files in {output_dir}")
    return 0

if __name__ == "__main__":
    exit(main())
