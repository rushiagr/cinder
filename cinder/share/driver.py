# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 NetApp
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
Drivers for shares.

"""

import ConfigParser
import os
import re
import time

from cinder import exception
from cinder import flags
from cinder.openstack.common import cfg
from cinder.openstack.common import log as logging
from cinder import utils


LOG = logging.getLogger(__name__)

driver_opts = [
    #NOTE(rushiagr): Reasonable to define this option at only one place.
    cfg.IntOpt('num_shell_tries',
               default=3,
               help='number of times to attempt to run flakey shell commands'),
    cfg.IntOpt('reserved_percentage',
               default=0,
               help='The percentage of backend capacity is reserved'),
]

FLAGS = flags.FLAGS
FLAGS.register_opts(driver_opts)


#NOTE(rushiagr): The right place for this class is cinder.driver or
#               cinder.utils.
class ExecuteMixin(object):
    """Provides an executable functionality to a driver class."""

    def __init__(self, *args, **kwargs):
        self.set_execute(kwargs.pop('execute', utils.execute))
        super(ExecuteMixin, self).__init__(*args, **kwargs)

    def set_execute(self, execute):
        self._execute = execute

    def _try_execute(self, *command, **kwargs):
        # NOTE(vish): Volume commands can partially fail due to timing, but
        #             running them a second time on failure will usually
        #             recover nicely.
        tries = 0
        while True:
            try:
                self._execute(*command, **kwargs)
                return True
            except exception.ProcessExecutionError:
                tries = tries + 1
                if tries >= FLAGS.num_shell_tries:
                    raise
                LOG.exception(_("Recovering from a failed execute.  "
                                "Try number %s"), tries)
                time.sleep(tries ** 2)


class ShareDriver(object):
    """Class defines interface of NAS driver."""

    def allocate_container(self, context, share):
        """Is called to allocate container for share."""
        raise NotImplementedError()

    def allocate_container_from_snapshot(self, context, share, snapshot):
        """Is called to create share from snapshot."""
        raise NotImplementedError()

    def deallocate_container(self, context, share):
        """Is called to deallocate container of share."""
        raise NotImplementedError()

    def create_share(self, context, share):
        """Is called to create share."""
        raise NotImplementedError()

    def create_snapshot(self, context, snapshot):
        """Is called to create snapshot."""
        raise NotImplementedError()

    def delete_share(self, context, share):
        """Is called to remove share."""
        raise NotImplementedError()

    def delete_snapshot(self, context, snapshot):
        """Is called to remove snapshot."""
        raise NotImplementedError()

    def create_export(self, context, share):
        """Is called to export share."""
        raise NotImplementedError()

    def remove_export(self, context, share):
        """Is called to stop exporting share."""
        raise NotImplementedError()

    def ensure_share(self, context, share):
        """Invoked to sure that share is exported."""
        raise NotImplementedError()

    def allow_access(self, context, share, access):
        """Allow access to the share."""
        raise NotImplementedError()

    def deny_access(self, context, share, access):
        """Deny access to the share."""
        raise NotImplementedError()

    def check_for_setup_error(self):
        """Check for setup error."""
        pass

    def get_share_stats(self, refresh=False):
        """Return the current state of the share service.

           :param refresh: If is True run the update first.
           :returns: State of share service.
        """
        return None

    def do_setup(self, context):
        """Any initialization the share driver does while starting."""
        pass
