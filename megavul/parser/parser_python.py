from typing import Tuple

from megavul.parser.parser_base import ParserBase
from megavul.parser.parser_util import (
    ExtractedFunction,
    traverse_tree,
    node_split_from_file,
)
from tree_sitter import Tree, Node


def _node_text(file_lines: list[str], node: Node) -> str:
    result = node_split_from_file(file_lines, node)
    if isinstance(result, list):
        return "".join(result)
    return result


class ParserPython(ParserBase):
    @property
    def language_name(self) -> str:
        return "python"

    def can_handle_this_language(self, language_name: str) -> bool:
        return language_name.lower() == "python"

    def find_function_nodes(self, tree: Tree) -> list[tuple[Node, Node]]:
        """
        Collect (outer_node, func_def_node) pairs for top-level and class-method functions.

        outer_node: the node whose text should be saved as `func` (decorated_definition or function_definition)
        func_def_node: the actual function_definition node (for name/params/return_type)

        Only includes functions whose direct parent is:
        - module (top-level)
        - block whose parent is class_definition (class method)
        Nested functions (inside other functions) are excluded.
        """
        pairs: list[tuple[Node, Node]] = []

        for node in traverse_tree(tree):
            if node.type == "function_definition":
                parent = node.parent
                if parent is None:
                    continue
                if self._is_allowed_parent(parent):
                    pairs.append((node, node))

            elif node.type == "decorated_definition":
                parent = node.parent
                if parent is None:
                    continue
                # inner node must be a function_definition (not class_definition)
                inner = self._get_inner_func_def(node)
                if inner is not None and self._is_allowed_parent(parent):
                    pairs.append((node, inner))

        return pairs

    def _is_allowed_parent(self, parent: Node) -> bool:
        """Return True if parent is module or a block directly inside a class_definition."""
        if parent.type == "module":
            return True
        if parent.type == "block":
            grandparent = parent.parent
            if grandparent is not None and grandparent.type == "class_definition":
                return True
        return False

    def _get_inner_func_def(self, decorated_node: Node) -> Node | None:
        """Return the innermost function_definition of a decorated_definition.

        Handles stacked decorators (@a\\n@b\\ndef f()) which tree-sitter parses
        as nested decorated_definition nodes.
        """
        for child in decorated_node.children:
            if child.type == "function_definition":
                return child
            if child.type == "decorated_definition":
                return self._get_inner_func_def(child)
        return None

    def _get_class_name(self, node: Node, file_lines: list[str]) -> str | None:
        """Walk up the tree to find an enclosing class_definition and return its name."""
        current = node.parent
        while current is not None:
            if current.type == "class_definition":
                name_node = current.child_by_field_name("name")
                if name_node is not None:
                    return _node_text(file_lines, name_node)
                return None
            # Stop climbing if we hit a function body (nested function)
            if current.type == "function_definition":
                return None
            current = current.parent
        return None

    def parse(self, tree: Tree, file_lines: list[str]) -> list[ExtractedFunction]:
        pairs = self.find_function_nodes(tree)
        extracted: list[ExtractedFunction] = []

        for outer_node, func_node in pairs:
            func = self._traverse_func_node(outer_node, func_node, file_lines)
            if func is not None:
                extracted.append(func)

        return extracted

    def _traverse_func_node(
        self, outer_node: Node, func_node: Node, file_lines: list[str]
    ) -> ExtractedFunction | None:
        # ---- function name ----
        name_node = func_node.child_by_field_name("name")
        if name_node is None:
            return None
        func_name = _node_text(file_lines, name_node)

        # Prefix with class name if this is a method
        class_name = self._get_class_name(func_node, file_lines)
        if class_name:
            func_name = f"{class_name}.{func_name}"

        # ---- parameters ----
        param_list_node = func_node.child_by_field_name("parameters")
        if param_list_node is None:
            return None
        parameter_list = self._extract_parameter_list(param_list_node, file_lines)

        sig_parts = []
        for param_type, param_name, _ in parameter_list:
            if param_type:
                sig_parts.append(f"{param_type} {param_name}")
            else:
                sig_parts.append(param_name)
        compose_signature = f"({', '.join(sig_parts)})"

        # ---- return type ----
        return_type_node = func_node.child_by_field_name("return_type")
        return_type = (
            _node_text(file_lines, return_type_node) if return_type_node else ""
        )

        # ---- full function text (include decorators if present) ----
        func_text = _node_text(file_lines, outer_node)

        self.debug("=" * 80)
        self.debug(f"func name   : {func_name}")
        self.debug(f"signature   : {compose_signature}")
        self.debug(f"parameters  : {parameter_list}")
        self.debug(f"return type : {return_type}")
        self.debug("=" * 80)

        return ExtractedFunction(
            func_name,
            compose_signature,
            parameter_list,
            return_type,
            func_text,
        )

    def _extract_parameter_list(
        self, param_list_node: Node, file_lines: list[str]
    ) -> list[Tuple[str, str, int]]:
        """
        Returns list of (type_str, name_str, -1).

        Handles:
          identifier                  → ("", name, -1)
          typed_parameter             → (type, name, -1)
          default_parameter           → ("", name, -1)
          typed_default_parameter     → (type, name, -1)
          list_splat_pattern (*args)  → ("", "*name", -1)
          dictionary_splat_pattern    → ("", "**name", -1)
          keyword_separator (*)       → skipped
        """
        params: list[Tuple[str, str, int]] = []

        for child in param_list_node.children:
            node_type = child.type

            if node_type == "identifier":
                # plain parameter: def f(x)
                params.append(("", _node_text(file_lines, child), -1))

            elif node_type == "typed_parameter":
                # def f(x: int)
                # tree-sitter Python grammar has no "name" field on typed_parameter;
                # the first named child is the identifier (or splat for *args: T / **kw: T)
                type_node = child.child_by_field_name("type")
                type_str = _node_text(file_lines, type_node) if type_node else ""
                name_part = child.named_children[0] if child.named_children else None
                if name_part is None:
                    pass
                elif name_part.type == "identifier":
                    params.append((type_str, _node_text(file_lines, name_part), -1))
                elif name_part.type == "list_splat_pattern":
                    inner = (
                        name_part.named_children[0]
                        if name_part.named_children
                        else None
                    )
                    name_str = f"*{_node_text(file_lines, inner)}" if inner else "*"
                    params.append((type_str, name_str, -1))
                elif name_part.type == "dictionary_splat_pattern":
                    inner = (
                        name_part.named_children[0]
                        if name_part.named_children
                        else None
                    )
                    name_str = f"**{_node_text(file_lines, inner)}" if inner else "**"
                    params.append((type_str, name_str, -1))

            elif node_type == "default_parameter":
                # def f(x=1)
                name_node = child.child_by_field_name("name")
                name_str = _node_text(file_lines, name_node) if name_node else ""
                if name_str:
                    params.append(("", name_str, -1))

            elif node_type == "typed_default_parameter":
                # def f(x: int = 1)
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                name_str = _node_text(file_lines, name_node) if name_node else ""
                type_str = _node_text(file_lines, type_node) if type_node else ""
                if name_str:
                    params.append((type_str, name_str, -1))

            elif node_type == "list_splat_pattern":
                # *args
                inner = child.named_children[0] if child.named_children else None
                name_str = f"*{_node_text(file_lines, inner)}" if inner else "*"
                params.append(("", name_str, -1))

            elif node_type == "dictionary_splat_pattern":
                # **kwargs
                inner = child.named_children[0] if child.named_children else None
                name_str = f"**{_node_text(file_lines, inner)}" if inner else "**"
                params.append(("", name_str, -1))

            # keyword_separator (*), "," and "(" ")" are skipped

        return params


if __name__ == "__main__":
    from megavul.util.logging_util import global_logger

    parser = ParserPython(global_logger)

    sample = """\
def greet(name: str, greeting: str = "Hello") -> str:
    return f"{greeting}, {name}!"

class MyClass:
    def method(self, x: int, *args, **kwargs):
        pass

    @staticmethod
    def static_method(a, b):
        return a + b

@decorator
def decorated(x: int) -> None:
    pass
"""
    file_lines = [line + "\n" for line in sample.splitlines()]
    tree = parser.parser.parse(bytes(sample, encoding="utf-8"))
    results = parser.parse(tree, file_lines)
    for r in results:
        print(r)
