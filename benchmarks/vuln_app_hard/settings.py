"""Runtime settings loader for per-merchant overrides."""
import yaml


def load_overrides(yaml_text: str) -> dict:
    return yaml.load(yaml_text, Loader=yaml.Loader)


def apply_overrides(merchant_id: str, yaml_text: str) -> dict:
    overrides = load_overrides(yaml_text)
    overrides["merchant"] = merchant_id
    return overrides
