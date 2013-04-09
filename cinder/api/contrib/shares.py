# Copyright 2011 Justin Santa Barbara
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

"""The shares api."""

import webob
from webob import exc

from cinder.api import common
from cinder.api import extensions
from cinder.api.openstack import wsgi
from cinder.api.views import shares as share_views
from cinder.api import xmlutil
from cinder import exception
from cinder.openstack.common import log as logging
from cinder import share


LOG = logging.getLogger(__name__)


def make_share(elem):
    elem.set('id')
    elem.set('size')
    elem.set('availability_zone')
    elem.set('status')
    elem.set('name')
    elem.set('description')
    elem.set('share_type')
    elem.set('export_location')


def remove_invalid_options(context, search_options, allowed_search_options):
    """Remove search options that are not valid for non-admin API/context."""
    if context.is_admin:
        # Allow all options
        return
    # Otherwise, strip out all unknown options
    unknown_options = [opt for opt in search_options
                       if opt not in allowed_search_options]
    bad_options = ", ".join(unknown_options)
    log_msg = _("Removing options '%(bad_options)s' from query") % locals()
    LOG.debug(log_msg)
    for opt in unknown_options:
        del search_options[opt]


class ShareTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('share', selector='share')
        make_share(root)
        return xmlutil.MasterTemplate(root, 1)


class SharesTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('shares')
        elem = xmlutil.SubTemplateElement(root, 'share', selector='shares')
        make_share(elem)
        return xmlutil.MasterTemplate(root, 1)


class ShareController(wsgi.Controller):
    """The Shares API controller for the OpenStack API."""

    _view_builder_class = share_views.ViewBuilder

    def __init__(self):
        super(ShareController, self).__init__()
        self.share_api = share.API()

    @wsgi.serializers(xml=ShareTemplate)
    def show(self, req, id):
        """Return data about the given share."""
        context = req.environ['cinder.context']

        try:
            share = self.share_api.get(context, id)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        return self._view_builder.detail(req, share)

    def delete(self, req, id):
        """Delete a share."""
        context = req.environ['cinder.context']

        LOG.audit(_("Delete share with id: %s"), id, context=context)

        try:
            share = self.share_api.get(context, id)
            self.share_api.delete(context, share)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        return webob.Response(status_int=202)

    @wsgi.serializers(xml=SharesTemplate)
    def index(self, req):
        """Returns a summary list of shares."""
        return self._get_shares(req, is_detail=False)

    @wsgi.serializers(xml=SharesTemplate)
    def detail(self, req):
        """Returns a detailed list of shares."""
        return self._get_shares(req, is_detail=True)

    def _get_shares(self, req, is_detail):
        """Returns a list of shares, transformed through view
           builder.
        """
        context = req.environ['cinder.context']

        search_opts = {}
        search_opts.update(req.GET)

        # NOTE(ikharin): v2 API allows name instead of display_name
        if 'name' in search_opts:
            search_opts['display_name'] = search_opts['name']
            del search_opts['name']

        remove_invalid_options(context, search_opts,
                               self._get_share_search_options())

        shares = self.share_api.get_all(context, search_opts=search_opts)

        limited_list = common.limited(shares, req)

        if is_detail:
            shares = self._view_builder.detail_list(req, limited_list)
        else:
            shares = self._view_builder.summary_list(req, limited_list)
        return shares

    def _get_share_search_options(self):
        """Return share search options allowed by non-admin."""
        return ('name', 'status')

    @wsgi.serializers(xml=ShareTemplate)
    def create(self, req, body):
        """Creates a new share."""
        context = req.environ['cinder.context']

        if not self.is_valid_body(body, 'share'):
            raise exc.HTTPUnprocessableEntity()

        share = body['share']

        # NOTE(ikharin): v2 API allows name instead of display_name
        if share.get('name'):
            share['display_name'] = share.get('name')
            del share['name']

        # NOTE(ikharin): v2 API allows description instead of
        #                display_description
        if share.get('description'):
            share['display_description'] = share.get('description')
            del share['description']

        size = share['size']
        share_type = share['share_type'].upper()

        msg = (_("Create %(share_type)s share of %(size)s GB") %
               {'share_type': share_type, 'size': size})
        LOG.audit(msg, context=context)

        kwargs = {}
        kwargs['availability_zone'] = share.get('availability_zone')

        snapshot_id = share.get('snapshot_id')
        if snapshot_id is not None:
            kwargs['snapshot'] = self.share_api.get_snapshot(context,
                                                             snapshot_id)
        else:
            kwargs['snapshot'] = None

        display_name = share.get('display_name')
        display_description = share.get('display_description')
        new_share = self.share_api.create(context,
                                          share_type,
                                          size,
                                          display_name,
                                          display_description,
                                          **kwargs)

        # TODO(vish): Instance should be None at db layer instead of
        #             trying to lazy load, but for now we turn it into
        #             a dict to avoid an error.
        return self._view_builder.summary(req, dict(new_share.iteritems()))


class Shares(extensions.ExtensionDescriptor):
    """Enable share API."""
    name = 'Shares'
    alias = 'shares'
    namespace = ''
    updated = '2013-01-29T00:00:00+00:00'

    def get_resources(self):
        controller = ShareController()
        resource = extensions.ResourceExtension(
            'shares', controller, collection_actions={'detail': 'GET'},
            member_actions={'action': 'POST'})
        return [resource]
