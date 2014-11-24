# Copyright (C) 2014 eBay Inc.
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

from cinder.api import common


class ViewBuilder(common.ViewBuilder):
    """Model policy-rules API responses as a Python dictionary."""

    _collection_name = "policy-rules"

    def __init__(self):
        """Initialize view builder."""
        super(ViewBuilder, self).__init__()

    def summary(self, request, rule):
        """Detailed view of a single policy rule."""
        return {
            'rule': {
                'name': rule.get('name'),
                'authorization': rule.get('authorization')
            }
        }

    def rules(self, request, rules):
        rule_list = [{'rule': k, 'authorization': v} for k, v in rules.items()]
        rules_dict = dict(rule=rule_list)

        return rules_dict
