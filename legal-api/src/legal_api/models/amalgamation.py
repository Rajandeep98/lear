# Copyright © 2019 Province of British Columbia
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Meta information about the service.

Currently this only provides API versioning information
"""

from enum import auto

from ..utils.base import BaseEnum
from .db import db


class Amalgamation(db.Model):  # pylint: disable=too-many-instance-attributes
    """This class manages the amalgamations."""

    # pylint: disable=invalid-name
    class AmalgamationTypes(BaseEnum):
        """Enum for the amalgamation type."""

        regular = auto()
        vertical = auto()
        horizontal = auto()

    # __versioned__ = {}
    __tablename__ = 'amalgamation'

    id = db.Column(db.Integer, primary_key=True)
    amalgamation_type = db.Column('amalgamation_type', db.Enum(AmalgamationTypes), nullable=False)
    amalgamation_date = db.Column('amalgamation_date', db.DateTime(timezone=True), nullable=False)
    court_approval = db.Column('court_approval', db.Boolean())

    # parent keys
    business_id = db.Column('business_id', db.Integer, db.ForeignKey('businesses.id'), index=True)
    filing_id = db.Column('filing_id', db.Integer, db.ForeignKey('filings.id'), nullable=False)

    # Relationships
    amalgamating_businesses = db.relationship('AmalgamatingBusiness', backref='amalgamation')
    business = db.relationship('Business', back_populates='amalgamation')

    def save(self):
        """Save the object to the database immediately."""
        db.session.add(self)
        db.session.commit()