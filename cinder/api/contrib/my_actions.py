#   Copyright 2012 OpenStack Foundation
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.


from oslo import messaging
import webob

from cinder.api import extensions
from cinder.api.openstack import wsgi
from cinder.api import xmlutil
from cinder import exception
from cinder.i18n import _
from cinder.openstack.common import log as logging
from cinder.openstack.common import strutils
from cinder import policy
from cinder import utils
from cinder import volume

from cinder.api import contrib


LOG = logging.getLogger(__name__)


def authorize(context, action_name):
    action = 'my_actions:%s' % action_name
    extensions.extension_authorizer('volume', action)(context)


class VolumeToImageSerializer(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('os-volume_upload_image',
                                       selector='os-volume_upload_image')
        root.set('id')
        root.set('updated_at')
        root.set('status')
        root.set('display_description')
        root.set('size')
        root.set('volume_type')
        root.set('image_id')
        root.set('container_format')
        root.set('disk_format')
        root.set('image_name')
        return xmlutil.MasterTemplate(root, 1)


class VolumeToImageDeserializer(wsgi.XMLDeserializer):
    """Deserializer to handle xml-formatted requests."""
    def default(self, string):
        dom = utils.safe_minidom_parse_string(string)
        action_node = dom.childNodes[0]
        action_name = action_node.tagName

        action_data = {}
        attributes = ["force", "image_name", "container_format", "disk_format"]
        for attr in attributes:
            if action_node.hasAttribute(attr):
                action_data[attr] = action_node.getAttribute(attr)
        if 'force' in action_data and action_data['force'] == 'True':
            action_data['force'] = True
        return {'body': {action_name: action_data}}


class MyActionsController(wsgi.Controller):
    def __init__(self, *args, **kwargs):
        super(MyActionsController, self).__init__(*args, **kwargs)

    @wsgi.action('os-allowed_actions')
    def _get_allowed_actions_(self, req, id, body):
        """Get allowed actions for the current user."""
        context = req.environ['cinder.context']
        dic = policy.get_action_permissions_from_policy_json(context)

        return webob.Response(body='corrct')
        return webob.Response(status_int=200)


class My_actions(extensions.ExtensionDescriptor):
    """Enable volume actions
    """

    name = "MyActions"
    alias = "os-my-actions"
    namespace = "http://docs.openstack.org/volume/ext/my-actions/api/v1.1"
    updated = "2012-05-31T00:00:00+00:00"

    def get_controller_extensions(self):
        controller = MyActionsController()
        extension = extensions.ControllerExtension(self, 'volumes', controller)
        return [extension]
