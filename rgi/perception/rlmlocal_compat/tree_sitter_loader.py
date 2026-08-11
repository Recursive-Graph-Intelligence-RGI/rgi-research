"""Lazy tree-sitter parser loader ported from rlmlocal's treeSitter.ts.

Each language grammar is imported on first use and cached. This keeps startup
fast and avoids hard dependencies on grammars the user does not need.
"""
import importlib
from pathlib import Path

from tree_sitter import Language, Parser, Tree

from rgi.perception.rlmlocal_compat.language_packs import (
    LANGUAGE_PACKS,
    LanguagePack,
    pack_for_extension,
)

_PARSER_CACHE: dict[str, Parser] = {}


def load_parser(pack: LanguagePack) -> Parser:
    """Return a tree-sitter Parser for the given language pack."""
    if pack.grammar_module in _PARSER_CACHE:
        return _PARSER_CACHE[pack.grammar_module]
    try:
        grammar = importlib.import_module(pack.grammar_module)
    except ImportError as exc:
        raise ImportError(
            f"Grammar package '{pack.grammar_module}' is not installed. "
            f"Install it (e.g. pip install {pack.grammar_module}) to parse {pack.family} files."
        ) from exc
    language_fn = getattr(grammar, pack.language_attr)
    language = Language(language_fn())
    parser = Parser(language)
    _PARSER_CACHE[pack.grammar_module] = parser
    return parser


def parse_file(path: Path) -> Tree | None:
    """Parse a source file into a tree-sitter Tree.

    Returns None if the file extension is not supported. Raises if the grammar
    package is not installed.
    """
    pack = pack_for_extension(path.suffix)
    if pack is None:
        return None
    parser = load_parser(pack)
    return parser.parse(path.read_bytes())
