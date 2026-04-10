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


class ParserJavaScript(ParserBase):
    @property
    def language_name(self) -> str:
        return "javascript"

    def can_handle_this_language(self, language_name: str) -> bool:
        return language_name.lower() in ("javascript", "js")

    def find_function_nodes(self, tree: Tree) -> list[Node]:
        """
        Collect top-level function nodes.
        Supported node types:
          - function_declaration          : function foo() {}
          - function_expression           : const foo = function() {}
          - arrow_function                : const foo = () => {}
          - method_definition             : class method or object method
        """
        func_nodes: list[Node] = []
        for node in traverse_tree(tree):
            if node.type in (
                "function_declaration",
                "function_expression",
                "arrow_function",
                "method_definition",
            ):
                func_nodes.append(node)

        # Remove nodes nested inside another collected function node
        result = []
        for i, s in enumerate(func_nodes):
            is_nested = False
            for j, other in enumerate(func_nodes):
                if i != j:
                    if (
                        other.start_point <= s.start_point
                        and other.end_point >= s.end_point
                        and (other.start_point, other.end_point)
                        != (s.start_point, s.end_point)
                    ):
                        is_nested = True
                        break
            if not is_nested:
                result.append(s)

        return result

    def parse(self, tree: Tree, file_lines: list[str]) -> list[ExtractedFunction]:
        func_nodes = self.find_function_nodes(tree)
        extracted: list[ExtractedFunction] = []

        for node in func_nodes:
            func = self._traverse_func_node(node, file_lines)
            if func is not None:
                extracted.append(func)

        return extracted

    def _traverse_func_node(
        self, func_node: Node, file_lines: list[str]
    ) -> ExtractedFunction | None:
        # ---- function name ----
        func_name = self._extract_func_name(func_node, file_lines)
        if func_name is None:
            return None

        # ---- parameters ----
        param_node = func_node.child_by_field_name("parameters")
        if param_node is None:
            # arrow functions with single param may use `identifier` as param directly
            param_node = func_node.child_by_field_name("parameter")
        parameter_list = self._extract_parameter_list(param_node, file_lines)

        # Build signature string: (name, name, ...)
        compose_signature = f"({', '.join(n for _, n, _ in parameter_list if n)})"

        # ---- return type (JS is dynamically typed) ----
        return_type = ""

        # ---- full function text ----
        func_text = _node_text(file_lines, func_node)

        self.debug("=" * 80)
        self.debug(f"func name   : {func_name}")
        self.debug(f"signature   : {compose_signature}")
        self.debug(f"parameters  : {parameter_list}")
        self.debug("=" * 80)

        return ExtractedFunction(
            func_name,
            compose_signature,
            parameter_list,
            return_type,
            func_text,
        )

    def _extract_func_name(self, func_node: Node, file_lines: list[str]) -> str | None:
        node_type = func_node.type

        if node_type == "function_declaration":
            # function foo() {}  →  name field is `identifier`
            name_node = func_node.child_by_field_name("name")
            if name_node is not None:
                return _node_text(file_lines, name_node)
            return None

        if node_type == "method_definition":
            # class Foo { bar() {} }  →  name field is `property_identifier`
            name_node = func_node.child_by_field_name("name")
            if name_node is not None:
                # Prefix with class name if the parent chain has a class_body → class_declaration
                class_name = self._find_class_name(func_node, file_lines)
                method_name = _node_text(file_lines, name_node)
                if class_name:
                    return f"{class_name}.{method_name}"
                return method_name
            return None

        # function_expression or arrow_function assigned to a variable
        # const foo = function() {}  or  const foo = () => {}
        # Walk up: function_expression → variable_declarator → name
        parent = func_node.parent
        if parent is not None and parent.type == "variable_declarator":
            name_node = parent.child_by_field_name("name")
            if name_node is not None:
                return _node_text(file_lines, name_node)

        # assignment_expression: module.exports = function() {}  or  obj.method = () => {}
        if parent is not None and parent.type == "assignment_expression":
            left = parent.child_by_field_name("left")
            if left is not None:
                return _node_text(file_lines, left)

        # Anonymous function with no clear name — skip
        return None

    def _find_class_name(self, method_node: Node, file_lines: list[str]) -> str | None:
        node = method_node.parent  # class_body
        if node is not None:
            node = node.parent  # class_declaration or class
        if node is not None and node.type in ("class_declaration", "class"):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                return _node_text(file_lines, name_node)
        return None

    def _extract_parameter_list(
        self, param_node: Node | None, file_lines: list[str]
    ) -> list[Tuple[str, str, int]]:
        """
        Returns list of ("", name_str, -1).
        JS has no type annotations (plain JS), so type is always empty string.
        Handles: identifiers, rest parameters (...args), destructuring patterns.
        """
        params: list[Tuple[str, str, int]] = []
        if param_node is None:
            return params

        # Single identifier parameter in arrow functions: x => x + 1
        if param_node.type == "identifier":
            return [("", _node_text(file_lines, param_node), -1)]

        # formal_parameters or destructuring
        for child in param_node.children:
            if child.type == "identifier":
                params.append(("", _node_text(file_lines, child), -1))
            elif child.type == "rest_pattern":
                # ...args
                inner = child.children[-1] if child.children else None
                name = _node_text(file_lines, inner) if inner else "..."
                params.append(("", f"...{name}", -1))
            elif child.type == "assignment_pattern":
                # param = default
                name_node = child.child_by_field_name("left")
                if name_node is not None:
                    params.append(("", _node_text(file_lines, name_node), -1))
            elif child.type in ("object_pattern", "array_pattern"):
                # destructuring: { a, b } or [a, b]
                params.append(("", _node_text(file_lines, child), -1))

        return params
