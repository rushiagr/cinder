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
from cinder.openstack.common import policy
from cinder import utils
from cinder import volume


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
        self.volume_api = volume.API()

    @wsgi.action('os-extendx')
    def _extend(self, req, id, body):
        """Extend size of volume."""
        context = req.environ['cinder.context']
        return webob.Response(body='extendx')
        try:
            volume = self.volume_api.get(context, id)
        except exception.VolumeNotFound as error:
            raise webob.exc.HTTPNotFound(explanation=error.msg)

        try:
            int(body['os-extend']['new_size'])
        except (KeyError, ValueError, TypeError):
            msg = _("New volume size must be specified as an integer.")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        size = int(body['os-extend']['new_size'])
        self.volume_api.extend(context, volume, size)
        return webob.Response(status_int=202)


    @wsgi.action('os-set_bootablex')
    def _set_bootable(self, req, id, body):
        """Update bootable status of a volume."""
        context = req.environ['cinder.context']
        enforcer = policy.Enforcer()
        enforcer.load_rules(True)
        LOG.warning(enforcer.rules)
        return webob.Response(body='corrct')
        try:
            volume = self.volume_api.get(context, id)
        except exception.VolumeNotFound as error:
            raise webob.exc.HTTPNotFound(explanation=error.msg)

        try:
            bootable = body['os-set_bootable']['bootable']
        except KeyError:
            msg = _("Must specify bootable in request.")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        if isinstance(bootable, basestring):
            try:
                bootable = strutils.bool_from_string(bootable,
                                                     strict=True)
            except ValueError:
                msg = _("Bad value for 'bootable'")
                raise webob.exc.HTTPBadRequest(explanation=msg)

        elif not isinstance(bootable, bool):
            msg = _("'bootable' not string or bool")
            raise webob.exc.HTTPBadRequest(explanation=msg)

        update_dict = {'bootable': bootable}

        self.volume_api.update(context, volume, update_dict)
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
