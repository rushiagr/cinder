# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Handles all requests relating to shares.
"""

import functools

from cinder.db import base
from cinder import exception
from cinder import flags
from cinder.image import glance
from cinder.openstack.common import log as logging
from cinder.openstack.common import rpc
from cinder.openstack.common import timeutils
import cinder.policy
from cinder import quota
from cinder.scheduler import rpcapi as scheduler_rpcapi
from cinder.share import rpcapi as share_rpcapi

from oslo.config import cfg


FLAGS = flags.FLAGS

LOG = logging.getLogger(__name__)
GB = 1048576 * 1024


def wrap_check_policy(func):
    """Check policy corresponding to the wrapped methods prior to execution.

    This decorator requires the first 3 args of the wrapped function
    to be (self, context, share).
    """
    @functools.wraps(func)
    def wrapped(self, context, target_obj, *args, **kwargs):
        check_policy(context, func.__name__, target_obj)
        return func(self, context, target_obj, *args, **kwargs)

    return wrapped


def check_policy(context, action, target_obj=None):
    target = {
        'project_id': context.project_id,
        'user_id': context.user_id,
    }
    target.update(target_obj or {})
    _action = 'share:%s' % action
    cinder.policy.enforce(context, _action, target)


class API(base.Base):
    """API for interacting with the share manager."""

    def __init__(self, db_driver=None):
        self.scheduler_rpcapi = scheduler_rpcapi.SchedulerAPI()
        self.share_rpcapi = share_rpcapi.ShareAPI()
        super(API, self).__init__(db_driver)

    def create(self, context, share_proto, size, name, description,
               snapshot=None, availability_zone=None):
        """Create new share."""

        if snapshot is not None:
            if snapshot['status'] != 'available':
                msg = _('status must be available')
                raise exception.InvalidShareSnapshot(reason=msg)
            if not size:
                size = snapshot['share_size']

            snapshot_id = snapshot['id']
        else:
            snapshot_id = None

        def as_int(s):
            try:
                return int(s)
            except (ValueError, TypeError):
                return s

        # tolerate size as stringified int
        size = as_int(size)

        if not isinstance(size, int) or size <= 0:
            msg = (_("Share size '%s' must be an integer and greater than 0")
                   % size)
            raise exception.InvalidInput(reason=msg)

        #TODO(rushiagr): Find a suitable place to keep all the allowed
        #                share types so that it becomes easier to add one
        if share_proto.lower() not in ['nfs', 'cifs']:
            msg = (_("Invalid share type provided: %s") % share_proto)
            raise exception.InvalidInput(reason=msg)

        if availability_zone is None:
            availability_zone = FLAGS.storage_availability_zone

        options = {'size': size,
                   'user_id': context.user_id,
                   'project_id': context.project_id,
                   'snapshot_id': snapshot_id,
                   'availability_zone': availability_zone,
                   'status': "creating",
                   'scheduled_at': timeutils.utcnow(),
                   'display_name': name,
                   'display_description': description,
                   'share_proto': share_proto,
                   }

        share = self.db.share_create(context, options)

        request_spec = {'share_properties': options,
                        'share_proto': share_proto,
                        'share_id': share['id'],
                        'snapshot_id': share['snapshot_id'],
                        }

        filter_properties = {}

        self.scheduler_rpcapi.create_share(
            context,
            FLAGS.share_topic,
            share['id'],
            snapshot_id,
            request_spec=request_spec,
            filter_properties=filter_properties)

        return share

    def delete(self, context, share):
        """Delete share."""
        share_id = share['id']
        if not share['host']:
            # NOTE(rushiagr): scheduling failed, delete
            self.db.share_delete(context, share_id)
            return

        if share['status'] not in ["available", "error"]:
            msg = _("Share status must be available or error")
            raise exception.InvalidShare(reason=msg)

        snapshots = self.db.share_snapshot_get_all_for_share(context, share_id)
        if len(snapshots):
            msg = _("Share still has %d dependent snapshots") % len(snapshots)
            raise exception.InvalidVolume(reason=msg)

        now = timeutils.utcnow()
        share = self.db.share_update(context, share_id, {'status': 'deleting',
                                                         'terminated_at': now})

        self.share_rpcapi.delete_share(context, share)

    def create_snapshot(self, context, share, name, description,
                        force=False):
        check_policy(context, 'create_snapshot', share)

        if ((not force) and (share['status'] != "available")):
            msg = _("must be available")
            raise exception.InvalidShare(reason=msg)

        options = {'share_id': share['id'],
                   'user_id': context.user_id,
                   'project_id': context.project_id,
                   'status': "creating",
                   'progress': '0%',
                   'share_size': share['size'],
                   'display_name': name,
                   'display_description': description,
                   'share_proto': share['share_proto'],
                   'export_location': share['export_location']}

        snapshot = self.db.share_snapshot_create(context, options)
        self.share_rpcapi.create_snapshot(context, share, snapshot)
        return snapshot

    @wrap_check_policy
    def delete_snapshot(self, context, snapshot, force=False):
        if not force and snapshot['status'] not in ["available", "error"]:
            msg = _("Share Snapshot status must be available or error")
            raise exception.InvalidShareSnapshot(reason=msg)

        self.db.share_snapshot_update(context, snapshot['id'],
                                      {'status': 'deleting'})
        share = self.db.share_get(context, snapshot['share_id'])
        self.share_rpcapi.delete_snapshot(context, snapshot, share['host'])

    @wrap_check_policy
    def update(self, context, share, fields):
        self.db.share_update(context, share['id'], fields)

    def get(self, context, share_id):
        rv = self.db.share_get(context, share_id)
        check_policy(context, 'get', rv)
        return rv

    def get_all(self, context, search_opts={}):
        check_policy(context, 'get_all')

        search_opts = search_opts or {}

        if (context.is_admin and 'all_tenants' in search_opts):
            # Need to remove all_tenants to pass the filtering below.
            del search_opts['all_tenants']
            shares = self.db.share_get_all(context)
        else:
            shares = self.db.share_get_all_by_project(context,
                                                      context.project_id)

        if search_opts:
            LOG.debug(_("Searching by: %s") % str(search_opts))

            results = []
            not_found = object()
            for share in shares:
                for opt, value in search_opts.iteritems():
                    if share.get(opt, not_found) != value:
                        break
                else:
                    results.append(share)
            shares = results
        return shares

    def get_snapshot(self, context, snapshot_id):
        check_policy(context, 'get_snapshot')
        rv = self.db.share_snapshot_get(context, snapshot_id)
        return dict(rv.iteritems())

    def get_all_snapshots(self, context, search_opts=None):
        check_policy(context, 'get_all_snapshots')

        search_opts = search_opts or {}

        if (context.is_admin and 'all_tenants' in search_opts):
            # Need to remove all_tenants to pass the filtering below.
            del search_opts['all_tenants']
            snapshots = self.db.share_snapshot_get_all(context)
        else:
            snapshots = self.db.share_snapshot_get_all_by_project(
                context, context.project_id)

        if search_opts:
            LOG.debug(_("Searching by: %s") % str(search_opts))

            results = []
            not_found = object()
            for snapshot in snapshots:
                for opt, value in search_opts.iteritems():
                    if snapshot.get(opt, not_found) != value:
                        break
                else:
                    results.append(snapshot)
            snapshots = results
        return snapshots

    def allow_access(self, ctx, share, access_type, access_to):
        """Allow access to share."""
        if not share['host']:
            msg = _("Share host is None")
            raise exception.InvalidShare(reason=msg)
        if share['status'] not in ["available"]:
            msg = _("Share status must be available")
            raise exception.InvalidShare(reason=msg)
        check_policy(ctx, 'allow_access')
        values = {'share_id': share['id'],
                  'access_type': access_type,
                  'access_to': access_to}
        access = self.db.share_access_create(ctx, values)
        self.share_rpcapi.allow_access(ctx, share, access)
        return access

    def deny_access(self, ctx, share, access):
        """Deny access to share."""
        check_policy(ctx, 'deny_access')
        #First check state of the target share
        if not share['host']:
            msg = _("Share host is None")
            raise exception.InvalidShare(reason=msg)
        if share['status'] not in ["available"]:
            msg = _("Share status must be available")
            raise exception.InvalidShare(reason=msg)

        #Then check state of the access rule
        if access['state'] == access.STATE_ERROR:
            self.db.share_access_delete(ctx, access["id"])
        elif access['state'] == access.STATE_ACTIVE:
            self.db.share_access_update(ctx, access["id"],
                                        {'state': access.STATE_DELETING})
            self.share_rpcapi.deny_access(ctx, share, access)
        else:
            msg = _("Access policy should be active or in error state")
            raise exception.InvalidShareAccess(reason=msg)
            #update share state and send message to manager

    def access_get_all(self, context, share):
        """Returns all access rules for share."""
        check_policy(context, 'access_get_all')
        rules = self.db.share_access_get_all_for_share(context, share['id'])
        return [{'id': rule.id,
                 'access_type': rule.access_type,
                 'access_to': rule.access_to,
                 'state': rule.state} for rule in rules]

    def access_get(self, context, access_id):
        """Returns access rule with the id."""
        check_policy(context, 'access_get')
        rule = self.db.share_access_get(context, access_id)
        return rule
