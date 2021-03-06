# Copyright 2003-2009 Mike Wakerly <opensource@hoho.com>
#
# This file is part of the Pykeg package of the Kegbot project.
# For more information on Pykeg or Kegbot, see http://kegbot.org/
#
# Pykeg is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# Pykeg is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pykeg.  If not, see <http://www.gnu.org/licenses/>.

import uuid

from kegbot.util import units

from . import models

METER_NAME_0 = 'kegboard.flow0'
METER_NAME_1 = 'kegboard.flow1'


def db_is_installed():
    return models.KegbotSite.objects.all().count() > 0

class AlreadyInstalledError(Exception):
    """Thrown when database is already installed."""

def set_defaults(force=False, set_is_setup=False):
    """Creates a new site and sets defaults, returning that site."""
    if not force and db_is_installed():
        raise AlreadyInstalledError("Database is already installed.")

    site = models.KegbotSite.get()
    if set_is_setup and not site.is_setup:
        site.is_setup = True
        site.save()

    # KegTap defaults
    main_tap = models.KegTap(name='Main Tap', meter_name=METER_NAME_0)
    main_tap.save()
    secondary_tap = models.KegTap(name='Second Tap', meter_name=METER_NAME_1)
    secondary_tap.save()

    return site
