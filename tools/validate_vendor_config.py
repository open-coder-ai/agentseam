#!/usr/bin/env python3
"""A minimal, stdlib-only JSON Schema validator for `data/vendors/schema.json`.

    python3 tools/validate_vendor_config.py

Not a general JSON Schema engine: it implements exactly the constructs `schema.json` uses
(`type`, `enum`, `pattern`, `additionalProperties`, `required`, `properties`, `items`,
`minLength`, `minItems`, `$ref`/`$defs`, and one `if`/`then` with a `const` guard) --
enough to actually execute the schema rather than duplicate them by hand, without pulling
in a third-party dependency this stdlib-only project does not otherwise need.

Called from `tests/test_vendor_config.py` as the validator-as-test (dialect-families.md
§3.3: "validation is a test, not a runtime cost").
"""

from __future__ import annotations

import re


def validate(schema, instance, root=None, path="$"):
    """Every violation of `schema` against `instance`, as human-readable strings."""
    root = schema if root is None else root
    if "$ref" in schema:
        return validate(_resolve(schema["$ref"], root), instance, root, path)

    errors = []
    errors.extend(_check_type(schema, instance, path))
    if errors:
        return errors  # a type mismatch makes every other check meaningless noise

    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: %r is not one of %r" % (path, instance, schema["enum"]))
    if "pattern" in schema and isinstance(instance, str) and not re.match(schema["pattern"], instance):
        errors.append("%s: %r does not match pattern %r" % (path, instance, schema["pattern"]))
    if "minLength" in schema and isinstance(instance, str) and len(instance) < schema["minLength"]:
        errors.append("%s: %r shorter than minLength %d" % (path, instance, schema["minLength"]))
    if "minItems" in schema and isinstance(instance, (list, tuple)) and len(instance) < schema["minItems"]:
        errors.append("%s: fewer than minItems %d" % (path, schema["minItems"]))

    if isinstance(instance, dict):
        errors.extend(_check_object(schema, instance, root, path))
    if isinstance(instance, (list, tuple)) and "items" in schema:
        for i, item in enumerate(instance):
            errors.extend(validate(schema["items"], item, root, "%s[%d]" % (path, i)))

    if "if" in schema:
        cond = schema["if"]
        if not _check_type(cond, instance, path) and _matches(cond, instance):
            errors.extend(validate(schema.get("then", {}), instance, root, path))

    return errors


def _resolve(ref, root):
    assert ref.startswith("#/"), "only local $ref is supported: %r" % (ref,)
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _json_type(instance):
    if isinstance(instance, bool):
        return "boolean"
    if isinstance(instance, str):
        return "string"
    if isinstance(instance, (int, float)):
        return "number"
    if isinstance(instance, (list, tuple)):
        return "array"
    if isinstance(instance, dict):
        return "object"
    if instance is None:
        return "null"
    return "unknown"


def _check_type(schema, instance, path):
    expected = schema.get("type")
    if expected is None:
        return []
    allowed = (expected,) if isinstance(expected, str) else tuple(expected)
    if _json_type(instance) not in allowed:
        return ["%s: expected type %r, got %r (%r)" % (path, allowed, _json_type(instance), instance)]
    return []


def _matches(schema, instance):
    """True when `instance` (assumed the right shape) satisfies every keyword in `schema`."""
    if isinstance(instance, dict) and "properties" in schema:
        for key, subschema in schema["properties"].items():
            if key in instance and "const" in subschema and instance[key] != subschema["const"]:
                return False
    return True


def _check_object(schema, instance, root, path):
    errors = []
    for key in schema.get("required", ()):
        if key not in instance:
            errors.append("%s: missing required property %r" % (path, key))
    properties = schema.get("properties", {})
    additional = schema.get("additionalProperties", True)
    for key, value in instance.items():
        if key in properties:
            errors.extend(validate(properties[key], value, root, "%s.%s" % (path, key)))
        elif additional is False:
            errors.append("%s: unknown property %r" % (path, key))
        elif isinstance(additional, dict):
            errors.extend(validate(additional, value, root, "%s.%s" % (path, key)))
    return errors


def main():
    import json
    import os
    import sys

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    vendors_dir = os.path.join(root, "src", "agentseam", "data", "vendors")
    with open(os.path.join(vendors_dir, "schema.json"), encoding="utf-8") as fh:
        schema = json.load(fh)

    failed = False
    for name in sorted(os.listdir(vendors_dir)):
        if name == "schema.json" or not name.endswith(".json"):
            continue
        with open(os.path.join(vendors_dir, name), encoding="utf-8") as fh:
            entry = json.load(fh)
        errors = validate(schema, entry)
        if errors:
            failed = True
            print("%s:" % name)
            for error in errors:
                print("  " + error)
        else:
            print("%s: ok" % name)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
