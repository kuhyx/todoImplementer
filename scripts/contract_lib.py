"""Load every contracts/*.schema.json into one registry and validate instances against them."""

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"
BASE = "https://todoimplementer.local/contracts/"


def registry(directory: Path = CONTRACTS) -> Registry:
    """Return a registry holding every schema in the directory, keyed by its $id."""
    reg: Registry = Registry()
    for path in sorted(directory.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        reg = reg.with_resource(
            schema["$id"], Resource.from_contents(schema, default_specification=DRAFT202012)
        )
    return reg


def validator(name: str, fragment: str = "") -> Draft202012Validator:
    """Return a validator for contracts/<name>.schema.json, or for its #/$defs/<fragment>."""
    reg = registry()
    ref = {"$ref": f"{BASE}{name}.schema.json{'#/$defs/' + fragment if fragment else ''}"}
    return Draft202012Validator(ref, registry=reg)


def validate(name: str, instance: Any, fragment: str = "") -> None:  # noqa: ANN401 - any JSON value
    """Raise jsonschema.ValidationError when the instance breaks the contract."""
    validator(name, fragment).validate(instance)
