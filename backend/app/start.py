import os
from collections.abc import Mapping

import uvicorn


def port_from_environment(
    environ: Mapping[str, str] | None = None,
) -> int:
    values = os.environ if environ is None else environ
    raw_port = values.get("PORT", "").strip()
    if not raw_port:
        raise ValueError("PORT environment variable is required.")
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("PORT must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535.")
    return port


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port_from_environment(),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
