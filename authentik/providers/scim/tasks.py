"""SCIM Provider tasks"""

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from dramatiq.actor import actor
from dramatiq.errors import Retry
from structlog.stdlib import get_logger

from authentik.core.models import User
from authentik.lib.sync.outgoing.exceptions import (
    DryRunRejected,
    NotFoundSyncException,
    StopSync,
    TransientSyncException,
)
from authentik.lib.sync.outgoing.tasks import SyncTasks
from authentik.providers.scim.models import SCIMProvider, SCIMProviderUser
from authentik.tasks.middleware import CurrentTask

sync_tasks = SyncTasks(SCIMProvider)


@actor(description=_("Sync SCIM provider objects."))
def scim_sync_objects(*args, **kwargs):
    return sync_tasks.sync_objects(*args, **kwargs)


@actor(description=_("Full sync for SCIM provider."))
def scim_sync(provider_pk: int, *args, **kwargs):
    """Run full sync for SCIM provider"""
    return sync_tasks.sync(provider_pk, scim_sync_objects)


@actor(description=_("Sync a direct object (user, group) for SCIM provider."))
def scim_sync_direct(*args, **kwargs):
    return sync_tasks.sync_signal_direct(*args, **kwargs)


@actor(description=_("Dispatch syncs for a direct object (user, group) for SCIM providers."))
def scim_sync_direct_dispatch(*args, **kwargs):
    return sync_tasks.sync_signal_direct_dispatch(scim_sync_direct, *args, **kwargs)


@actor(description=_("Delete an object (user, group) for SCIM provider."))
def scim_sync_delete(*args, **kwargs):
    return sync_tasks.sync_signal_delete(*args, **kwargs)


@actor(description=_("Dispatch deletions for an object (user, group) for SCIM providers."))
def scim_sync_delete_dispatch(*args, **kwargs):
    return sync_tasks.sync_signal_delete_dispatch(scim_sync_delete, *args, **kwargs)


@actor(description=_("Sync a related object (memberships) for SCIM provider."))
def scim_sync_m2m(group_pk: str, provider_pk: int, action: str, pk_set: list[int]):
    # Update group membership while the removed users' remote IDs are still available.
    try:
        sync_tasks.sync_signal_m2m(group_pk, provider_pk, action, pk_set)
    except NotFoundSyncException:
        if action != "post_remove":
            raise
        # A group that is already absent cannot retain a membership, but its users
        # may still need account cleanup after losing application access.
        get_logger().info(
            "Group not found in remote provider", group_pk=group_pk, provider_pk=provider_pk
        )
    if action != "post_remove" or not pk_set:
        return

    provider = SCIMProvider.objects.filter(
        Q(backchannel_application__isnull=False) | Q(application__isnull=False),
        pk=provider_pk,
    ).first()
    if not provider:
        return

    # Group filters only limit group synchronization. An excluded or unprovisioned
    # group can still grant application access, so cleanup must run independently.
    # Recheck current access to preserve other bindings and ignore stale removal events.
    in_scope = provider.get_object_qs(User, pk__in=pk_set).values("pk")
    stale = SCIMProviderUser.objects.filter(provider=provider, user_id__in=pk_set).exclude(
        user_id__in=in_scope
    )
    if not stale.exists():
        return

    logger = get_logger().bind(provider_pk=provider.pk)
    task = CurrentTask.get_task()
    try:
        client = provider.client_for_model(User)
        for connection in stale:
            try:
                client.delete(connection.scim_id)
                task.info("Deleted out-of-scope user", scim_id=connection.scim_id)
            except NotFoundSyncException as exc:
                logger.info(
                    "Object not found in remote provider", scim_id=connection.scim_id, exc=exc
                )
            except DryRunRejected as exc:
                logger.info("Rejected dry-run cleanup event", exc=exc)
    except TransientSyncException as exc:
        raise Retry() from exc
    except StopSync as exc:
        logger.warning("Stopping sync", exc=exc)


@actor(description=_("Dispatch syncs for a related object (memberships) for SCIM providers."))
def scim_sync_m2m_dispatch(*args, **kwargs):
    return sync_tasks.sync_signal_m2m_dispatch(scim_sync_m2m, *args, **kwargs)
