from cinder.volume.drivers.netapp.api import NaApiError, NaElement, NaServer

# Trying to create a cifs server
#TODO

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