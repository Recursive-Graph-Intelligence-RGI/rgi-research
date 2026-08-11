"""Language-pack table ported from rlmlocal-site's languagePacks.ts.

A LanguagePack defines how to parse and extract structure for one language
family. The table is pure data and can be consumed by both the tree-sitter
loader and the structure extractor without importing grammar-specific code.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class LanguagePack:
    family: str  # e.g. "python", "js", "go", "rust"
    grammar_module: str  # pip package name, e.g. "tree_sitter_python"
    extensions: tuple[str, ...]
    test_file_regex: str
    call_expression_node_type: str
    function_like_node_types: tuple[str, ...]
    method_container_types: tuple[str, ...]
    language_attr: str = "language"  # attribute on the grammar module that returns the Language


LANGUAGE_PACKS: dict[str, LanguagePack] = {
    "python": LanguagePack(
        family="python",
        grammar_module="tree_sitter_python",
        extensions=(".py",),
        test_file_regex=r"(_test|test_)\.py$|tests?/.*\.py$",
        call_expression_node_type="call",
        function_like_node_types=("function_definition", "lambda"),
        method_container_types=("class_definition",),
    ),
    "javascript": LanguagePack(
        family="js",
        grammar_module="tree_sitter_javascript",
        extensions=(".js", ".jsx", ".mjs", ".cjs"),
        test_file_regex=r"\.(test|spec)\.(js|jsx|mjs|cjs)$",
        call_expression_node_type="call_expression",
        function_like_node_types=(
            "function_declaration",
            "function_expression",
            "arrow_function",
            "method_definition",
        ),
        method_container_types=("class_declaration", "object"),
    ),
    "typescript": LanguagePack(
        family="js",
        grammar_module="tree_sitter_typescript",
        extensions=(".ts", ".mts", ".cts"),
        test_file_regex=r"\.(test|spec)\.(ts|mts|cts)$",
        call_expression_node_type="call_expression",
        function_like_node_types=(
            "function_declaration",
            "function_expression",
            "arrow_function",
            "method_definition",
        ),
        method_container_types=("class_declaration", "interface_declaration", "object"),
        language_attr="language_typescript",
    ),
    "tsx": LanguagePack(
        family="js",
        grammar_module="tree_sitter_typescript",
        extensions=(".tsx",),
        test_file_regex=r"\.(test|spec)\.(tsx)$",
        call_expression_node_type="call_expression",
        function_like_node_types=(
            "function_declaration",
            "function_expression",
            "arrow_function",
            "method_definition",
        ),
        method_container_types=("class_declaration", "interface_declaration", "object"),
        language_attr="language_tsx",
    ),
    "go": LanguagePack(
        family="go",
        grammar_module="tree_sitter_go",
        extensions=(".go",),
        test_file_regex=r"_test\.go$",
        call_expression_node_type="call_expression",
        function_like_node_types=("function_declaration", "func_literal", "method_declaration"),
        method_container_types=("type_declaration",),
    ),
    "rust": LanguagePack(
        family="rust",
        grammar_module="tree_sitter_rust",
        extensions=(".rs",),
        test_file_regex=r"#\[cfg(test)\]",
        call_expression_node_type="call_expression",
        function_like_node_types=("function_item", "closure_expression"),
        method_container_types=("impl_item", "trait_item"),
    ),
}

_EXTENSION_TO_PACK: dict[str, LanguagePack] = {
    ext: pack for pack in LANGUAGE_PACKS.values() for ext in pack.extensions
}


def lang_family(ext: str) -> str | None:
    """Return the language family for a file extension, or None."""
    pack = _EXTENSION_TO_PACK.get(ext.lower())
    return pack.family if pack else None


def supported_extensions() -> set[str]:
    """Return the set of supported file extensions."""
    return set(_EXTENSION_TO_PACK.keys())


def pack_for_extension(ext: str) -> LanguagePack | None:
    """Return the full LanguagePack for a file extension, or None."""
    return _EXTENSION_TO_PACK.get(ext.lower())
