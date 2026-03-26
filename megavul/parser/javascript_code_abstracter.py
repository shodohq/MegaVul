import logging
from typing import Callable
from tree_sitter import Node, Parser
from megavul.parser.code_abstracter_base import CodeAbstracterBase
from megavul.util.logging_util import global_logger


class JavaScriptCodeAbstracter(CodeAbstracterBase):
    """
    Code abstracter for JavaScript functions.
    Abstracts identifiers, string/template/number literals, and comments
    in the same style as the Go and Java abstracters.
    """

    def __init__(self, logger: logging.Logger):
        super().__init__(logger)
        self._parser = self.get_parser("javascript")

    @property
    def support_languages(self) -> list[str]:
        return ["javascript", "js"]

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

            # Keep top-level function/class declaration names as-is
            if (
                parent.type
                in (
                    "function_declaration",
                    "class_declaration",
                )
                and parent.child_by_field_name("name") == node
            ):
                return

            # Keep method definition names as-is
            if (
                parent.type == "method_definition"
                and parent.child_by_field_name("name") == node
            ):
                return

            # Keep the callee in a call expression (direct function call)
            if (
                parent.type == "call_expression"
                and parent.child_by_field_name("function") == node
            ):
                node_abstract(node, "FUNC")
                return

            # Keep the property in a member expression (obj.property)
            if (
                parent.type == "member_expression"
                and parent.child_by_field_name("property") == node
            ):
                node_abstract(node, "FIELD")
                return

            node_abstract(node, "VAR")

        elif node_type == "property_identifier":
            parent = node.parent
            if parent is None:
                node_abstract(node, "FIELD")
                return

            # Keep method/property names in class / object definitions
            if parent.type in ("method_definition", "pair"):
                return

            node_abstract(node, "FIELD")

        elif node_type in (
            "string",
            "template_string",
        ):
            node_abstract(node, "STR")

        elif node_type == "number":
            node_abstract(node, "NUMBER")

        elif node_type in ("comment", "html_comment"):
            node_abstract(node, "COMMENT")


if __name__ == "__main__":
    abstracter = JavaScriptCodeAbstracter(global_logger)
    print(
        abstracter.abstract_code(
            """
function processRequest(req, res) {
    // validate input
    const name = req.query.name;
    if (!name || name === "") {
        res.status(400).send("missing name parameter");
        return;
    }
    const msg = `Hello, ${name}!`;
    res.status(200).send(msg);
}
""",
            "javascript",
        )[0]
    )
