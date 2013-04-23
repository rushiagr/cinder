from cinder.volume.drivers.netapp.api import NaApiError, NaElement, NaServer
from lxml import etree

# Trying to create a cifs server
#TODO

'''
Notes for this file

>>> response = server.invoke_successfully(NaElement('vserver-get'))
>>> response.to_string()
'<results xmlns="http://www.netapp.com/filer/admin" status="passed"><attributes><vserver
-info><aggr-list><aggr-name>aggr2</aggr-name><aggr-name>aggr3</aggr-name></aggr-list><al
lowed-protocols><protocol>nfs</protocol><protocol>cifs</protocol><protocol>fcp</protocol
><protocol>iscsi</protocol></allowed-protocols><antivirus-on-access-policy>default</anti
virus-on-access-policy><comment/><is-repository-vserver>false</is-repository-vserver><la
nguage>c</language><max-volumes>unlimited</max-volumes><name-mapping-switch><nmswitch>fi
le</nmswitch></name-mapping-switch><name-server-switch><nsswitch>file</nsswitch><nsswitc
h>nis</nsswitch></name-server-switch><quota-policy>default</quota-policy><root-volume>ru
shi_root</root-volume><root-volume-aggregate>aggr2</root-volume-aggregate><root-volume-s
ecurity-style>unix</root-volume-security-style><snapshot-policy>default</snapshot-policy
><state>running</state><uuid>110dc3b1-aa41-11e2-b3d0-123478563412</uuid><vserver-aggr-in
fo-list><vserver-aggr-info><aggr-availsize>986827870208</aggr-availsize><aggr-name>aggr2
</aggr-name></vserver-aggr-info><vserver-aggr-info><aggr-availsize>752918863872</aggr-av
ailsize><aggr-name>aggr3</aggr-name></vserver-aggr-info></vserver-aggr-info-list><vserve
r-name>rushi</vserver-name><vserver-type>data</vserver-type></vserver-info></attributes>
</results>'



'''

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
    
    
    return aggr_dict



if __name__ == '__main__':
    server = NaServer('10.63.165.71',
                      server_type='filer',
                      transport_type='http',
                      style='basic_auth',
                      username='admin',
                      password='Netapp123')
    
    # ONTAPI version
    server.set_api_version(1,15)
    
    # Vserver name
    server.set_vserver('rushi')