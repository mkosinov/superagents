#!/usr/bin/env python3
"""gh_board.py — GH Project #3 (Memo Project) board management for @manager.

Usage:
  python3 .opencode/skills/github-board/scripts/gh_board.py next-up              — show the trajectory (Next Up 1→3)
  python3 .opencode/skills/github-board/scripts/gh_board.py set-next-up N 1|2|3|none  — set/clear queue position
  python3 .opencode/skills/github-board/scripts/gh_board.py shift                — after Next Up 1 completes: clear it, shift 2→1, 3→2
  python3 .opencode/skills/github-board/scripts/gh_board.py status N "In IMPL"         — move a card's status

Project constants are hardcoded (IDs are stable for Project #3).
"""
import json
import subprocess
import sys

# Configure per project. Get IDs via:
#   gh api graphql -f query='query { user(login: "<owner>") { projectV2(number: <N>) { id fields(first: 30) { nodes { ... on ProjectV2SingleSelectField { name id options { id name } } } } } } }'
# Values below are for the reference project (memo, Project #3).
PROJECT_ID = "PVT_kwHOA-0Z984BXl3Z"
OWNER = "mkosinov"
REPO = "memo"
PROJECT_NUM = 3

NEXT_UP_FIELD = "PVTSSF_lAHOA-0Z984BXl3ZzhZEGRs"
NEXT_UP_OPTS = {"1": "ad936c13", "2": "8167d82e", "3": "ece04007"}

# Статусы доски (актуальные для Project #3)
STATUSES = [
    "Backlog", "In Design (G1a)", "Spec OK (G1b)", "Ready to IMPL (G2)",
    "In IMPL", "PR (G7)", "In-main", "deployed",
]

_status_field_id = None
_status_opts = None


def gql(query: str) -> dict:
    r = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"gh api error: {r.stderr.strip()}")
    data = json.loads(r.stdout)
    if "errors" in data:
        sys.exit(f"graphql errors: {data['errors']}")
    return data["data"]


def load_status_field():
    global _status_field_id, _status_opts
    if _status_field_id:
        return
    d = gql(f'query {{ node(id: "{PROJECT_ID}") {{ ... on ProjectV2 {{ fields(first: 30) {{ nodes {{ __typename ... on ProjectV2SingleSelectField {{ id name options {{ id name }} }} }} }} }} }} }}')
    for f in d["node"]["fields"]["nodes"]:
        if f["__typename"] == "ProjectV2SingleSelectField" and f["name"] == "Status":
            _status_field_id = f["id"]
            _status_opts = {o["name"]: o["id"] for o in f["options"]}
            return
    sys.exit("Status field not found")


def items_with_fields() -> list[dict]:
    d = gql(f'''query {{ node(id: "{PROJECT_ID}") {{ ... on ProjectV2 {{ items(first: 100) {{ nodes {{
        id
        content {{ ... on Issue {{ number title state }} }}
        fieldValues(first: 20) {{ nodes {{
            ... on ProjectV2ItemFieldSingleSelectValue {{ name field {{ ... on ProjectV2FieldCommon {{ name }} }} }}
        }} }}
    }} }} }} }} }}''')
    out = []
    for it in d["node"]["items"]["nodes"]:
        c = it.get("content")
        if not c or "number" not in c:
            continue
        vals = {v["field"]["name"]: v["name"] for v in it["fieldValues"]["nodes"] if v}
        out.append({
            "item_id": it["id"],
            "number": c["number"],
            "title": c["title"],
            "state": c["state"],
            "status": vals.get("Status"),
            "next_up": vals.get("Next Up"),
        })
    return out


def find_item(number: int) -> dict:
    for it in items_with_fields():
        if it["number"] == number:
            return it
    # не на доске — добавить
    d = gql(f'query {{ repository(owner: "{OWNER}", name: "{REPO}") {{ issue(number: {number}) {{ id title state }} }} }}')
    issue = d["repository"]["issue"]
    if not issue:
        sys.exit(f"Issue #{number} not found")
    d2 = gql(f'mutation {{ addProjectV2ItemById(input: {{ projectId: "{PROJECT_ID}", contentId: "{issue["id"]}" }}) {{ item {{ id }} }} }}')
    return {
        "item_id": d2["addProjectV2ItemById"]["item"]["id"],
        "number": number, "title": issue["title"], "state": issue["state"],
        "status": None, "next_up": None,
    }


def set_field(item_id: str, field_id: str, option_id: str | None):
    value = f'value: {{ singleSelectOptionId: "{option_id}" }}' if option_id else "value: {}"
    # очистка single-select — пустое value не поддерживается; используем clear mutation
    if option_id is None:
        gql(f'mutation {{ clearProjectV2ItemFieldValue(input: {{ projectId: "{PROJECT_ID}", itemId: "{item_id}", fieldId: "{field_id}" }}) {{ projectV2Item {{ id }} }} }}')
    else:
        gql(f'mutation {{ updateProjectV2ItemFieldValue(input: {{ projectId: "{PROJECT_ID}", itemId: "{item_id}", fieldId: "{field_id}", {value} }}) {{ projectV2Item {{ id }} }} }}')


def cmd_next_up():
    items = [it for it in items_with_fields() if it["next_up"] and it["state"] == "OPEN"]
    items.sort(key=lambda x: x["next_up"])
    if not items:
        print("Trajectory is empty — no open issue has Next Up set.")
        return
    print("Trajectory (Next Up):")
    for it in items:
        print(f"  {it['next_up']}. #{it['number']} [{it['status'] or 'no status'}] {it['title']}")


def cmd_set_next_up(number: int, pos: str):
    it = find_item(number)
    if pos == "none":
        set_field(it["item_id"], NEXT_UP_FIELD, None)
        print(f"#{number}: Next Up cleared")
        return
    if pos not in NEXT_UP_OPTS:
        sys.exit("pos must be 1|2|3|none")
    # conflict: if the position is taken by another issue — clear it there
    for other in items_with_fields():
        if other["next_up"] == pos and other["number"] != number:
            set_field(other["item_id"], NEXT_UP_FIELD, None)
            print(f"#{other['number']}: Next Up {pos} freed (was occupied)")
    set_field(it["item_id"], NEXT_UP_FIELD, NEXT_UP_OPTS[pos])
    print(f"#{number}: Next Up = {pos}")


def cmd_shift():
    items = {it["next_up"]: it for it in items_with_fields() if it["next_up"]}
    if "1" in items:
        set_field(items["1"]["item_id"], NEXT_UP_FIELD, None)
        print(f"#{items['1']['number']}: Next Up 1 cleared (completed)")
    for src, dst in (("2", "1"), ("3", "2")):
        if src in items:
            set_field(items[src]["item_id"], NEXT_UP_FIELD, NEXT_UP_OPTS[dst])
            print(f"#{items[src]['number']}: Next Up {src} → {dst}")
    print("Queue shifted. Position 3 is free.")


def cmd_status(number: int, status: str):
    load_status_field()
    if status not in _status_opts:
        sys.exit(f"Unknown status '{status}'. Available: {', '.join(STATUSES)}")
    it = find_item(number)
    set_field(it["item_id"], _status_field_id, _status_opts[status])
    print(f"#{number}: Status → {status}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    cmd = args[0]
    if cmd == "next-up":
        cmd_next_up()
    elif cmd == "set-next-up" and len(args) == 3:
        cmd_set_next_up(int(args[1]), args[2])
    elif cmd == "shift":
        cmd_shift()
    elif cmd == "status" and len(args) == 3:
        cmd_status(int(args[1]), args[2])
    else:
        print(__doc__)
        sys.exit(1)
