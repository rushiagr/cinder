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
from cinder.api.views import policy_rules as policy_rules_view
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
    action = 'policy_rules:%s' % action_name
    extensions.extension_authorizer('policy', action)(context)


class PolicyController(wsgi.Controller):
    ##TODO: add docstring here
    # TODO: add viewbuilder here

    _view_builder_class = policy_rules_view.ViewBuilder

    def __init__(self, *args, **kwargs):
        super(PolicyController, self).__init__(*args, **kwargs)

    #@wsgi.action('os-allowed_actions')
    def get_actions(self, req):
        """Get allowed actions for the current user."""
        context = req.environ['cinder.context']
        rules_dic = policy.get_action_permissions_from_policy_json(context)
        LOG.error(rules_dic)
        return self._view_builder.rules(req, rules_dic)

class Policy_rules(extensions.ExtensionDescriptor):
    """Policy operations."""

    name = "PolicyRules"
    alias = "policy-rules"
    namespace = "http://docs.openstack.org/volume/ext/policy-rules/api/v1.1"
    updated = "2012-05-31T00:00:00+00:00"

    def get_resources(self):
        resources = []
        res = extensions.ResourceExtension(
                    Policy_rules.alias,
                    PolicyController(),
                    collection_actions={"get_actions": "GET"})

        resources.append(res)

        return resources
