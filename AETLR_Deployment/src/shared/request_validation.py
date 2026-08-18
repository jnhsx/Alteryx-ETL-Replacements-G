from typing import Iterable

import azure.functions as func


def get_required_request_fields(
    payload: dict,
    req: func.HttpRequest,
    field_names: Iterable[str],
) -> dict[str, str]:
    missing: list[str] = []
    values: dict[str, str] = {}

    for name in field_names:
        value = payload.get(name) or req.params.get(name)
        if value is None or str(value).strip() == "":
            missing.append(name)
        else:
            values[name] = str(value).strip()

    if missing:
        raise ValueError(
            "Missing required request parameters: " + ", ".join(missing)
        )

    return values
