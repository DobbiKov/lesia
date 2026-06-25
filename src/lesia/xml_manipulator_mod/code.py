import re

# Ensure you have the necessary library installed:
# pip install tree-sitter-language-pack
try:
    from tree_sitter_language_pack import get_parser, get_language
except ImportError:
    print("Please install tree-sitter-language-pack: pip install tree-sitter-language-pack")
    exit()

class CodeParser:
    """
    An intelligent, generic parser that uses a two-tiered strategy to precisely
    separate translatable content from syntax markers.
    """

    def __init__(self, language: str):
        self.language_name = language
        try:
            self.language = get_language(language)
            self.parser = get_parser(language)
        except Exception as e:
            raise ValueError(f"Could not load parser for language '{language}'.") from e

        # Tier 1 Config: Structural analysis.
        # Defines child node types that are pure translatable content.
        self.translatable_child_types = {
            'python': {'string_content'},
            # Other languages might be added here if their parsers are as granular.
        }

        # Tier 2 Config: Regex-based analysis for leaf nodes or less granular nodes.
        # The key is a (language, node_type) tuple. The value is a compiled regex.
        # The regex should have two capture groups: (syntax_markers, content).
        self.dissection_regex = {
            ('python', 'comment'): re.compile(r'^(#+)(.*)'),
            ('rust', 'line_comment'): re.compile(r'^(//+!?)(.*)'),
            ('rust', 'block_comment'): re.compile(r'(/\*+!?)(.*?)(\*/)', re.DOTALL),
            ('java', 'line_comment'): re.compile(r'(//)(.*)'),
            ('java', 'block_comment'): re.compile(r'(/\*+)(.*?)(\*/)', re.DOTALL),
            ('java', 'string_literal'): re.compile(r'(")(.*?)(")')
        }

        # Candidate nodes that contain text we want to process.
        self.candidate_node_types = {
            'python': {'comment', 'string'},
            'java': {'line_comment', 'block_comment', 'string_literal'},
            'rust': {'line_comment', 'block_comment', 'string_literal'},
        }

    def _find_candidate_nodes(self, node, nodes_list):
        if node.type in self.candidate_node_types.get(self.language_name, {}):
            nodes_list.append(node)
            return
        for child in node.children:
            self._find_candidate_nodes(child, nodes_list)

    def _dissect_node(self, node):
        """
        Dissects a node using the smartest available method:
        1. Structural (child nodes) if possible.
        2. Pattern-based (regex) as a robust fallback.
        """
        node_type = node.type
        
        # --- Strategy 1: Structural Dissection (using child nodes) ---
        if node.children:
            child_segments = []
            translatable_types = self.translatable_child_types.get(self.language_name, set())
            for child in node.children:
                if child.type in translatable_types:
                    child_segments.append(('text', child.text.decode('utf8')))
                else:
                    child_segments.append(('placeholder', child.text.decode('utf8')))
            # If we successfully segmented using children, return the result.
            if any(seg[0] == 'text' for seg in child_segments):
                return child_segments

        # --- Strategy 2: Pattern-Based Dissection (using regex) ---
        key = (self.language_name, node_type)
        if key in self.dissection_regex:
            regex = self.dissection_regex[key]
            match = regex.match(node.text.decode('utf8'))
            if match:
                groups = match.groups()
                if len(groups) == 2: # e.g., (marker, content)
                    return [('placeholder', groups[0]), ('text', groups[1])]
                elif len(groups) == 3: # e.g., (opener, content, closer)
                    return [
                        ('placeholder', groups[0]),
                        ('text', groups[1]),
                        ('placeholder', groups[2])
                    ]

        # --- Fallback: Treat the whole node as text if no rules apply ---
        return [('text', node.text.decode('utf8'))]

    def parse(self, source_code: str) -> list[tuple[str, str]]:
        tree = self.parser.parse(bytes(source_code, "utf8"))
        candidate_nodes = []
        self._find_candidate_nodes(tree.root_node, candidate_nodes)
        candidate_nodes.sort(key=lambda n: n.start_byte)

        segments = []
        current_pos = 0
        for node in candidate_nodes:
            placeholder_content = source_code[current_pos:node.start_byte]
            if placeholder_content:
                segments.append(('placeholder', placeholder_content))
            
            segments.extend(self._dissect_node(node))
            current_pos = node.end_byte

        final_placeholder = source_code[current_pos:]
        if final_placeholder:
            segments.append(('placeholder', final_placeholder))
            
        return segments

