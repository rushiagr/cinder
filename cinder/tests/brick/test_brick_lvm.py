# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2012 OpenStack LLC.
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

import mox


from cinder.brick.local_dev import lvm as brick
from cinder.openstack.common import log as logging
from cinder.openstack.common import processutils
from cinder import test
from cinder.volume import configuration as conf

LOG = logging.getLogger(__name__)


def create_configuration():
    configuration = mox.MockObject(conf.Configuration)
    configuration.append_config_values(mox.IgnoreArg())
    return configuration


class BrickLvmTestCase(test.TestCase):
    def setUp(self):
        self._mox = mox.Mox()
        self.configuration = mox.MockObject(conf.Configuration)
        self.configuration.volume_group_name = 'fake-volumes'
        super(BrickLvmTestCase, self).setUp()
        self.stubs.Set(processutils, 'execute',
                       self.fake_execute)
        self.vg = brick.LVM(self.configuration.volume_group_name)

    def failed_fake_execute(obj, *cmd, **kwargs):
        return ("\n", "fake-error")

    def fake_execute(obj, *cmd, **kwargs):
        cmd_string = ', '.join(cmd)
        data = "\n"

        if 'vgs, --noheadings, -o, name' == cmd_string:
            data = "  fake-volumes\n"
        elif 'vgs, --noheadings, -o uuid, fake-volumes' in cmd_string:
            data = "  kVxztV-dKpG-Rz7E-xtKY-jeju-QsYU-SLG6Z1\n"
        elif 'vgs, --noheadings, -o, name,size,free,lv_count,uuid' in\
                cmd_string:
            data = "  fake-volumes:10.00g:10.00g:0:"\
                   "kVxztV-dKpG-Rz7E-xtKY-jeju-QsYU-SLG6Z1\n"
            if 'fake-volumes' in cmd_string:
                return (data, "")
            data += "  fake-volumes-2:10.00g:10.00g:0:"\
                    "lWyauW-dKpG-Rz7E-xtKY-jeju-QsYU-SLG7Z2\n"
            data += "  fake-volumes-3:10.00g:10.00g:0:"\
                    "mXzbuX-dKpG-Rz7E-xtKY-jeju-QsYU-SLG8Z3\n"
        elif 'lvs, --noheadings, -o, vg_name,name,size' in cmd_string:
            data = "  fake-volumes fake-1 1.00g\n"
            data += "  fake-volumes fake-2 1.00g\n"
        elif 'lvs, --noheadings, -o, vg_name,name,size' in cmd_string:
            data = "  fake-volumes fake-1 1.00g\n"
            data += "  fake-volumes fake-2 1.00g\n"
        elif 'pvs, --noheadings' and 'fake-volumes' in cmd_string:
            data = "  fake-volumes:/dev/sda:10.00g:8.99g\n"
        elif 'pvs, --noheadings' in cmd_string:
            data = "  fake-volumes:/dev/sda:10.00g:8.99g\n"
            data += "  fake-volumes-2:/dev/sdb:10.00g:8.99g\n"
            data += "  fake-volumes-3:/dev/sdc:10.00g:8.99g\n"
        else:
            pass

        return (data, "")

    def test_vg_exists(self):
        self.stubs.Set(processutils, 'execute', self.fake_execute)
        self.assertEqual(self.vg._vg_exists(), True)

        self.stubs.Set(processutils, 'execute', self.failed_fake_execute)
        self.assertEqual(self.vg._vg_exists(), False)

    def test_get_vg_uuid(self):
        self.stubs.Set(processutils, 'execute', self.fake_execute)
        self.assertEqual(self.vg._get_vg_uuid()[0],
                         'kVxztV-dKpG-Rz7E-xtKY-jeju-QsYU-SLG6Z1')

    def test_get_all_volumes(self):
        self.stubs.Set(processutils, 'execute', self.fake_execute)
        out = self.vg.get_volumes()

        self.assertEqual(out[0]['name'], 'fake-1')
        self.assertEqual(out[0]['size'], '1.00g')
        self.assertEqual(out[0]['vg'], 'fake-volumes')

    def test_get_volume(self):
        self.stubs.Set(processutils, 'execute', self.fake_execute)
        self.assertEqual(self.vg.get_volume('fake-1')['name'], 'fake-1')

    def test_get_all_physical_volumes(self):
        self.stubs.Set(processutils, 'execute', self.fake_execute)
        pvs = self.vg.get_all_physical_volumes()
        self.assertEqual(len(pvs), 3)

    def test_get_physical_volumes(self):
        self.stubs.Set(processutils, 'execute', self.fake_execute)
        pvs = self.vg.get_physical_volumes()
        self.assertEqual(len(pvs), 1)

    def test_get_volume_groups(self):
        self.stubs.Set(processutils, 'execute', self.fake_execute)
        self.assertEqual(len(self.vg.get_all_volume_groups()), 3)
        self.assertEqual(len(self.vg.get_all_volume_groups('fake-volumes')), 1)

    def test_update_vg_info(self):
        self.stubs.Set(processutils, 'execute', self.fake_execute)
        self.assertEqual(self.vg.update_volume_group_info()['name'],
                         'fake-volumes')
