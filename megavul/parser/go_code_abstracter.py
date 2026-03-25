import logging
from typing import Callable
from tree_sitter import Node, Parser
from megavul.parser.code_abstracter_base import CodeAbstracterBase
from megavul.util.logging_util import global_logger


class GoCodeAbstracter(CodeAbstracterBase):
    """
    Code abstracter for Go functions.
    Abstracts identifiers, types, string/number/char literals, and comments
    in the same style as the Java and C/C++ abstracters.
    """

    def __init__(self, logger: logging.Logger):
        super().__init__(logger)
        self._parser = self.get_parser("go")

    @property
    def support_languages(self) -> list[str]:
        return ["go"]

    def find_parser(self, language: str) -> Parser:
        return self._parser

    def abstract_node(
        self,
        node: Node,
        node_abstract: Callable[[Node, str], None],
        abstract_type_map: dict[str, dict[str, str]],
    ):
        node_type = node.type

        if node_type == "identifier":
            parent = node.parent
            if parent is None:
                return

            # Keep function/method names and package names as-is
            if parent.type in (
                "function_declaration",
                "method_declaration",
                "package_clause",
            ):
                return

            # Keep the function name in a call expression
            if (
                parent.type == "call_expression"
                and parent.child_by_field_name("function") == node
            ):
                node_abstract(node, "FUNC")
                return

            # Keep the field part of a selector expression (qualified.Name)
            if (
                parent.type == "selector_expression"
                and parent.child_by_field_name("field") == node
            ):
                node_abstract(node, "FIELD")
                return

            # The selector itself (left side of x.y) – treat as VAR
            node_abstract(node, "VAR")

        elif node_type in ("type_identifier", "package_identifier"):
            # Keep built-in type names (int, string, bool, etc.) as-is
            parent = node.parent
            if parent is not None and parent.type in (
                "function_declaration",
                "method_declaration",
                "type_declaration",
                "type_spec",
            ):
                return
            node_abstract(node, "TYPE")

        elif node_type in (
            "interpreted_string_literal",
            "raw_string_literal",
        ):
            node_abstract(node, "STR")

        elif node_type == "comment":
            node_abstract(node, "COMMENT")

        elif node_type in (
            "int_literal",
            "float_literal",
            "imaginary_literal",
        ):
            node_abstract(node, "NUMBER")

        elif node_type == "rune_literal":
            node_abstract(node, "CHAR")


if __name__ == "__main__":
    abstracter = GoCodeAbstracter(global_logger)
    print(
        abstracter.abstract_code(
            """
func exampleHandler(w http.ResponseWriter, r *http.Request) error {
    // handle request
    name := r.URL.Query().Get("name")
    if name == "" {
        return fmt.Errorf("missing name parameter")
    }
    msg := fmt.Sprintf("Hello, %s!", name)
    w.WriteHeader(200)
    fmt.Fprintln(w, msg)
    return nil
}
""",
            "go",
        )[0]
    )
