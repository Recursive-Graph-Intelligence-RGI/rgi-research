from rgi.perception.rlmlocal_compat.language_packs import (
    LANGUAGE_PACKS,
    LanguagePack,
    lang_family,
    pack_for_extension,
    supported_extensions,
)


def test_python_pack_exists():
    pack = LANGUAGE_PACKS["python"]
    assert isinstance(pack, LanguagePack)
    assert pack.family == "python"
    assert ".py" in pack.extensions


def test_lang_family_python():
    assert lang_family(".py") == "python"


def test_lang_family_javascript_typescript():
    assert lang_family(".js") == "js"
    assert lang_family(".ts") == "js"
    assert lang_family(".jsx") == "js"
    assert lang_family(".tsx") == "js"


def test_lang_family_go():
    assert lang_family(".go") == "go"


def test_lang_family_rust():
    assert lang_family(".rs") == "rust"


def test_lang_family_unknown():
    assert lang_family(".unknown") is None


def test_supported_extensions_includes_all():
    for ext in (".py", ".js", ".ts", ".go", ".rs"):
        assert ext in supported_extensions()


def test_pack_for_extension():
    pack = pack_for_extension(".py")
    assert pack is not None
    assert pack.family == "python"
    ts_pack = pack_for_extension(".ts")
    assert ts_pack is not None
    assert ts_pack.grammar_module == "tree_sitter_typescript"
    assert pack_for_extension(".nope") is None
