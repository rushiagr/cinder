# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Piston Cloud Computing, Inc.
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
SQLAlchemy models for cinder data.
"""

from sqlalchemy import Column, Integer, String, Text, schema
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import ForeignKey, DateTime, Boolean, Enum
from sqlalchemy.orm import relationship, backref, object_mapper

from cinder.db.sqlalchemy.session import get_session

from cinder import exception
from cinder import flags
from cinder.openstack.common import timeutils


FLAGS = flags.FLAGS
BASE = declarative_base()


class CinderBase(object):
    """Base class for Cinder Models."""
    __table_args__ = {'mysql_engine': 'InnoDB'}
    __table_initialized__ = False
    created_at = Column(DateTime, default=timeutils.utcnow)
    updated_at = Column(DateTime, onupdate=timeutils.utcnow)
    deleted_at = Column(DateTime)
    deleted = Column(Boolean, default=False)
    metadata = None

    def save(self, session=None):
        """Save this object."""
        if not session:
            session = get_session()
        session.add(self)
        try:
            session.flush()
        except IntegrityError, e:
            if str(e).endswith('is not unique'):
                raise exception.Duplicate(str(e))
            else:
                raise

    def delete(self, session=None):
        """Delete this object."""
        self.deleted = True
        self.deleted_at = timeutils.utcnow()
        self.save(session=session)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __iter__(self):
        self._i = iter(object_mapper(self).columns)
        return self

    def next(self):
        n = self._i.next().name
        return n, getattr(self, n)

    def update(self, values):
        """Make the model object behave like a dict."""
        for k, v in values.iteritems():
            setattr(self, k, v)

    def iteritems(self):
        """Make the model object behave like a dict.

        Includes attributes from joins."""
        local = dict(self)
        joined = dict([(k, v) for k, v in self.__dict__.iteritems()
                      if not k[0] == '_'])
        local.update(joined)
        return local.iteritems()


class Service(BASE, CinderBase):
    """Represents a running service on a host."""

    __tablename__ = 'services'
    id = Column(Integer, primary_key=True)
    host = Column(String(255))  # , ForeignKey('hosts.id'))
    binary = Column(String(255))
    topic = Column(String(255))
    report_count = Column(Integer, nullable=False, default=0)
    disabled = Column(Boolean, default=False)
    availability_zone = Column(String(255), default='cinder')


class CinderNode(BASE, CinderBase):
    """Represents a running cinder service on a host."""

    __tablename__ = 'cinder_nodes'
    id = Column(Integer, primary_key=True)
    service_id = Column(Integer, ForeignKey('services.id'), nullable=True)


class Volume(BASE, CinderBase):
    """Represents a block storage device that can be attached to a vm."""
    __tablename__ = 'volumes'
    id = Column(String(36), primary_key=True)

    @property
    def name(self):
        return FLAGS.volume_name_template % self.id

    ec2_id = Column(Integer)
    user_id = Column(String(255))
    project_id = Column(String(255))

    snapshot_id = Column(String(36))

    host = Column(String(255))  # , ForeignKey('hosts.id'))
    size = Column(Integer)
    availability_zone = Column(String(255))  # TODO(vish): foreign key?
    instance_uuid = Column(String(36))
    mountpoint = Column(String(255))
    attach_time = Column(String(255))  # TODO(vish): datetime
    status = Column(String(255))  # TODO(vish): enum?
    attach_status = Column(String(255))  # TODO(vish): enum

    scheduled_at = Column(DateTime)
    launched_at = Column(DateTime)
    terminated_at = Column(DateTime)

    display_name = Column(String(255))
    display_description = Column(String(255))

    provider_location = Column(String(255))
    provider_auth = Column(String(255))

    volume_type_id = Column(String(36))
    source_volid = Column(String(36))


class VolumeMetadata(BASE, CinderBase):
    """Represents a metadata key/value pair for a volume."""
    __tablename__ = 'volume_metadata'
    id = Column(Integer, primary_key=True)
    key = Column(String(255))
    value = Column(String(255))
    volume_id = Column(String(36), ForeignKey('volumes.id'), nullable=False)
    volume = relationship(Volume, backref="volume_metadata",
                          foreign_keys=volume_id,
                          primaryjoin='and_('
                          'VolumeMetadata.volume_id == Volume.id,'
                          'VolumeMetadata.deleted == False)')


class VolumeTypes(BASE, CinderBase):
    """Represent possible volume_types of volumes offered."""
    __tablename__ = "volume_types"
    id = Column(String(36), primary_key=True)
    name = Column(String(255))

    volumes = relationship(Volume,
                           backref=backref('volume_type', uselist=False),
                           foreign_keys=id,
                           primaryjoin='and_('
                           'Volume.volume_type_id == VolumeTypes.id, '
                           'VolumeTypes.deleted == False)')


class VolumeTypeExtraSpecs(BASE, CinderBase):
    """Represents additional specs as key/value pairs for a volume_type."""
    __tablename__ = 'volume_type_extra_specs'
    id = Column(Integer, primary_key=True)
    key = Column(String(255))
    value = Column(String(255))
    volume_type_id = Column(String(36),
                            ForeignKey('volume_types.id'),
                            nullable=False)
    volume_type = relationship(
        VolumeTypes,
        backref="extra_specs",
        foreign_keys=volume_type_id,
        primaryjoin='and_('
        'VolumeTypeExtraSpecs.volume_type_id == VolumeTypes.id,'
        'VolumeTypeExtraSpecs.deleted == False)'
    )


class VolumeGlanceMetadata(BASE, CinderBase):
    """Glance metadata for a bootable volume."""
    __tablename__ = 'volume_glance_metadata'
    id = Column(Integer, primary_key=True, nullable=False)
    volume_id = Column(String(36), ForeignKey('volumes.id'))
    snapshot_id = Column(String(36), ForeignKey('snapshots.id'))
    key = Column(String(255))
    value = Column(Text)
    volume = relationship(Volume, backref="volume_glance_metadata",
                          foreign_keys=volume_id,
                          primaryjoin='and_('
                          'VolumeGlanceMetadata.volume_id == Volume.id,'
                          'VolumeGlanceMetadata.deleted == False)')


class Quota(BASE, CinderBase):
    """Represents a single quota override for a project.

    If there is no row for a given project id and resource, then the
    default for the quota class is used.  If there is no row for a
    given quota class and resource, then the default for the
    deployment is used. If the row is present but the hard limit is
    Null, then the resource is unlimited.
    """

    __tablename__ = 'quotas'
    id = Column(Integer, primary_key=True)

    project_id = Column(String(255), index=True)

    resource = Column(String(255))
    hard_limit = Column(Integer, nullable=True)


class QuotaClass(BASE, CinderBase):
    """Represents a single quota override for a quota class.

    If there is no row for a given quota class and resource, then the
    default for the deployment is used.  If the row is present but the
    hard limit is Null, then the resource is unlimited.
    """

    __tablename__ = 'quota_classes'
    id = Column(Integer, primary_key=True)

    class_name = Column(String(255), index=True)

    resource = Column(String(255))
    hard_limit = Column(Integer, nullable=True)


class QuotaUsage(BASE, CinderBase):
    """Represents the current usage for a given resource."""

    __tablename__ = 'quota_usages'
    id = Column(Integer, primary_key=True)

    project_id = Column(String(255), index=True)
    resource = Column(String(255))

    in_use = Column(Integer)
    reserved = Column(Integer)

    @property
    def total(self):
        return self.in_use + self.reserved

    until_refresh = Column(Integer, nullable=True)


class Reservation(BASE, CinderBase):
    """Represents a resource reservation for quotas."""

    __tablename__ = 'reservations'
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), nullable=False)

    usage_id = Column(Integer, ForeignKey('quota_usages.id'), nullable=False)

    project_id = Column(String(255), index=True)
    resource = Column(String(255))

    delta = Column(Integer)
    expire = Column(DateTime, nullable=False)


class Snapshot(BASE, CinderBase):
    """Represents a block storage device that can be attached to a VM."""
    __tablename__ = 'snapshots'
    id = Column(String(36), primary_key=True)

    @property
    def name(self):
        return FLAGS.snapshot_name_template % self.id

    @property
    def volume_name(self):
        return FLAGS.volume_name_template % self.volume_id

    user_id = Column(String(255))
    project_id = Column(String(255))

    volume_id = Column(String(36))
    status = Column(String(255))
    progress = Column(String(255))
    volume_size = Column(Integer)

    display_name = Column(String(255))
    display_description = Column(String(255))

    provider_location = Column(String(255))

    volume = relationship(Volume, backref="snapshots",
                          foreign_keys=volume_id,
                          primaryjoin='and_('
                          'Snapshot.volume_id == Volume.id,'
                          'Snapshot.deleted == False)')


class SnapshotMetadata(BASE, CinderBase):
    """Represents a metadata key/value pair for a snapshot."""
    __tablename__ = 'snapshot_metadata'
    id = Column(Integer, primary_key=True)
    key = Column(String(255))
    value = Column(String(255))
    snapshot_id = Column(String(36),
                         ForeignKey('snapshots.id'),
                         nullable=False)
    snapshot = relationship(Snapshot, backref="snapshot_metadata",
                            foreign_keys=snapshot_id,
                            primaryjoin='and_('
                            'SnapshotMetadata.snapshot_id == Snapshot.id,'
                            'SnapshotMetadata.deleted == False)')


class IscsiTarget(BASE, CinderBase):
    """Represents an iscsi target for a given host."""
    __tablename__ = 'iscsi_targets'
    __table_args__ = (schema.UniqueConstraint("target_num", "host"),
                      {'mysql_engine': 'InnoDB'})
    id = Column(Integer, primary_key=True)
    target_num = Column(Integer)
    host = Column(String(255))
    volume_id = Column(String(36), ForeignKey('volumes.id'), nullable=True)
    volume = relationship(Volume,
                          backref=backref('iscsi_target', uselist=False),
                          foreign_keys=volume_id,
                          primaryjoin='and_(IscsiTarget.volume_id==Volume.id,'
                          'IscsiTarget.deleted==False)')


class Migration(BASE, CinderBase):
    """Represents a running host-to-host migration."""
    __tablename__ = 'migrations'
    id = Column(Integer, primary_key=True, nullable=False)
    # NOTE(tr3buchet): the ____compute variables are instance['host']
    source_compute = Column(String(255))
    dest_compute = Column(String(255))
    # NOTE(tr3buchet): dest_host, btw, is an ip address
    dest_host = Column(String(255))
    old_instance_type_id = Column(Integer())
    new_instance_type_id = Column(Integer())
    instance_uuid = Column(String(255),
                           ForeignKey('instances.uuid'),
                           nullable=True)
    #TODO(_cerberus_): enum
    status = Column(String(255))


class SMFlavors(BASE, CinderBase):
    """Represents a flavor for SM volumes."""
    __tablename__ = 'sm_flavors'
    id = Column(Integer(), primary_key=True)
    label = Column(String(255))
    description = Column(String(255))


class SMBackendConf(BASE, CinderBase):
    """Represents the connection to the backend for SM."""
    __tablename__ = 'sm_backend_config'
    id = Column(Integer(), primary_key=True)
    flavor_id = Column(Integer, ForeignKey('sm_flavors.id'), nullable=False)
    sr_uuid = Column(String(255))
    sr_type = Column(String(255))
    config_params = Column(String(2047))


class SMVolume(BASE, CinderBase):
    __tablename__ = 'sm_volume'
    id = Column(String(36), ForeignKey(Volume.id), primary_key=True)
    backend_id = Column(Integer, ForeignKey('sm_backend_config.id'),
                        nullable=False)
    vdi_uuid = Column(String(255))


class Backup(BASE, CinderBase):
    """Represents a backup of a volume to Swift."""
    __tablename__ = 'backups'
    id = Column(String(36), primary_key=True)

    @property
    def name(self):
        return FLAGS.backup_name_template % self.id

    user_id = Column(String(255), nullable=False)
    project_id = Column(String(255), nullable=False)

    volume_id = Column(String(36), nullable=False)
    host = Column(String(255))
    availability_zone = Column(String(255))
    display_name = Column(String(255))
    display_description = Column(String(255))
    container = Column(String(255))
    status = Column(String(255))
    fail_reason = Column(String(255))
    service_metadata = Column(String(255))
    service = Column(String(255))
    size = Column(Integer)
    object_count = Column(Integer)


class Share(BASE, CinderBase):
    """Represents an NFS and CIFS shares."""
    __tablename__ = 'shares'

    @property
    def name(self):
        return FLAGS.share_name_template % self.id

    id = Column(String(36), primary_key=True)
    user_id = Column(String(255))
    project_id = Column(String(255))
    host = Column(String(255))
    size = Column(Integer)
    availability_zone = Column(String(255))
    status = Column(String(255))
    scheduled_at = Column(DateTime)
    launched_at = Column(DateTime)
    terminated_at = Column(DateTime)
    display_name = Column(String(255))
    display_description = Column(String(255))
    snapshot_id = Column(String(36))
    share_proto = Column(String(255))
    export_location = Column(String(255))


class ShareAccessMapping(BASE, CinderBase):
    """Represents access to NFS."""
    STATE_NEW = 'new'
    STATE_ACTIVE = 'active'
    STATE_DELETING = 'deleting'
    STATE_DELETED = 'deleted'
    STATE_ERROR = 'error'

    __tablename__ = 'share_access_map'
    id = Column(String(36), primary_key=True)
    share_id = Column(String(36), ForeignKey('shares.id'))
    access_type = Column(String(255))
    access_to = Column(String(255))
    state = Column(Enum(STATE_NEW, STATE_ACTIVE,
                        STATE_DELETING, STATE_DELETED, STATE_ERROR),
                   default=STATE_NEW)


class ShareSnapshot(BASE, CinderBase):
    """Represents a snapshot of a share."""
    __tablename__ = 'share_snapshots'

    @property
    def name(self):
        return FLAGS.share_snapshot_name_template % self.id

    @property
    def share_name(self):
        return FLAGS.share_name_template % self.share_id

    id = Column(String(36), primary_key=True)
    user_id = Column(String(255))
    project_id = Column(String(255))
    share_id = Column(String(36))
    status = Column(String(255))
    progress = Column(String(255))
    display_name = Column(String(255))
    display_description = Column(String(255))
    share_size = Column(Integer)
    share_proto = Column(String(255))
    export_location = Column(String(255))
    share = relationship(Share, backref="snapshots",
                         foreign_keys=share_id,
                         primaryjoin='and_('
                         'ShareSnapshot.share_id == Share.id,'
                         'ShareSnapshot.deleted == False)')


def register_models():
    """Register Models and create metadata.

    Called from cinder.db.sqlalchemy.__init__ as part of loading the driver,
    it will never need to be called explicitly elsewhere unless the
    connection is lost and needs to be reestablished.
    """
    from sqlalchemy import create_engine
    models = (Backup,
              Migration,
              Service,
              Share,
              ShareAccessMapping,
              ShareSnapshot,
              SMBackendConf,
              SMFlavors,
              SMVolume,
              Volume,
              VolumeMetadata,
              SnapshotMetadata,
              VolumeTypeExtraSpecs,
              VolumeTypes,
              VolumeGlanceMetadata,
              )
    engine = create_engine(FLAGS.sql_connection, echo=False)
    for model in models:
        model.metadata.create_all(engine)
