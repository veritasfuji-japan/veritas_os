"""Example invocation for AML/KYC regulated action path fixture."""

from __future__ import annotations

import json

from veritas_os.governance.regulated_action_path import run_all_regulated_action_scenarios


if __name__ == "__main__":
    output = [item.to_dict() for item in run_all_regulated_action_scenarios()]
    print(json.dumps(output, ensure_ascii=False, indent=2))
