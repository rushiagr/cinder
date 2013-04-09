# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012, Red Hat, Inc.
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
Unit Tests for cinder.scheduler.rpcapi
"""

from cinder import context
from cinder import flags
from cinder.openstack.common import rpc
from cinder.scheduler import rpcapi as scheduler_rpcapi
from cinder import test


FLAGS = flags.FLAGS


class SchedulerRpcAPITestCase(test.TestCase):

    def setUp(self):
        super(SchedulerRpcAPITestCase, self).setUp()

    def tearDown(self):
        super(SchedulerRpcAPITestCase, self).tearDown()

    def _test_scheduler_api(self, method, rpc_method, **kwargs):
        ctxt = context.RequestContext('fake_user', 'fake_project')
        rpcapi = scheduler_rpcapi.SchedulerAPI()
        expected_retval = 'foo' if method == 'call' else None
        expected_version = kwargs.pop('version', rpcapi.RPC_API_VERSION)
        expected_msg = rpcapi.make_msg(method, **kwargs)
        expected_msg['version'] = expected_version

        self.fake_args = None
        self.fake_kwargs = None

        def _fake_rpc_method(*args, **kwargs):
            self.fake_args = args
            self.fake_kwargs = kwargs
            if expected_retval:
                return expected_retval

        self.stubs.Set(rpc, rpc_method, _fake_rpc_method)

        retval = getattr(rpcapi, method)(ctxt, **kwargs)

        self.assertEqual(retval, expected_retval)
        expected_args = [ctxt, FLAGS.scheduler_topic, expected_msg]
        for arg, expected_arg in zip(self.fake_args, expected_args):
            self.assertEqual(arg, expected_arg)

    def test_update_service_capabilities(self):
        self._test_scheduler_api('update_service_capabilities',
                                 rpc_method='fanout_cast',
                                 service_name='fake_name',
                                 host='fake_host',
                                 capabilities='fake_capabilities')

    def test_create_volume(self):
        self._test_scheduler_api('create_volume',
                                 rpc_method='cast',
                                 topic='topic',
                                 volume_id='volume_id',
                                 snapshot_id='snapshot_id',
                                 image_id='image_id',
                                 request_spec='fake_request_spec',
                                 filter_properties='filter_properties',
                                 version='1.2')

    def test_create_share(self):
        self._test_scheduler_api('create_share',
                                 rpc_method='cast',
                                 topic='topic',
                                 share_id='share_id',
                                 snapshot_id='snapshot_id',
                                 request_spec='fake_request_spec',
                                 filter_properties='filter_properties',
                                 version='1.3')
