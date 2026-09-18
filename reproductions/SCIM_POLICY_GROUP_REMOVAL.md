# SCIM account cleanup after application group removal

## Verified result

On September 18, 2026, the native test runner reported **2 failed, 23 passed,
1 warning in 103.36 seconds**. Both failures reached the account deletion
assertion: zero HTTP DELETE requests were observed where one was expected.

- Upstream baseline: `fd5aee1fd127f64f3ecb849f2aec1b515085c0e6`
- Test and workflow revision: `66a7ddd3d82be5c6b70d23d94a7fdf9493cfa86b`
- [GitHub Actions run](https://github.com/upramod/authentik/actions/runs/35309056242)
- [Job log](https://github.com/upramod/authentik/actions/runs/35309056242/job/105487111199)
- [Test source at the executed revision](https://github.com/upramod/authentik/blob/66a7ddd3d82be5c6b70d23d94a7fdf9493cfa86b/authentik/providers/scim/tests/test_membership.py)

This revision changes tests and adds a fork-only CI workflow. It does not change
production behavior.

## Scenario and expected behavior

1. Create a synthetic user and group.
2. Bind the group to the SCIM provider's application.
3. Provision the user and group through a full sync. Verify the user mapping and
   simulated remote group membership exist.
4. Remove the membership through the group manager or the user manager.
5. Allow the real membership signals and the native synchronous test broker to
   process the event. Do not request a full sync.
6. Verify that application access no longer includes the user and that the local
   user still exists.
7. Expect one DELETE request for the managed remote account and removal of its
   SCIM mapping.

Actual: both removal paths reach step 7 without a DELETE request. The assertions
also verify that no SCIM actor error was recorded before this failure.

## Test outcomes

All four new tests belong to `SCIMMembershipTests` in
`authentik/providers/scim/tests/test_membership.py`.

| Test | Result | Observation |
| --- | --- | --- |
| `test_policy_group_removal_deprovisions_user` | FAIL | Removal via `group.users.remove(user)` produces zero account DELETE requests. |
| `test_policy_group_removal_from_user_deprovisions_user` | FAIL | Removal via `user.groups.remove(group)` produces zero account DELETE requests. |
| `test_policy_group_removal_manual_sync_cleanup` | PASS | A full sync deletes the same kind of out-of-scope account and removes its mapping. |
| `test_policy_group_removal_preserves_directly_bound_user` | PASS | A remaining direct binding preserves the account; simulated remote group membership is removed. |

The other 21 membership and application-policy tests pass.

Failure message:

```text
AssertionError: 0 != 1 : Leaving application scope must deprovision the managed
SCIM account without a manual or scheduled full sync.
```

## Reproduction

Check out the executed revision and use the upstream development or CI setup
with Python 3.14 and PostgreSQL. The recorded run used Python 3.14.7,
PostgreSQL 16, Ubuntu 24.04, and the unchanged dependency lockfile.

```sh
git checkout 66a7ddd3d82be5c6b70d23d94a7fdf9493cfa86b
CI_TEST_SEED=25291 make test \
  authentik/providers/scim/tests/test_membership.py \
  authentik/providers/scim/tests/test_application_policies.py
```

The workflow at `.github/workflows/repro-scim-policy-group-removal.yml` contains
the complete runner setup, including the public upstream test database settings.
Keep this fork-only workflow and reproduction note out of an upstream code patch.

The earlier run, `35309030272`, failed before test execution because the workflow
omitted the test database password. It is an environment failure and supplies no
evidence about SCIM behavior. The result above comes from the corrected run.

## Scope of this evidence

The tests exercise real database models, application access queries, membership
signals, SCIM clients, and tasks under the repository's native eager test broker.
Only HTTP transport is mocked; the simulated remote group membership is stored
independently from the local database.

This proves a missing account-deletion request in the tested event path. It is
not a live third-party SCIM integration test, an asynchronous worker timing test,
or a measurement of downstream deployment impact. No production fix or upstream
review has been completed as part of this reproduction.
