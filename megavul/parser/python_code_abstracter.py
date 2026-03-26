import logging
from typing import Callable
from tree_sitter import Node, Parser
from megavul.parser.code_abstracter_base import CodeAbstracterBase
from megavul.util.logging_util import global_logger


class PythonCodeAbstracter(CodeAbstracterBase):
    """
    Code abstracter for Python functions.
    Abstracts identifiers, literals, strings, and comments
    in the same style as the Go and Java abstracters.
    """

    def __init__(self, logger: logging.Logger):
        super().__init__(logger)
        self._parser = self.get_parser("python")

    @property
    def support_languages(self) -> list[str]:
        return ["python"]

    def find_parser(self, language: str) -> Parser:
        return self._parser

    def abstract_node(
        self,
        node: Node,
        node_abstract: Callable[[Node, str], None],
        abstract_type_map: dict[str, dict[str, str]],
    ):
        node_type = node.type
        parent = node.parent

        if node_type == "identifier":
            if parent is None:
                return

            # Keep function/method names in definitions
            if (
                parent.type == "function_definition"
                and parent.child_by_field_name("name") == node
            ):
                return

            # Keep class names in definitions
            if (
                parent.type == "class_definition"
                and parent.child_by_field_name("name") == node
            ):
                return

            # Keep the function name in a call expression
            if parent.type == "call" and parent.child_by_field_name("function") == node:
                node_abstract(node, "FUNC")
                return

            # Keep the attribute part of an attribute access (obj.attr → attr is FIELD)
            if (
                parent.type == "attribute"
                and parent.child_by_field_name("attribute") == node
            ):
                node_abstract(node, "FIELD")
                return

            # Decorator names
            if parent.type == "decorator":
                node_abstract(node, "ANNOTATION")
                return

            node_abstract(node, "VAR")

        elif node_type in ("string", "concatenated_string"):
            node_abstract(node, "STR")

        elif node_type == "comment":
            node_abstract(node, "COMMENT")

        elif node_type in ("integer", "float"):
            node_abstract(node, "NUMBER")


if __name__ == "__main__":
    abstracter = PythonCodeAbstracter(global_logger)
    print(
        abstracter.abstract_code(
            """\
def process_data(items, threshold=10):
    # filter items above threshold
    result = []
    for item in items:
        value = item.get_value()
        if value > threshold:
            result.append(value)
    return result
""",
            "python",
        )[0]
    )
