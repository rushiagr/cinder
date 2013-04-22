from cinder.volume.drivers.netapp.api import NaApiError, NaElement, NaServer
from lxml import etree

# Trying to create a cifs server
#TODO

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