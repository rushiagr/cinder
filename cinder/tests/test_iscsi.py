# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 Red Hat, Inc.
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

import os.path
import shutil
import string
import tempfile

from cinder.brick.iscsi import iscsi
from cinder import test
from cinder.volume import utils as volume_utils


class TargetAdminTestCase(object):

    def setUp(self):
        self.cmds = []

        self.tid = 1
        self.target_name = 'iqn.2011-09.org.foo.bar:blaa'
        self.lun = 10
        self.path = '/foo'
        self.vol_id = 'blaa'

        self.script_template = None
        self.stubs.Set(os.path, 'isfile', lambda _: True)
        self.stubs.Set(os, 'unlink', lambda _: '')
        self.stubs.Set(iscsi.TgtAdm, '_get_target', self.fake_get_target)
        self.stubs.Set(iscsi.LioAdm, '_get_target', self.fake_get_target)
        self.stubs.Set(iscsi.LioAdm, '__init__', self.fake_init)

    def fake_init(obj):
        return

    def fake_get_target(obj, iqn):
        return 1

    def get_script_params(self):
        return {'tid': self.tid,
                'target_name': self.target_name,
                'lun': self.lun,
                'path': self.path}

    def get_script(self):
        return self.script_template % self.get_script_params()

    def fake_execute(self, *cmd, **kwargs):
        self.cmds.append(string.join(cmd))
        return "", None

    def clear_cmds(self):
        self.cmds = []

    def verify_cmds(self, cmds):
        self.assertEqual(len(cmds), len(self.cmds))
        for a, b in zip(cmds, self.cmds):
            self.assertEqual(a, b)

    def verify(self):
        script = self.get_script()
        cmds = []
        for line in script.split('\n'):
            if not line.strip():
                continue
            cmds.append(line)
        self.verify_cmds(cmds)

    def run_commands(self):
        tgtadm = iscsi.get_target_admin()
        tgtadm.set_execute(self.fake_execute)
        tgtadm.create_iscsi_target(self.target_name, self.tid,
                                   self.lun, self.path)
        tgtadm.show_target(self.tid, iqn=self.target_name)
        tgtadm.remove_iscsi_target(self.tid, self.lun, self.vol_id)

    def test_target_admin(self):
        self.clear_cmds()
        self.run_commands()
        self.verify()


class TgtAdmTestCase(test.TestCase, TargetAdminTestCase):

    def setUp(self):
        super(TgtAdmTestCase, self).setUp()
        TargetAdminTestCase.setUp(self)
        self.persist_tempdir = tempfile.mkdtemp()
        self.flags(iscsi_helper='tgtadm')
        self.flags(volumes_dir=self.persist_tempdir)
        self.script_template = "\n".join([
            'tgt-admin --update iqn.2011-09.org.foo.bar:blaa',
            'tgt-admin --force '
            '--delete iqn.2010-10.org.openstack:volume-blaa'])

    def tearDown(self):
        try:
            shutil.rmtree(self.persist_tempdir)
        except OSError:
            pass
        super(TgtAdmTestCase, self).tearDown()


class IetAdmTestCase(test.TestCase, TargetAdminTestCase):

    def setUp(self):
        super(IetAdmTestCase, self).setUp()
        TargetAdminTestCase.setUp(self)
        self.flags(iscsi_helper='ietadm')
        self.script_template = "\n".join([
            'ietadm --op new --tid=%(tid)s --params Name=%(target_name)s',
            'ietadm --op new --tid=%(tid)s --lun=%(lun)s '
            '--params Path=%(path)s,Type=fileio',
            'ietadm --op show --tid=%(tid)s',
            'ietadm --op delete --tid=%(tid)s --lun=%(lun)s',
            'ietadm --op delete --tid=%(tid)s'])


class IetAdmBlockIOTestCase(test.TestCase, TargetAdminTestCase):

    def setUp(self):
        super(IetAdmBlockIOTestCase, self).setUp()
        TargetAdminTestCase.setUp(self)
        self.flags(iscsi_helper='ietadm')
        self.flags(iscsi_iotype='blockio')
        self.script_template = "\n".join([
            'ietadm --op new --tid=%(tid)s --params Name=%(target_name)s',
            'ietadm --op new --tid=%(tid)s --lun=%(lun)s '
            '--params Path=%(path)s,Type=blockio',
            'ietadm --op show --tid=%(tid)s',
            'ietadm --op delete --tid=%(tid)s --lun=%(lun)s',
            'ietadm --op delete --tid=%(tid)s'])


class IetAdmFileIOTestCase(test.TestCase, TargetAdminTestCase):

    def setUp(self):
        super(IetAdmFileIOTestCase, self).setUp()
        TargetAdminTestCase.setUp(self)
        self.flags(iscsi_helper='ietadm')
        self.flags(iscsi_iotype='fileio')
        self.script_template = "\n".join([
            'ietadm --op new --tid=%(tid)s --params Name=%(target_name)s',
            'ietadm --op new --tid=%(tid)s --lun=%(lun)s '
            '--params Path=%(path)s,Type=fileio',
            'ietadm --op show --tid=%(tid)s',
            'ietadm --op delete --tid=%(tid)s --lun=%(lun)s',
            'ietadm --op delete --tid=%(tid)s'])


class IetAdmAutoIOTestCase(test.TestCase, TargetAdminTestCase):

    def setUp(self):
        super(IetAdmAutoIOTestCase, self).setUp()
        TargetAdminTestCase.setUp(self)
        self.stubs.Set(volume_utils, 'is_block', lambda _: True)
        self.flags(iscsi_helper='ietadm')
        self.flags(iscsi_iotype='auto')
        self.script_template = "\n".join([
            'ietadm --op new --tid=%(tid)s --params Name=%(target_name)s',
            'ietadm --op new --tid=%(tid)s --lun=%(lun)s '
            '--params Path=%(path)s,Type=blockio',
            'ietadm --op show --tid=%(tid)s',
            'ietadm --op delete --tid=%(tid)s --lun=%(lun)s',
            'ietadm --op delete --tid=%(tid)s'])


class LioAdmTestCase(test.TestCase, TargetAdminTestCase):

    def setUp(self):
        super(LioAdmTestCase, self).setUp()
        TargetAdminTestCase.setUp(self)
        self.persist_tempdir = tempfile.mkdtemp()
        self.flags(iscsi_helper='lioadm')
        self.script_template = "\n".join([
            'rtstool create '
                '/foo iqn.2011-09.org.foo.bar:blaa test_id test_pass',
            'rtstool delete iqn.2010-10.org.openstack:volume-blaa'])
