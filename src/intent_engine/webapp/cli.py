"""V1.0.1 webapp CLI — runserver, create-user, check-config. No action surface.

    PYTHONPATH=src python -m intent_engine.webapp runserver [--host H] [--port P]
    PYTHONPATH=src python -m intent_engine.webapp create-user EMAIL
    PYTHONPATH=src python -m intent_engine.webapp check-config
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys

from intent_engine.webapp.app import WebApp, make_server
from intent_engine.webapp.config import ConfigError, from_env


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="intent_engine.webapp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rs = sub.add_parser("runserver")
    rs.add_argument("--host", default="127.0.0.1")
    rs.add_argument("--port", type=int, default=8600)
    cu = sub.add_parser("create-user")
    cu.add_argument("email")
    cu.add_argument("--password", default=None,
                    help="omit to be prompted (preferred)")
    sub.add_parser("check-config")
    sub.add_parser("generate-bootstrap")

    args = ap.parse_args(argv)

    if args.cmd == "generate-bootstrap":
        # Runs entirely locally. Prints ONLY env-var assignments (email,
        # hash, random token) — never the plaintext password.
        import secrets as _secrets

        from intent_engine.webapp.auth import hash_password
        email = input("Email: ").strip().lower()
        if "@" not in email:
            print("ERROR: invalid email", file=sys.stderr)
            return 2
        password = getpass.getpass("Password (8+ chars): ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("ERROR: passwords do not match", file=sys.stderr)
            return 2
        try:
            password_hash = hash_password(password)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        token = _secrets.token_urlsafe(32)
        print(f"WEBAPP_BOOTSTRAP_EMAIL={email}")
        print(f"WEBAPP_BOOTSTRAP_PASSWORD_HASH={password_hash}")
        print(f"WEBAPP_BOOTSTRAP_TOKEN={token}")
        return 0

    try:
        config = from_env()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "check-config":
        print(json.dumps({"env": config.env, "valid": True,
                          "trusted_hosts": list(config.trusted_hosts),
                          "cookie_secure": config.cookie_secure,
                          "debug": config.debug,
                          "registration_open": config.registration_open}))
        return 0
    if args.cmd == "create-user":
        app = WebApp(config)
        password = args.password or getpass.getpass("Password (8+ chars): ")
        user_id = app.auth.create_user(args.email, password)
        print(json.dumps({"created": user_id, "email": args.email}))
        return 0
    if args.cmd == "runserver":
        app = WebApp(config)
        server = make_server(app, args.host, args.port)
        print(f"webapp [{config.env}] listening on "
              f"http://{args.host}:{server.server_port}")
        server.serve_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
