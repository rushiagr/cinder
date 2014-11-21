# Copyright (c) 2011 OpenStack Foundation
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

"""Policy Engine For Cinder"""


from oslo.config import cfg

from cinder import exception
from cinder.openstack.common import policy

CONF = cfg.CONF

_ENFORCER = None


def init():
    global _ENFORCER
    if not _ENFORCER:
        _ENFORCER = policy.Enforcer()


def enforce_action(context, action):
    """Checks that the action can be done by the given context.

    Applies a check to ensure the context's project_id and user_id can be
    applied to the given action using the policy enforcement api.
    """

    return enforce(context, action, {'project_id': context.project_id,
                                     'user_id': context.user_id})


def enforce(context, action, target):
    """Verifies that the action is valid on the target in this context.

       :param context: cinder context
       :param action: string representing the action to be checked
           this should be colon separated for clarity.
           i.e. ``compute:create_instance``,
           ``compute:attach_volume``,
           ``volume:attach_volume``

       :param object: dictionary representing the object of the action
           for object creation this should be a dictionary representing the
           location of the object e.g. ``{'project_id': context.project_id}``

       :raises PolicyNotAuthorized: if verification fails.

    """
    init()
    return _ENFORCER.enforce(action, target, context.to_dict(),
                             do_raise=True,
                             exc=exception.PolicyNotAuthorized,
                             action=action)


def check_is_admin(roles):
    """Whether or not roles contains 'admin' role according to policy setting.

    """
    init()

    # include project_id on target to avoid KeyError if context_is_admin
    # policy definition is missing, and default admin_or_owner rule
    # attempts to apply.  Since our credentials dict does not include a
    # project_id, this target can never match as a generic rule.
    target = {'project_id': ''}
    credentials = {'roles': roles}

    return _ENFORCER.enforce('context_is_admin', target, credentials)

def get_action_permissions_from_policy_json(context):
    """Parse policy.json to find allowed and forbidden actions.

    Returns a dictionary. Keys are actions from policy.json, values are
    'allowed' or 'forbidden'."""
    #NOTE(rushiagr): no information is provided for the actions not listed in
    # policy.json. In future, we could parse the value for the 'default' rule
    # from policy.json and if it is a very simple rule, e.g. "",
    # "admin_or_owner" or "nobody", we should also include key value pair of
    # 'default' and the value that default takes. Note that we should NOT send
    # any 'value' for any rule name, as the value can potentially contain
    # sensitive data, e.g. "not project:%(admin_only_poc_project)"

    init()
    _ENFORCER.load_rules(force_reload=True)
    return_dict = {}
    for rule in _ENFORCER.rules:
        # If rule doesn't contain a ':', the rule doesn't pertain to a specific
        # API, e.g. 'default'
        if rule.find(':') == -1:
            continue

        action_permission = 'allowed'
        try:
            enforce_action(context, rule)
            action_permission = 'forbidden'
        except exception.PolicyNotAuthorized:
            pass

        return_dict[rule] = action_permission

    return return_dict
