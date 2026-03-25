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


class ParserGo(ParserBase):
    @property
    def language_name(self) -> str:
        return "go"

    def can_handle_this_language(self, language_name: str) -> bool:
        return language_name.lower() == "go"

    def find_function_nodes(self, tree: Tree) -> list[Node]:
        """Collect function_declaration and method_declaration nodes, excluding nested ones."""
        func_nodes: list[Node] = []
        for node in traverse_tree(tree):
            if node.type in ("function_declaration", "method_declaration"):
                func_nodes.append(node)

        # Remove nodes that are nested inside another function node
        result = []
        for i, s in enumerate(func_nodes):
            is_nested = False
            for j, other in enumerate(func_nodes):
                if i != j:
                    if (
                        other.start_point[0] <= s.start_point[0]
                        and other.end_point[0] >= s.end_point[0]
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
        name_node = func_node.child_by_field_name("name")
        if name_node is None:
            return None
        func_name = _node_text(file_lines, name_node)

        # For method_declaration, prefix with receiver type for context
        if func_node.type == "method_declaration":
            receiver_node = func_node.child_by_field_name("receiver")
            if receiver_node is not None:
                receiver_type = self._extract_receiver_type(receiver_node, file_lines)
                if receiver_type:
                    func_name = f"({receiver_type}).{func_name}"

        # ---- parameters ----
        param_list_node = func_node.child_by_field_name("parameters")
        if param_list_node is None:
            return None
        parameter_list = self._extract_parameter_list(param_list_node, file_lines)

        # Build signature string: (type name, type name, ...)
        sig_parts = []
        for param_type, param_name, _ in parameter_list:
            if param_name:
                sig_parts.append(f"{param_type} {param_name}")
            else:
                sig_parts.append(param_type)
        compose_signature = f"({', '.join(sig_parts)})"

        # ---- return type ----
        result_node = func_node.child_by_field_name("result")
        return_type = self._extract_result_type(result_node, file_lines)

        # ---- full function text ----
        func_text = _node_text(file_lines, func_node)

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
        Go allows multiple names per type: func(a, b int) → [("int","a",-1), ("int","b",-1)]
        Unnamed params: func(int) → [("int","",-1)]
        """
        params: list[Tuple[str, str, int]] = []

        cursor = param_list_node.walk()
        if not cursor.goto_first_child():
            return params

        while True:
            node = cursor.node
            if node.type == "parameter_declaration":
                type_node = node.child_by_field_name("type")
                if type_node is None:
                    if cursor.goto_next_sibling():
                        continue
                    break
                type_str = _node_text(file_lines, type_node)

                # Multiple names are possible: func(a, b int)
                name_nodes = node.children_by_field_name("name")
                if name_nodes:
                    for name_node in name_nodes:
                        name_str = _node_text(file_lines, name_node)
                        params.append((type_str, name_str, -1))
                else:
                    # Unnamed parameter: func(int)
                    params.append((type_str, "", -1))

            elif node.type == "variadic_parameter_declaration":
                type_node = node.child_by_field_name("type")
                if type_node is None:
                    if cursor.goto_next_sibling():
                        continue
                    break
                type_str = f"...{_node_text(file_lines, type_node)}"

                name_node = node.child_by_field_name("name")
                name_str = _node_text(file_lines, name_node) if name_node else ""
                params.append((type_str, name_str, -1))

            if not cursor.goto_next_sibling():
                break

        return params

    def _extract_result_type(
        self, result_node: Node | None, file_lines: list[str]
    ) -> str:
        """Extract return type string from the result field."""
        if result_node is None:
            return ""

        if result_node.type == "parameter_list":
            # Multiple or named returns: (int, error) or (n int, err error)
            parts = []
            cursor = result_node.walk()
            if cursor.goto_first_child():
                while True:
                    node = cursor.node
                    if node.type == "parameter_declaration":
                        type_node = node.child_by_field_name("type")
                        if type_node:
                            parts.append(_node_text(file_lines, type_node))
                    elif node.type == "variadic_parameter_declaration":
                        type_node = node.child_by_field_name("type")
                        if type_node:
                            parts.append(f"...{_node_text(file_lines, type_node)}")
                    if not cursor.goto_next_sibling():
                        break
            return f"({', '.join(parts)})"
        else:
            # Single return type: error, int, *Foo, etc.
            return _node_text(file_lines, result_node)

    def _extract_receiver_type(self, receiver_node: Node, file_lines: list[str]) -> str:
        """Extract receiver type string from parameter_list receiver node."""
        cursor = receiver_node.walk()
        if not cursor.goto_first_child():
            return ""

        while True:
            node = cursor.node
            if node.type == "parameter_declaration":
                type_node = node.child_by_field_name("type")
                if type_node:
                    return _node_text(file_lines, type_node)
            if not cursor.goto_next_sibling():
                break

        return ""
