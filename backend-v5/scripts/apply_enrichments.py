#!/usr/bin/env python3
"""
Apply candidate enrichments from research agents.
Reads enrichment data and updates election-results-2082.json.
"""
import json
from pathlib import Path

def load_enrichments(enrichment_file: Path) -> list:
    """Load enrichments from a Python file or JSON."""
    if not enrichment_file.exists():
        return []

    content = enrichment_file.read_text(encoding='utf-8')

    # Try to extract ENRICHMENTS list from Python code
    if 'ENRICHMENTS' in content:
        # Find the list definition
        import re
        match = re.search(r'ENRICHMENTS\s*=\s*\[', content)
        if match:
            start = match.start()
            # Find matching bracket
            bracket_count = 0
            in_string = False
            string_char = None
            for i, char in enumerate(content[start:]):
                if char in '"\'':
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif char == string_char and content[start+i-1] != '\\':
                        in_string = False
                elif not in_string:
                    if char == '[':
                        bracket_count += 1
                    elif char == ']':
                        bracket_count -= 1
                        if bracket_count == 0:
                            list_str = content[start:start+i+1]
                            # Extract just the list part
                            list_str = list_str[list_str.index('['):]
                            try:
                                # Use ast.literal_eval for safety
                                import ast
                                return ast.literal_eval(list_str)
                            except:
                                pass
                            break

    # Try JSON
    try:
        return json.loads(content)
    except:
        pass

    return []


def main():
    script_dir = Path(__file__).parent.resolve()
    data_path = script_dir / "../../frontend/public/data/election-results-2082.json"
    enrichments_dir = script_dir / "enrichments"

    # Create enrichments directory if needed
    enrichments_dir.mkdir(exist_ok=True)

    print(f"Loading {data_path}")
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Load all enrichment files
    all_enrichments = []
    for enrichment_file in enrichments_dir.glob("*.py"):
        print(f"Loading enrichments from {enrichment_file.name}")
        enrichments = load_enrichments(enrichment_file)
        all_enrichments.extend(enrichments)
        print(f"  Found {len(enrichments)} enrichments")

    for enrichment_file in enrichments_dir.glob("*.json"):
        print(f"Loading enrichments from {enrichment_file.name}")
        enrichments = load_enrichments(enrichment_file)
        all_enrichments.extend(enrichments)
        print(f"  Found {len(enrichments)} enrichments")

    print(f"\nTotal enrichments to apply: {len(all_enrichments)}")

    # Create lookup by Nepali name
    enrichment_lookup = {}
    for e in all_enrichments:
        match_ne = e.get("match_ne", "")
        if match_ne:
            enrichment_lookup[match_ne] = e

    # Apply enrichments
    updated = 0
    for constituency in data.get("results", []):
        for candidate in constituency.get("candidates", []):
            name_ne = candidate.get("name_ne", "") or candidate.get("name_en", "")

            if name_ne in enrichment_lookup:
                enrichment = enrichment_lookup[name_ne]

                # Update fields
                if enrichment.get("name_en_roman"):
                    candidate["name_en_roman"] = enrichment["name_en_roman"]

                # Merge aliases
                existing_aliases = set(candidate.get("aliases", []))
                new_aliases = enrichment.get("aliases", [])
                existing_aliases.update(new_aliases)
                candidate["aliases"] = list(existing_aliases)

                if enrichment.get("biography"):
                    candidate["biography"] = enrichment["biography"]

                if enrichment.get("biography_source"):
                    candidate["biography_source"] = enrichment["biography_source"]

                if enrichment.get("is_notable") is not None:
                    candidate["is_notable"] = enrichment["is_notable"]

                updated += 1

    # Save
    with open(data_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nUpdated {updated} candidates with detailed biographies")


if __name__ == "__main__":
    main()
