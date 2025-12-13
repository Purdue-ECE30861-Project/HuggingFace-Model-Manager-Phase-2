#!/usr/bin/env python3
import argparse
import json
import sys
import requests

# ===========================
# Global server configuration
# ===========================
SERVER_HOST = "18.118.161.226"
SERVER_PORT = 80

BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"


# ===========================
# Utility Helpers
# ===========================
def print_response(resp: requests.Response):
    print("STATUS:", resp.status_code)
    print("HEADERS:", dict(resp.headers))
    try:
        print("BODY:", resp.json())
    except Exception:
        print("BODY:", resp.text)


# ===========================
# Endpoint Implementations
# ===========================


# POST /artifacts
def cmd_get_artifacts(args):
    url = f"{BASE_URL}/artifacts"
    payload = {
        "artifact_type": args.artifact_type if hasattr(args, "artifact_type") else None
    }
    # actual ArtifactQuery fields must be filled by user
    try:
        query_obj = json.loads(args.query_json)
    except Exception:
        print("Invalid JSON for --query-json")
        sys.exit(1)

    params = {"offset": args.offset}

    resp = requests.post(url, json=query_obj, params=params)
    print_response(resp)


# POST /artifact/byName/{name}
def cmd_get_artifacts_by_name(args):
    url = f"{BASE_URL}/artifact/byName/{args.name}"
    resp = requests.post(url)
    print_response(resp)


# POST /artifact/byRegEx
def cmd_get_artifacts_by_regex(args):
    url = f"{BASE_URL}/artifact/byRegEx"

    try:
        regex_payload = json.loads(args.regex_json)
    except Exception:
        print("Invalid JSON for --regex-json")
        sys.exit(1)

    resp = requests.post(url, json=regex_payload)
    print_response(resp)


# GET /artifacts/{artifact_type}/{id}
def cmd_get_artifact(args):
    url = f"{BASE_URL}/artifacts/{args.artifact_type}/{args.id}"
    resp = requests.get(url)
    print_response(resp)


# PUT /artifacts/{artifact_type}/{id}
def cmd_update_artifact(args):
    url = f"{BASE_URL}/artifacts/{args.artifact_type}/{args.id}"
    try:
        payload = json.loads(args.artifact_json)
    except Exception:
        print("Invalid JSON for --artifact-json")
        sys.exit(1)

    resp = requests.put(url, json=payload)
    print_response(resp)


# DELETE /artifacts/{artifact_type}/{id}
def cmd_delete_artifact(args):
    url = f"{BASE_URL}/artifacts/{args.artifact_type}/{args.id}"
    resp = requests.delete(url)
    print_response(resp)


# POST /artifacts/{artifact_type}
def cmd_register_artifact(args):
    url = f"{BASE_URL}/artifact/{args.artifact_type}"
    print(url)
    try:
        payload = {
            "url": str(args.url),
            "download_url": "",
        }
    except Exception:
        print("Invalid arguments for register_artifact")
        sys.exit(1)

    resp = requests.post(url, json=payload)
    print_response(resp)


def cmd_reset(args):
    url = f"{BASE_URL}/reset"
    resp = requests.delete(url)
    print_response(resp)


def cmd_get_audit_history(args):
    url = f"{BASE_URL}/artifact/{args.artifact_type}/{args.id}/audit"
    resp = requests.get(url)
    print_response(resp)


def cmd_get_cost(args):
    url = f"{BASE_URL}/artifact/{args.artifact_type}/{args.id}/cost"
    params = {"dependency": str(args.dependency).lower()}
    resp = requests.get(url, params=params)
    print_response(resp)


def cmd_get_model_lineage(args):
    url = f"{BASE_URL}/artifact/model/{args.id}/lineage"
    resp = requests.get(url)
    print_response(resp)


def cmd_rate_model(args):
    url = f"{BASE_URL}/artifact/model/{args.id}/rate"
    resp = requests.get(url)
    print_response(resp)


# ===========================
# Argument Parser
# ===========================


def build_parser():
    parser = argparse.ArgumentParser(description="CLI client for backend artifact API")
    sub = parser.add_subparsers(dest="command", required=True)

    # /artifacts (POST)
    p = sub.add_parser("get-artifacts", help="POST /artifacts")
    p.add_argument("--offset", required=True, help="numeric offset")
    p.add_argument("--query-json", required=True, help="ArtifactQuery JSON object")
    p.set_defaults(func=cmd_get_artifacts)

    # /artifact/byName/{name}
    p = sub.add_parser("get-by-name", help="POST /artifact/byName/{name}")
    p.add_argument("name")
    p.set_defaults(func=cmd_get_artifacts_by_name)

    # /artifact/byRegEx
    p = sub.add_parser("get-by-regex", help="POST /artifact/byRegEx")
    p.add_argument("--regex-json", required=True, help="ArtifactRegEx JSON object")
    p.set_defaults(func=cmd_get_artifacts_by_regex)

    # GET /artifacts/{artifact_type}/{id}
    p = sub.add_parser("get-artifact", help="GET /artifacts/{artifact_type}/{id}")
    p.add_argument("artifact_type")
    p.add_argument("id")
    p.set_defaults(func=cmd_get_artifact)

    # PUT /artifacts/{artifact_type}/{id}
    p = sub.add_parser("update-artifact", help="PUT /artifacts/{artifact_type}/{id}")
    p.add_argument("artifact_type")
    p.add_argument("id")
    p.add_argument("--artifact-json", required=True, help="Full Artifact JSON")
    p.set_defaults(func=cmd_update_artifact)

    # DELETE /artifacts/{artifact_type}/{id}
    p = sub.add_parser("delete-artifact", help="DELETE /artifacts/{artifact_type}/{id}")
    p.add_argument("artifact_type")
    p.add_argument("id")
    p.set_defaults(func=cmd_delete_artifact)

    # POST /artifacts/{artifact_type}
    p = sub.add_parser("register-artifact", help="POST /artifacts/{artifact_type}")
    p.add_argument("artifact_type")
    p.add_argument("--url", required=True)
    p.add_argument("--download-url", required=False)
    p.set_defaults(func=cmd_register_artifact)

    p = sub.add_parser("reset", help="DELETE /reset")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("get-audit", help="GET /artifact/{type}/{id}/audit")
    p.add_argument("artifact_type")
    p.add_argument("id")
    p.set_defaults(func=cmd_get_audit_history)

    p = sub.add_parser("get-cost", help="GET /artifact/{type}/{id}/cost")
    p.add_argument("artifact_type")
    p.add_argument("id")
    p.add_argument(
        "--dependency",
        required=True,
        choices=["true", "false"],
        help="Whether to compute dependency cost",
    )
    p.set_defaults(func=cmd_get_cost)

    p = sub.add_parser("get-lineage", help="GET /artifact/model/{id}/lineage")
    p.add_argument("id")
    p.set_defaults(func=cmd_get_model_lineage)

    p = sub.add_parser("rate-model", help="GET /artifact/model/{id}/rate")
    p.add_argument("id")
    p.set_defaults(func=cmd_rate_model)

    return parser


# ===========================
# Entry Point
# ===========================
def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
