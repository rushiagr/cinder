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
NetApp specific NAS storage driver. Supports NFS and CIFS protocols.

This driver requires NetApp OnCommand 5.0 and one or more Data
ONTAP 7-mode storage systems with installed CIFS and NFS licenses.
"""
from lxml import etree
import suds
from suds.sax import text

from cinder import exception
from cinder import flags
from cinder.openstack.common import log
from cinder.share import driver

from cinder.volume.drivers.netapp.api import NaApiError, NaElement, NaServer


from oslo.config import cfg

'''config options
vserver name(openstack)
filer IP
filer uname
filer password

#TODOS(rushiagr)
    1. Make _remember_share() more generic, or remove altogether
    2. Change _client.send_request_to() to some other name
    3. Remove references of cmode_filer

'''

LOG = log.getLogger(__name__)

NETAPP_NAS_OPTS = [
    cfg.StrOpt('netapp_nas_transport_type',
               default='http',
               help='Transport type protocol'),
    cfg.StrOpt('netapp_nas_login',
               default='admin',
               help='User name for the clustered ONTAP controller'),
    cfg.StrOpt('netapp_nas_password',
               default='Netapp123',
               help='Password for the clustered ONTAP controller',
               secret=True),
    cfg.StrOpt('netapp_nas_server_hostname',
               default='10.63.165.71',
               help='Hostname for the clustered ONTAP controller'),
    cfg.StrOpt('netapp_nas_vserver',
               default='openstack',
               help='Cluster vserver to use for provisioning'),
    cfg.FloatOpt('netapp_nas_size_multiplier',
                 default=1.2,
                 help='Volume size multiplier to ensure while creation'),
]


FLAGS = flags.FLAGS
FLAGS.register_opts(NETAPP_NAS_OPTS)


class NetAppClusteredShareDriver(driver.ShareDriver):
    """
    NetApp specific NAS driver. Allows for NFS and CIFS NAS storage usage.
    """

    def __init__(self, db, *args, **kwargs):
        super(NetAppClusteredShareDriver, self).__init__(*args, **kwargs)
        self.db = db
        self._client = NetAppApiClient()
        self._helpers = None
        self._share_table = {}

    def allocate_container(self, context, share):
        """Allocate space for the share on aggregates."""
        aggregate = self._find_best_aggregate()
        self._allocate_share_space(aggregate, share)
        self._remember_share(share['id'], 'cmode_filer')

    def allocate_container_from_snapshot(self, context, share, snapshot):
        """Creates a share from a snapshot."""
        share_name = _get_valid_share_name(share['id'])
        parent_share_name = _get_valid_share_name(snapshot['share_id'])
        parent_snapshot_name = _get_valid_snapshot_name(snapshot['id'])

        xml_args = ('<volume>%s</volume>'
                    '<parent-volume>%s</parent-volume>'
                    '<parent-snapshot>%s</parent-snapshot>') % \
                   (share_name, parent_share_name, parent_snapshot_name)
        self._client.send_request_to('volume-clone-create', xml_args)
        self._remember_share(share['id'], 'cmode_filer')

    def deallocate_container(self, context, share):
        """Free share space."""
        self._share_offline(share)
        self._delete_share(share)

    def create_share(self, context, share):
        """Creates NAS storage."""
        helper = self._get_helper(share)
        export_location = helper.create_share(share)
        return export_location

    def create_snapshot(self, context, snapshot):
        """Creates a snapshot of a share."""
        share_name = _get_valid_share_name(snapshot['share_id'])
        snapshot_name = _get_valid_snapshot_name(snapshot['id'])

        filer = self._get_filer(snapshot['share_id'])

        xml_args = ('<volume>%s</volume>'
                    '<snapshot>%s</snapshot>') % (share_name, snapshot_name)
        self._client.send_request_to('snapshot-create', xml_args)

    def delete_share(self, context, share):
        """Deletes NAS storage."""
        helper = self._get_helper(share)
        target = helper.get_target(share)
        # share may be in error state, so there's no share and target
        if target:
            helper.delete_share(share)

    def delete_snapshot(self, context, snapshot):
        """Deletes a snapshot of a share."""
        share_name = _get_valid_share_name(snapshot['share_id'])
        snapshot_name = _get_valid_snapshot_name(snapshot['id'])

        filer = self._get_filer(snapshot['share_id'])

        self._is_snapshot_busy(filer, share_name, snapshot_name)
        xml_args = ('<snapshot>%s</snapshot>'
                    '<volume>%s</volume>') % (snapshot_name, share_name)
        self._client.send_request_to('snapshot-delete', xml_args)

    def create_export(self, context, share):
        """Share already exported."""
        pass

    def remove_export(self, context, share):
        """Share already removed."""
        pass

    def ensure_share(self, context, share):
        """Remember previously created shares."""
        helper = self._get_helper(share)
        filer = helper.get_target(share)
        self._remember_share(share['id'], filer)

    def allow_access(self, context, share, access):
        """Allows access to a given NAS storage for IPs in :access:"""
        helper = self._get_helper(share)
        return helper.allow_access(context, share, access)

    def deny_access(self, context, share, access):
        """Denies access to a given NAS storage for IPs in :access:"""
        helper = self._get_helper(share)
        return helper.deny_access(context, share, access)

    def do_setup(self, context):
        """Prepare once the driver.

        Called once by the manager after the driver is loaded.
        Validate the flags we care about and setup the suds (web
        services) client.
        """
        self._client.do_setup()
        self._setup_helpers()

    def check_for_setup_error(self):
        """Raises error if prerequisites are not met."""
        self._client.check_configuration()

    def _get_filer(self, share_id):
        """Returns filer name for the share_id."""
        try:
            return self._share_table[share_id]
        except KeyError:
            return

    def _remember_share(self, share_id, filer):
        """Stores required share info in local state."""
        self._share_table[share_id] = filer

    def _forget_share(self, share_id):
        """Remove share info about share."""
        try:
            self._share_table.pop(share_id)
        except KeyError:
            pass

    def _share_offline(self, share):
        """Sends share offline. Required before deleting a share."""
        share_name = _get_valid_share_name(share['id'])
        xml_args = ('<name>%s</name>') % share_name
        self._client.send_request_to('volume-offline', xml_args)

    def _delete_share(self, share):
        """Destroys share on a target OnTap device."""
        share_name = _get_valid_share_name(share['id'])
        xml_args = ('<name>%s</name>'
                   ) % share_name
        self._client.send_request_to('volume-destroy', xml_args)

    def _setup_helpers(self):
        """Initializes protocol-specific NAS drivers."""
        self._helpers = {'CIFS': NetAppCIFSHelper(self._client),
                         'NFS': NetAppNFSHelper(self._client)}

    def _get_helper(self, share):
        """Returns driver which implements share protocol."""
        share_proto = share['share_type']

        for proto in self._helpers.keys():
            if share_proto.upper().startswith(proto):
                return self._helpers[proto]

        err_msg = _("Invalid NAS protocol supplied: %s. ") % (share_proto)

        raise exception.Error(err_msg)

    def _find_best_aggregate(self):
        """Returns aggregate with the most free space left."""
        aggrs = self._client.get_available_aggregates()
        best_aggregate = max(aggrs, key=lambda m: aggrs[m])

        return best_aggregate

    def _allocate_share_space(self, aggregate, share):
        """Create new share on aggregate."""
        share_name = _get_valid_share_name(share['id'])
        args_xml = ('<containing-aggr-name>%s</containing-aggr-name>'
                    '<junction-path>/vol</junction-path>'
                    '<size>%dg</size>'
                    '<volume>%s</volume>') % (aggregate, share['size'],
                                              share_name)
        self._client.send_request_to('volume-create', args_xml)

    def _is_snapshot_busy(self, filer, share_name, snapshot_name):
        """Raises ShareSnapshotIsBusy if snapshot is busy."""
        xml_args = ('<volume>%s</volume>') % share_name
        snapshots = self._client.send_request_to('snapshot-list-info',
                                                 xml_args,
                                                 do_response_check=False)

        for snap in snapshots.Results.snapshots[0]['snapshot-info']:
            if snap['name'][0] == snapshot_name and snap['busy'][0] == 'true':
                raise exception.ShareSnapshotIsBusy(
                    snapshot_name=snapshot_name)


def _check_response(request, response):
    """Checks RPC responses from NetApp devices."""
    if response.Status == 'failed':
        name = request.Name
        reason = response.Reason
        msg = _('API %(name)s failed: %(reason)s')
        raise exception.Error(msg % locals())


def _get_valid_share_name(share_id):
    """The name can contain letters, numbers, and the underscore
    character (_). The first character must be a letter or an
    underscore."""
    return 'share_' + share_id.replace('-', '_')


def _get_valid_snapshot_name(snapshot_id):
    """The name can contain letters, numbers, and the underscore
    character (_). The first character must be a letter or an
    underscore."""
    return 'share_snapshot_' + snapshot_id.replace('-', '_')


class NetAppApiClient(object):
    """Wrapper for connection to NetApp controller."""

    REQUIRED_FLAGS = ['netapp_nas_login',
                      'netapp_nas_password',
                      'netapp_nas_server_hostname']

    def __init__(self):
        self._client = None

    def do_setup(self):
        protocol = 'https' if FLAGS.netapp_nas_transport_type == 'https' else 'http'

        self._client = NaServer(host=FLAGS.netapp_nas_server_hostname,
                                server_type=NaServer.SERVER_TYPE_FILER,
                                transport_type=FLAGS.netapp_nas_transport_type,
                                style=NaServer.STYLE_LOGIN_PASSWORD,
                                username=FLAGS.netapp_nas_login,
                                password=FLAGS.netapp_nas_password)
        self._client.set_api_version(1,15)
        self._client.set_vserver('rushi')
        #LOG.debug(_('Using NetApp filer:'), FLAGS.netapp_nas_server_hostname)

    def send_request_to(self, request, xml_args=None,
                        do_response_check=True):
        """
        Sends RPC :request: to :target:.
        :param target: IP address, ID or network name of OnTap device
        :param request: API name
        :param xml_args: call arguments
        :param do_response_check: if set to True and RPC call has failed,
        raises exception.
        """
        client = self._client

        # TODO(rushiagr): better way to repr xml string, with sanitation
        query_string = '<' + request + '>' + xml_args + '</' + request + '>'
        query_elem = NaElement(etree.fromstring(query_string))
        
        response = self._client.invoke_successfully(query_elem)

        return response

    def get_available_aggregates(self):
        """Returns aggregate list for the vfiler."""
        response = self._client.invoke_successfully(NaElement('vserver-get'))
        aggr_list_elements = response.get_child_by_name('attributes') \
                                .get_child_by_name('vserver-info') \
                                .get_child_by_name('vserver-aggr-info-list') \
                                .get_children()
        
        if not aggr_list_elements:
            msg = _("No aggregate assigned to vserver %s")
            raise exception.Error(msg % FLAGS.netapp_nas_vserver)
        
        # return dict of key-value pair of aggr_name:size
        aggr_dict = {}
        
        for aggr_elem in aggr_list_elements:
            aggr_name = aggr_elem.get_child_content('aggr-name')
            aggr_size = int(aggr_elem.get_child_content('aggr-availsize'))
            aggr_dict[aggr_name] = aggr_size
        
        LOG.debug("aggr_dict:", aggr_dict)
        return aggr_dict


    def get_host_ip_by(self, host_id):
        """Returns IP address of a host known by DFM."""
        if (type(host_id) is str or type(host_id) is unicode) and \
                len(host_id.split('.')) == 4:
            # already IP
            return host_id

        client = self._client
        srv = client.service

        filer_filter = client.factory.create('HostListInfoIterStart')
        filer_filter.ObjectNameOrId = host_id
        resp = srv.HostListInfoIterStart(HostListInfoIterStart=filer_filter)
        tag = resp.Tag

        try:
            filers = srv.HostListInfoIterNext(Tag=tag, Maximum=resp.Records)
        finally:
            srv.HostListInfoIterEnd(Tag=tag)

        ip = None
        for host in filers.Hosts.HostInfo:
            if int(host.HostId) == int(host_id):
                ip = host.HostAddress

        return ip

    @staticmethod
    def check_configuration():
        """Ensure that the flags we care about are set."""
        for flag in NetAppApiClient.REQUIRED_FLAGS:
            if not getattr(FLAGS, flag, None):
                raise exception.Error(_('%s is not set') % flag)


class NetAppNASHelperBase(object):
    """Interface for protocol-specific NAS drivers."""
    def __init__(self, suds_client):
        self._client = suds_client

    def create_share(self, target_id, share):
        """Creates NAS share"""
        raise NotImplementedError()

    def delete_share(self, share):
        """Deletes NAS share"""
        raise NotImplementedError()

    def allow_access(self, context, share, new_rules):
        """Allows new_rules to a given NAS storage for IPs in :new_rules"""
        raise NotImplementedError()

    def deny_access(self, context, share, new_rules):
        """Denies new_rules to a given NAS storage for IPs in :new_rules"""
        raise NotImplementedError()

    def get_target(self, share):
        """Returns host where the share located."""
        raise NotImplementedError()


class NetAppNFSHelper(NetAppNASHelperBase):
    """Netapp specific NFS sharing driver"""

    def __init__(self, suds_client):
        super(NetAppNFSHelper, self).__init__(suds_client)
#TODO(rushiagr): start from here. 
    def create_share(self, share):
        """Creates NFS share"""
        args_xml = ('<rules>'
                    '<exports-rule-info-2>'
                    '<pathname>%s</pathname>'
                    '<security-rules>'
                    '<security-rule-info>'
                    '<read-write>'
                    '<exports-hostname-info>'
                    '<name>localhost</name>'
                    '</exports-hostname-info>'
                    '</read-write>'
                    '<root>'
                    '<exports-hostname-info>'
                    '<all-hosts>false</all-hosts>'
                    '<name>localhost</name>'
                    '</exports-hostname-info>'
                    '</root>'
                    '</security-rule-info>'
                    '</security-rules>'
                    '</exports-rule-info-2>'
                    '</rules>')

        client = self._client
        valid_share_name = _get_valid_share_name(share['id'])
        export_pathname = '/vol/' + valid_share_name
        print 'export pathname:', export_pathname
        client.send_request_to('nfs-exportfs-append-rules-2',
                               args_xml % export_pathname)

        export_ip = FLAGS.netapp_nas_server_hostname
        export_location = ':'.join([export_ip, export_pathname])
        return export_location

    def delete_share(self, share):
        """Deletes NFS share."""
        target, export_path = self._get_export_path(share)

        xml_args = ('<pathnames>'
                    '<pathname-info>'
                    '<name>%s</name>'
                    '</pathname-info>'
                    '</pathnames>') % export_path

        self._client.send_request_to('nfs-exportfs-delete-rules',
                                     xml_args)

    def allow_access(self, context, share, access):
        """Allows access to a given NFS storage for IPs in :access:"""
        if access['access_type'] != 'ip':
            raise exception.Error(('Invalid access type supplied. '
                                   'Only \'ip\' type is supported'))

        ips = access['access_to']

        existing_rules = self._get_exisiting_rules(share)
        new_rules_xml = self._append_new_rules_to(existing_rules, ips)

        self._modify_rule(share, new_rules_xml)

    def deny_access(self, context, share, access):
        """Denies access to a given NFS storage for IPs in :access:"""
        denied_ips = access['access_to']
        existing_rules = self._get_exisiting_rules(share)

        if type(denied_ips) is not list:
            denied_ips = [denied_ips]

        for deny_rule in denied_ips:
            try:
                existing_rules.remove(deny_rule)
            except ValueError:
                pass

        new_rules_xml = self._append_new_rules_to([], existing_rules)
        self._modify_rule(share, new_rules_xml)

    def get_target(self, share):
        """Returns ID of target OnTap device based on export location."""
        return self._get_export_path(share)[0]

    def _modify_rule(self, share, rw_rules):
        """Modifies access rule for a share"""
        target, export_path = self._get_export_path(share)

        xml_args = ('<persistent>true</persistent>'
                    '<rules>'
                    '<exports-rule-info-2>'
                    '<pathname>%s</pathname>'
                    '<security-rules>%s'
                    '</security-rules>'
                    '</exports-rule-info-2>'
                    '</rules>') % (export_path, ''.join(rw_rules))

        self._client.send_request_to('nfs-exportfs-append-rules-2',
                                     xml_args)

    def _get_exisiting_rules(self, share):
        """Returns available access rules for the share."""
        target, export_path = self._get_export_path(share)
        xml_args = '<pathname>%s</pathname>' % export_path

        response = self._client.send_request_to('nfs-exportfs-list-rules-2',
                                                xml_args)

        rules = response.Results.rules[0]
        security_rule = rules['exports-rule-info-2'][0]['security-rules'][0]
        security_info = security_rule['security-rule-info'][0]
        root_rules = security_info['root'][0]
        allowed_hosts = root_rules['exports-hostname-info']

        existing_rules = []

        for allowed_host in allowed_hosts:
            if 'name' in allowed_host:
                existing_rules.append(allowed_host['name'][0])

        return existing_rules

    @staticmethod
    def _append_new_rules_to(existing_rules, new_rules):
        """Adds new rules to existing."""
        security_rule_xml = ('<security-rule-info>'
                             '<read-write>%s'
                             '</read-write>'
                             '<root>%s'
                             '</root>'
                             '</security-rule-info>')

        hostname_info_xml = ('<exports-hostname-info>'
                             '<name>%s</name>'
                             '</exports-hostname-info>')

        allowed_hosts_xml = []

        if type(new_rules) is not list:
            new_rules = [new_rules]

        all_rules = existing_rules + new_rules

        for ip in all_rules:
            allowed_hosts_xml.append(hostname_info_xml % ip)

        return security_rule_xml % (allowed_hosts_xml, allowed_hosts_xml)

    @staticmethod
    def _get_export_path(share):
        """Returns IP address and export location of a share."""
        export_location = share['export_location']

        if export_location is None:
            export_location = ':'

        return export_location.split(':')


class NetAppCIFSHelper(NetAppNASHelperBase):
    """Netapp specific NFS sharing driver."""

    CIFS_USER_GROUP = 'Administrators'

    def __init__(self, suds_client):
        super(NetAppCIFSHelper, self).__init__(suds_client)

    def create_share(self, target_id, share):
        """Creates CIFS storage."""
        cifs_status = self._get_cifs_status(target_id)

        if cifs_status == 'stopped':
            self._start_cifs_service(target_id)

        share_name = _get_valid_share_name(share['id'])

        self._set_qtree_security(target_id, share)
        self._add_share(target_id, share_name)
        self._restrict_access(target_id, 'everyone', share_name)

        ip_address = self._client.get_host_ip_by(target_id)

        cifs_location = self._set_export_location(ip_address, share_name)

        return cifs_location

    def delete_share(self, share):
        """Deletes CIFS storage"""
        host_ip, share_name = self._get_export_location(share)
        xml_args = '<share-name>%s</share-name>' % share_name
        self._client.send_request_to('cifs-share-delete', xml_args)

    def allow_access(self, context, share, access):
        """Allows access to a given CIFS storage for IPs in :access"""
        if access['access_type'] != 'passwd':
            ex_text = ('NetApp only supports "passwd" access type for CIFS.')
            raise exception.Error(ex_text)

        user = access['access_to']
        target, share_name = self._get_export_location(share)

        if self._user_exists(target, user):
            self._allow_access_for(target, user, share_name)
        else:
            exc_text = ('User "%s" does not exist on %s OnTap.') % (user,
                                                                    target)
            raise exception.Error(exc_text)

    def deny_access(self, context, share, access):
        """Denies access to a given CIFS storage for IPs in access."""
        host_ip, share_name = self._get_export_location(share)
        user = access['access_to']

        self._restrict_access(host_ip, user, share_name)

    def get_target(self, share):
        """Returns OnTap target IP based on share export location."""
        return self._get_export_location(share)[0]

    def _set_qtree_security(self, target, share):
        client = self._client
        share_name = '/vol/' + _get_valid_share_name(share['id'])

        xml_args = ('<args>'
                    '<arg>qtree</arg>'
                    '<arg>security</arg>'
                    '<arg>%s</arg>'
                    '<arg>mixed</arg>'
                    '</args>') % share_name

        client.send_request_to('system-cli', xml_args)

    def _restrict_access(self, target, user_name, share_name):
        xml_args = ('<user-name>%s</user-name>'
                    '<share-name>%s</share-name>') % (user_name, share_name)
        self._client.send_request_to('cifs-share-ace-delete',
                                     xml_args)

    def _start_cifs_service(self, target_id):
        """Starts CIFS service on OnTap target."""
        client = self._client
        return client.send_request_to('cifs-start',
                                      do_response_check=False)

    @staticmethod
    def _get_export_location(share):
        """Returns export location for a given CIFS share."""
        export_location = share['export_location']

        if export_location is None:
            export_location = '///'

        _, _, host_ip, share_name = export_location.split('/')
        return host_ip, share_name

    @staticmethod
    def _set_export_location(ip, share_name):
        """Returns export location of a share."""
        return "//%s/%s" % (ip, share_name)

    def _get_cifs_status(self, target_id):
        """Returns status of a CIFS service on target OnTap."""
        client = self._client
        response = client.send_request_to('cifs-status')
        return response.Status

    def _allow_access_for(self, target, username, share_name):
        """Allows access to the CIFS share for a given user."""
        xml_args = ('<access-rights>rwx</access-rights>'
                    '<share-name>%s</share-name>'
                    '<user-name>%s</user-name>') % (share_name, username)
        self._client.send_request_to('cifs-share-ace-set', xml_args)

    def _user_exists(self, target, user):
        """Returns True if user already exists on a target OnTap."""
        xml_args = ('<user-name>%s</user-name>') % user
        resp = self._client.send_request_to('useradmin-user-list',
                                            xml_args,
                                            do_response_check=False)

        return (resp.Status == 'passed')

    def _add_share(self, target_id, share_name):
        """Creates CIFS share on target OnTap host."""
        client = self._client
        xml_args = ('<path>/vol/%s</path>'
                    '<share-name>%s</share-name>') % (share_name, share_name)
        client.send_request_to('cifs-share-add', xml_args)

if __name__ == '__main__':
    client = NetAppApiClient()
    drv = NetAppClusteredShareDriver('')
    drv.do_setup('blah')
    print 'setup done'
    print drv._find_best_aggregate()
    print 'found best aggr'
    share = {'id': '12-34', 'size': 1, 'share_type': 'NfS'}
    drv.allocate_container('blah', share)
    print 'share allocated, table:', drv._share_table
    
    