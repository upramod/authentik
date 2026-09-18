# SCIM policy group removal: targeted fix

## Implementation

Revision: `9dc70fa1c97d1481e7c8da767babf5d9d286d643`.

The membership actor first updates the remote group while user mappings are
available. For a removal event, it then checks current application access for
the affected users. It deletes only this provider's mapped accounts that now
fall outside that access scope.

This check still runs when group filters exclude the changed group, its local
SCIM mapping is absent, or its remote endpoint returns 404. Other event actions
keep the prior 404 behavior. Another valid binding, or restored membership before
processing, preserves the user account.

The user client now removes its local mapping only after a successful remote
DELETE or a 404 indicating that the remote account is already absent. Failed
requests and dry-run requests preserve the mapping. Transient cleanup errors
raise the existing task retry signal.

Production changes are limited to:

- `authentik/providers/scim/tasks.py`
- `authentik/providers/scim/clients/users.py`

No database migrations, API changes, or shared Google Workspace/Entra task
changes are included.

## Verification

On September 18, 2026, the full SCIM provider suite passed at the revision above:
**78 passed, 1 warning in 128.24 seconds**. Both previously failing regression
tests passed. The job and workflow completed successfully.

- [GitHub Actions run](https://github.com/upramod/authentik/actions/runs/35309894838)
- [Job log](https://github.com/upramod/authentik/actions/runs/35309894838/job/105489568285)
- [Executed fix commit](https://github.com/upramod/authentik/commit/9dc70fa1c97d1481e7c8da767babf5d9d286d643)

The warning concerns pytest assertion rewriting for an already imported `anyio`
module. It was also present in the baseline run.

Ruff, Black, whitespace checks, and the configured Bandit checks passed locally.
Ruff and Black also passed in the successful CI job.

The full SCIM provider suite runs through the upstream test environment:

```sh
CI_TEST_SEED=25291 make test authentik/providers/scim
```

The regression coverage includes:

- Removal through the group and user relationship managers.
- Retention through a direct user binding or another group binding.
- Group filtering, absent group mappings, and remote group 404 responses.
- Delayed removal after a user rejoins.
- Preservation of unrelated out-of-scope accounts.
- Failed deletion, retained mapping, retry signaling, and a successful retry.
- Remote account 404 and dry-run behavior.
- Full-sync deletion retries and dry-run mapping preservation.

The [baseline reproduction](SCIM_POLICY_GROUP_REMOVAL.md) records the original
two failures and 23 passing controls at the pre-fix revision.

## Limits

The tests use real models, signals, clients, and the native synchronous test
broker with mocked HTTP. They do not validate a live external SCIM service or
asynchronous worker scheduling. The test broker disables automatic retries;
the retry test checks the retry signal and explicitly delivers the next attempt.

This fix covers membership `post_remove` events. It does not add handlers for
`clear()`, policy edits, group hierarchy changes, or access loss caused by adding
a group under a negated policy. Other synchronization paths remain relevant.

Transient remote group-update failures delay account cleanup until a retry. A
delayed removal event can still alter remote group membership after a re-add;
the new scope check prevents account deletion, not that existing ordering issue.
The access check and remote HTTP request are not one atomic transaction.

The implementation is on the contributor's fork. No upstream acceptance,
release inclusion, external adoption, or production impact is established.

Keep the fork-only workflow and reproduction notes out of an upstream code patch.
