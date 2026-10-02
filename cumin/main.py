import os
import secrets

import uvicorn

from src.app import bootstrap_tenant, create_app, limiter_from_env
from src.services.db import Database
from src.services.moderation import OpenAIModerator
from src.services.openai_inference import OpenAIInference


def main() -> None:
    database = Database(os.environ.get("CUMIN_DB", "data/cumin.db"))
    raw_key = bootstrap_tenant(database)
    if raw_key is None:
        print("tenant acme already exists; use the key issued on the first run")
    else:
        print(f"issued key: {raw_key}")
    admin_token = os.environ.get("CUMIN_ADMIN_TOKEN") or secrets.token_urlsafe(18)
    port = int(os.environ.get("CUMIN_PORT", "8000"))
    print(f"admin dashboard: http://127.0.0.1:{port}/admin")
    print(f"admin token: {admin_token}")
    print("summarize: POST /v1/summarize  Authorization: Bearer <key>  {\"url\": \"https://example.com\"}")
    app = create_app(
        database,
        OpenAIInference(),
        moderator=OpenAIModerator(),
        limiter=limiter_from_env(),
        admin_token=admin_token,
    )
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
