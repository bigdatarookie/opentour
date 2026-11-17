#!/usr/bin/env python3
"""Plan/apply one exact existing client binding; never submits a business event."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sqlite3
from contextlib import closing

from backend.adapters import Failure, NativeObligation, private_json
from backend.board_store import BoardStore
from backend.client_conversations import ClientControls
from backend.client_binding import plan_binding_read, apply_binding, validate_plan
from backend.core import version
from tools.local_board_release import _connect_readonly, ReleaseError


def actual_actor():
    result = subprocess.run(['rig', 'whoami', '--json'], capture_output=True, check=True, timeout=12)
    if len(result.stdout) > 65536:raise Failure('client_binding_actor_unavailable', 503)
    identity = json.loads(result.stdout).get('identity', {})
    allowed = {'engineering.platform': 'engineering-platform@engineering-rig',
               'infrastructure.engineer': 'infrastructure-engineer@engineering-rig'}
    if (identity.get('rigName') != 'engineering-rig' or not identity.get('nodeId') or
            identity.get('sessionName') != allowed.get(identity.get('logicalId'))):
        raise Failure('client_binding_actor_forbidden', 403)
    return 'native:'+identity['sessionName']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--board-db', type=Path, required=True)
    p.add_argument('--client-controls-file', type=Path, required=True)
    p.add_argument('--task-id', required=True)
    p.add_argument('--previous-ref', required=True)
    p.add_argument('--event-request-id', required=True)
    p.add_argument('--apply-plan', type=Path)
    p.add_argument('--expected-plan-sha256')
    p.add_argument('--request-id')
    args = p.parse_args()
    try:
        actor = actual_actor()
        with closing(_connect_readonly(args.board_db)) as db:
            if db.execute('PRAGMA user_version').fetchone()[0] != 5:
                raise Failure('client_binding_schema_not_qualified', 409)
        controls = ClientControls(args.client_controls_file)
        native = NativeObligation()
        if args.apply_plan:
            if not args.request_id or not re.fullmatch('[a-f0-9]{64}', args.expected_plan_sha256 or ''):
                raise Failure('client_binding_plan_identity_required', 400)
            document = private_json(args.apply_plan)
            if (isinstance(document, dict) and set(document) == {'status', 'plan', 'planSha256'}
                    and document['status'] == 'PLANNED_READ_ONLY'
                    and document['planSha256'] == args.expected_plan_sha256):
                plan = document['plan']
            else:
                plan = document
            validate_plan(plan, args.expected_plan_sha256)
            if (plan.get('taskId') != args.task_id or plan.get('previousRef') != args.previous_ref or
                    plan.get('originalEventRequestId') != args.event_request_id):
                raise Failure('client_binding_plan_identity_mismatch', 409)
            result = apply_binding(BoardStore(args.board_db), plan, args.expected_plan_sha256,
                                   args.request_id, actor, controls, native)
        else:
            plan = plan_binding_read(args.board_db, args.task_id, args.previous_ref,
                                     args.event_request_id, controls, native)
            result = {'status': 'PLANNED_READ_ONLY', 'plan': plan, 'planSha256': version(plan)}
        print(json.dumps(result, sort_keys=True))
    except (Failure, ReleaseError, OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'ERROR', 'code': exc.code if isinstance(exc, Failure) else 'client_binding_unavailable'}))
        raise SystemExit(1)


if __name__ == '__main__': main()
