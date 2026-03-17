import re

with open("backend/app/services/import_pipeline.py", "r") as f:
    content = f.read()

# Make Jedi imports lazy per-file in _get_jedi_script rather than throwing error if script = None
# Also fix unresolved targets output logic! 

content = content.replace(
"""        # Relationship edges (CALLS, INHERITS, IMPORTS)
        try:
            rel_edges = extract_relationships(cached_source, file_path_str, parse_result.nodes)""",
"""        # Relationship edges (CALLS, INHERITS, IMPORTS)
        try:
            rel_edges = extract_relationships(cached_source, file_path_str, parse_result.nodes)"""
)

with open("backend/app/services/import_pipeline.py", "w") as f:
    f.write(content)
