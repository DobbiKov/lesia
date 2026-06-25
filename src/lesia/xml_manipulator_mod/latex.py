import re
import uuid
from pylatexenc.latexwalker import (LatexCommentNode, LatexWalker, LatexCharsNode, LatexMacroNode,
                                    LatexEnvironmentNode, LatexMathNode, LatexGroupNode)
class LatexParser:
    """
    Unified LaTeX parser that combines all functionality:
    - Asterisk preservation (\\section*, \\verb*, etc.)
    - Verb command preprocessing (\\verb|content|, \\verb*|content|)
    - Unknown commands with pipe delimiters (\\custommacro|content|)
    - Standard LaTeX argument parsing ({}, [])
    """
    
    def __init__(self, placeholder_commands: list = [], placeholder_envs: list = [], placeholders_with_text: list = []):
        # Configuration attributes
        self.placeholder_commands = {'ref', 'autoref', 'cite', 'label', 'includegraphics', 'input', 'include', 'frac', 'sqrt', 'path', 'url', 'href', '\\', 'verb'}
        self.placeholder_envs = {'verbatim', 'Verbatim', 'lstlisting', 'minted'}
        self.math_envs = {
                'equation', 'equation*', 'align', 'align*', 'aligned', 'gather', 'gather*', 
                'gathered', 'flalign', 'flalign*', 'alignat', 'alignat*', 'multline', 'multline*',
                'displaymath', 'math', 'eqnarray', 'eqnarray*'
                }
        self.math_text_macros = {'text', 'mathrm','mathbf', 'operatorname',
                                 'mathit', 'textrm', 'textit', 'mathsf',
                                 'mathtt', 'boldsymbol' }
        self.definition_macros = {'newcommand', 'renewcommand', 'newenvironment', 'renewenvironment', 'def'}
        self.alignment_envs = {'tabular', 'tabular*', 'array', 'align', 'align*',
                               'aligned', 'flalign', 'flalign*', 'alignat',
                               'alignat*', 'gather', 'gather*'}
        # Allow customization
        if len(placeholder_commands) != 0:
            self.placeholder_commands.update(placeholder_commands)
        if len(placeholder_envs) != 0:
            self.placeholder_envs.update(placeholder_envs)
        if len(placeholders_with_text) != 0:
            self.math_text_macros.update(placeholders_with_text)
        # State attributes
        self.segments = []
        self.latex_content = ""
        self._verb_map: dict[str, str] = {}
        self._pipe_map: dict[str, str] = {}
    def parse(self, latex_content) -> list[tuple[str, str]]:
        """
        Main parsing method that handles all special cases.
        Returns list of (type, content) tuples where type is 'text' or 'placeholder'.
        """
        # Extract verb commands first (highest priority) (causing the most problems ahah)
        verb_info = self._extract_verb_commands(latex_content)
        processed_content = verb_info['processed_text']
        
        # Extract unknown commands with pipe delimiters
        pipe_info = self._extract_pipe_commands(processed_content)
        processed_content = pipe_info['processed_text']
        
        # Parse with LaTeX parser
        self.segments = []
        self.latex_content = processed_content
        lw = LatexWalker(processed_content)
        nodelist, _, _ = lw.get_latex_nodes()
        if r'\end{document}' in processed_content and r'\begin{document}' not in processed_content:
            return [('placeholder', latex_content)]
        self._walk_text_nodes(nodelist)
        
        # Restore in reverse order (pipe commands first, then verb commands)
        self._restore_pipe_commands()
        self._restore_verb_commands()
        
        return self.segments
    def add_math_text_macros(self, *names: str):
        """Register additional text‑in‑math macros at runtime."""
        self.math_text_macros.update(names)
    # === PREPROCESSING METHODS ===
    def _make_placeholder(self, tag: str) -> str:
        """
        Return a collision‑proof placeholder string such as
        '<<VERB_9f56c1a379c84c7c8e27d120f2f6e5d9>>'.
        Using UUIDs guarantees the token will never exist in real LaTeX source.
        """
        return f"<<{tag}_{uuid.uuid4().hex}>>"
    
    def _extract_verb_commands(self, text):
        """Extract \\verb and \\verb* commands to avoid parsing issues."""
        verb_commands = []
        
        verb_pattern = r'\\verb\*?(.)(.*?)\1'
        
        def collect_verb(match):
            placeholder = self._make_placeholder("VERB")
            self._verb_map[placeholder] = match.group(0)
            return placeholder
        
        processed_text = re.sub(verb_pattern, collect_verb, text)
        
        return {
            'processed_text': processed_text,
            'verb_commands': verb_commands
        }
    
    def _extract_pipe_commands(self, text):
        """Extract unknown commands that use pipe delimiters \\command|content|."""
        pipe_commands = []
        
        # Pattern for commands with pipe delimiters (excluding verb which is handled separately)
        pipe_pattern = r'\\([a-zA-Z]+)(\*?)\|([\s\S]*?)\|'
        
        def collect_pipe(match):
            command_name = match.group(1)
            # star = match.group(2)
            # content = match.group(3)
            
            # Skip verb commands as they're handled separately
            if command_name.lower() == 'verb':
                return match.group(0)
            
            placeholder = self._make_placeholder("PIPE")
            self._pipe_map[placeholder] = match.group(0)
            return placeholder
        
        processed_text = re.sub(pipe_pattern, collect_pipe, text, flags=re.DOTALL)
        
        return {
            'processed_text': processed_text,
            'pipe_commands': pipe_commands
        }
    # === CORE PARSING METHODS ===
    
    def _add_placeholder(self, content):
        if content: 
            self.segments.append(('placeholder', content))
    def _add_text(self, content):
        if content.strip(): 
            self.segments.append(('text', content))
        elif content: 
            self.segments.append(('placeholder', content))
    def _process_chars_node(self, node, in_alignment=False):
        """Process character nodes, handling & specially."""
        if in_alignment:
            parts = re.split(r'(&)', node.chars)
        else:
            parts = [node.chars]  
        for part in parts:
            if not part: 
                continue
            if part == '&': 
                self._add_placeholder(part)
            else: 
                self._add_text(part)
    def _walk_text_nodes(self, nodelist, env_stack=[]):
        """Main node walker for text mode - handles asterisk preservation."""
        if nodelist is None: 
            return
        for node in nodelist:
            if node.isNodeType(LatexCharsNode):
                self._process_chars_node(node, in_alignment=(len(env_stack)>0) and env_stack[-1] in self.alignment_envs)
            elif node.isNodeType(LatexCommentNode):
                self._add_placeholder('% ')
                self._add_text(node.comment)
                self._add_placeholder(node.comment_post_space or '\n')
            elif node.isNodeType(LatexMathNode):
                self._add_placeholder(node.delimiters[0])
                self._walk_math_nodes(node.nodelist)
                self._add_placeholder(node.delimiters[1])
            elif node.isNodeType(LatexGroupNode):
                self._add_placeholder('{')
                self._walk_text_nodes(node.nodelist)
                self._add_placeholder('}')
            elif node.isNodeType(LatexMacroNode):
                if node.macroname in self.definition_macros:
                    self._process_definition_macro(node)
                elif node.macroname in self.placeholder_commands:
                    self._add_placeholder(node.latex_verbatim())
                else:
                    # ASTERISK PRESERVATION: Use latex_verbatim() and extract command part
                    full_command = node.latex_verbatim()
                    if node.nodeargs:
                        # Find where the command ends and arguments begin
                        command_part = full_command
                        for arg_node in node.nodeargs:
                            if arg_node is not None:
                                arg_start = arg_node.pos - node.pos
                                command_part = full_command[:arg_start]
                                break
                        self._add_placeholder(command_part)
                        for arg_node in node.nodeargs:
                            if arg_node is None:
                                continue
                            self._walk_text_nodes([arg_node])
                    else:
                        # No arguments, use the full command
                        self._add_placeholder(full_command)
            elif node.isNodeType(LatexEnvironmentNode):
                envname = node.environmentname
                env_stack.append(envname)
                if envname in self.placeholder_envs:
                    self._add_placeholder(node.latex_verbatim())
                else:
                    if not node.nodelist:
                        self._add_placeholder(node.latex_verbatim())
                        continue
                    # find the first node that lies *after* the \begin argument list
                    header_end_pos = self._env_header_end(node)
                    first_body_node = next(
                        (n for n in node.nodelist if n.pos >= header_end_pos),
                        node.nodelist[0],
                    )
                    content_start_pos = header_end_pos
                    if content_start_pos <= node.pos or content_start_pos > first_body_node.pos:
                        content_start_pos = first_body_node.pos

                    last_node = node.nodelist[-1]
                    content_end_pos = last_node.pos + last_node.len

                    begin_placeholder = self.latex_content[node.pos:content_start_pos]
                    begin_placeholder = re.sub(r'\n[ \t]*$', '', begin_placeholder)
                    self._add_placeholder(begin_placeholder)

                    if envname in self.math_envs:
                        self._walk_math_nodes(node.nodelist) 
                    else:
                        self._walk_text_nodes(node.nodelist)

                    end_placeholder = self.latex_content[content_end_pos:(node.pos + node.len)]
                    self._add_placeholder(end_placeholder)
                env_stack.pop()
            else:
                self._add_placeholder(node.latex_verbatim())

    def _process_definition_macro(self, node):
        """Process definition macros like \\newcommand with asterisk preservation."""
        # Extract command part from latex_verbatim to preserve asterisks
        full_command = node.latex_verbatim()
        if node.nodeargs:
            command_part = full_command
            for arg_node in node.nodeargs:
                if arg_node is not None:
                    arg_start = arg_node.pos - node.pos
                    command_part = full_command[:arg_start]
                    break
            self._add_placeholder(command_part)
        else:
            self._add_placeholder(full_command)
            
        if not node.nodeargs: 
            return

        syntax_args = node.nodeargs[:-1]
        definition_arg = node.nodeargs[-1]

        for arg in syntax_args:
            if arg is None:
                continue
            self._add_placeholder(arg.latex_verbatim())

        self._add_placeholder(definition_arg.delimiters[0])
        self._walk_definition_nodes(definition_arg.nodelist)
        self._add_placeholder(definition_arg.delimiters[1])

    def _walk_definition_nodes(self, nodelist):
        """Special walker for inside \\newcommand that recognizes # tokens."""
        if nodelist is None: 
            return
        for node in nodelist:
            if node.isNodeType(LatexMacroNode) and node.macroname == '#':
                self._add_placeholder(node.latex_verbatim())
            else:
                if node.isNodeType(LatexCharsNode): 
                    self._process_chars_node(node)
                elif node.isNodeType(LatexMathNode): 
                    self._add_placeholder(node.latex_verbatim())
                elif node.isNodeType(LatexGroupNode):
                    self._add_placeholder(node.delimiters[0])
                    self._walk_definition_nodes(node.nodelist)
                    self._add_placeholder(node.delimiters[1])
                elif node.isNodeType(LatexMacroNode):
                    self._walk_text_nodes([node])
                else:
                    self._add_placeholder(node.latex_verbatim())

    def _walk_math_nodes(self, nodelist):
        """Node walker for math mode with asterisk preservation."""
        if nodelist is None: 
            return
        for node in nodelist:
            if node.isNodeType(LatexMacroNode) and node.macroname in self.math_text_macros:
                # Extract command part to preserve asterisks
                full_command = node.latex_verbatim()
                if node.nodeargs:
                    command_part = full_command
                    for arg_node in node.nodeargs:
                        if arg_node is not None:
                            arg_start = arg_node.pos - node.pos
                            command_part = full_command[:arg_start]
                            break
                    self._add_placeholder(command_part)
                    for arg_node in node.nodeargs:
                        self._walk_text_nodes([arg_node])
                else:
                    self._add_placeholder(full_command)
            else:
                self._add_placeholder(node.latex_verbatim())

    # === POSTPROCESSING METHODS ===
    def _restore_pipe_commands(self):
        """
        Replace **every** placeholder instance, even if a segment contains the token
        more than once.  Uses the lookup table built in `_extract_pipe_commands`.
        """
        self._generic_restore(self._pipe_map)    

    def _restore_verb_commands(self):
        """Restore all `\verb` placeholders using the same generic helper."""
        self._generic_restore(self._verb_map)

    def _generic_restore(self, lookup: dict[str, str]) -> None:
        """
        Generic helper that replaces every placeholder found in *lookup* with its
        original text, handling any number of occurrences inside a segment.
        """
        i = 0
        while i < len(self.segments):
            seg_type, content = self.segments[i]
            made_changes = False
            for placeholder, original in lookup.items():
                if placeholder in content:
                    # Split *every* occurrence, not just the first two.
                    parts = content.split(placeholder)
                    new_segments = []
                    for k, part in enumerate(parts):
                        if part:
                            new_segments.append(
                                ('text' if part.strip() else 'placeholder', part)
                            )
                        if k < len(parts) - 1:
                            new_segments.append(('placeholder', original))
                    # Replace current segment with the expanded list
                    self.segments[i:i+1] = new_segments
                    made_changes = True
                    break  # restart outer loop because list length changed
            if not made_changes:
                i += 1
    # === UTILITIES ===
    def _env_header_end(self, env_node):
        """
        Return the character offset immediately after
        \\begin{envname}[opt1][opt2]{mand}
        by scanning the original source.  This works on *any* pylatexenc
        version because it doesn’t rely on internal attributes.
        """
        s = self.latex_content
        i = env_node.pos          # points at the backslash of \begin
        n = len(s)

        # Skip '\begin'
        i = s.find('{', i)
        if i == -1:
            return env_node.pos   # malformed, fall back
        # Skip '{envname}'
        depth = 1
        i += 1
        while i < n and depth:
            if s[i] == '{':
                depth += 1
            elif s[i] == '}':
                depth -= 1
            i += 1
        if depth:
            return env_node.pos   # unmatched brace – give up

        # Skip whitespace
        while i < n and s[i].isspace():
            i += 1

        # Zero or more optional [ ... ] groups
        while i < n and s[i] == '[':
            depth = 1
            i += 1
            while i < n and depth:
                if s[i] == '[':
                    depth += 1
                elif s[i] == ']':
                    depth -= 1
                i += 1
            while i < n and s[i].isspace():
                i += 1

        # First mandatory { ... } group
        if i < n and s[i] == '{':
            depth = 1
            i += 1
            while i < n and depth:
                if s[i] == '{':
                    depth += 1
                elif s[i] == '}':
                    depth -= 1
                i += 1

        return i  # character *after* the closing '}' of the mandatory arg

def parse_latex(latex_content) -> list[tuple[str, str]]:
    """High-level function to instantiate and use the LatexParser."""
    parser = LatexParser()
    return parser.parse(latex_content)



