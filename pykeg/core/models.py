# -*- coding: latin-1 -*-
# Copyright 2010 Mike Wakerly <opensource@hoho.com>
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

import datetime
import os
import pytz
import random
import re

from django.contrib.auth.models import AbstractUser
from django.core.urlresolvers import reverse
from django.db import IntegrityError
from django.db import models
from django.db.models.signals import post_save
from django.db.models.signals import pre_save
from django.utils import timezone

from imagekit.models import ImageSpecField
from imagekit.processors import Adjust
from imagekit.processors import resize

from pykeg import EPOCH

from pykeg.core import kb_common
from pykeg.core import keg_sizes
from pykeg.core import fields
from pykeg.core import jsonfield
from pykeg.core import managers
from pykeg.core.util import make_serial

from kegbot.util import units
from kegbot.util import util

"""Django models definition for the kegbot database."""

TIMEZONE_CHOICES = ((z, z) for z in pytz.common_timezones)


class User(AbstractUser):
    mugshot = models.ForeignKey('Picture', blank=True, null=True,
        related_name='user_mugshot',
        on_delete=models.SET_NULL)

    def get_absolute_url(self):
        return reverse('kb-drinker', kwargs={'username': self.username})

    def get_stats_record(self):
        qs = UserStats.objects.filter(user=self).order_by('-id')
        if len(qs):
            return qs[0]
        return None

    def get_stats(self):
        ret = {}
        record = self.get_stats_record()
        if record:
            ret = record.stats
        return util.AttrDict(ret)

    def get_api_key(self):
        api_key, new = ApiKey.objects.get_or_create(user=self,
            defaults={'key': ApiKey.generate_key()})
        return api_key.key


class KegbotSite(models.Model):
    name = models.CharField(max_length=64, unique=True, default='default',
        editable=False)
    is_active = models.BooleanField(default=True,
        help_text='On/off switch for this site.')
    is_setup = models.BooleanField(default=False,
        help_text='True if the site has completed setup.',
        editable=False)
    epoch = models.PositiveIntegerField(default=EPOCH,
        help_text='Database epoch number.',
        editable=False)
    serial_number = models.TextField(max_length=128, editable=False,
        blank=True, default='',
        help_text='A unique id for this system.')

    def __str__(self):
        return self.name

    @classmethod
    def get(cls):
        """Gets the default site settings."""
        return KegbotSite.objects.get_or_create(name='default',
            defaults={'is_setup': False})[0]

    def GetStatsRecord(self):
        try:
            return SystemStats.objects.latest()
        except SystemStats.DoesNotExist:
            return None

    def GetStats(self):
        ret = {}
        record = self.GetStatsRecord()
        if record:
            ret = record.stats
        return util.AttrDict(ret)

def _kegbotsite_pre_save(sender, instance, **kwargs):
    if not instance.serial_number:
        instance.serial_number = make_serial()
pre_save.connect(_kegbotsite_pre_save, sender=KegbotSite)

def _kegbotsite_post_save(sender, instance, **kwargs):
    """Creates a SiteSettings object if none already exists."""
    settings, _ = SiteSettings.objects.get_or_create(site=instance)
post_save.connect(_kegbotsite_post_save, sender=KegbotSite)

class SiteSettings(models.Model):
    """General system-wide settings."""
    VOLUME_DISPLAY_UNITS_CHOICES = (
      ('metric', 'Metric (mL, L)'),
      ('imperial', 'Imperial (oz, pint)'),
    )
    TEMPERATURE_DISPLAY_UNITS_CHOICES = (
      ('f', 'Fahrenheit'),
      ('c', 'Celsius'),
    )
    PRIVACY_CHOICES = (
      ('public', 'Public: Browsing does not require login'),
      ('members', 'Members only: Must log in to browse'),
      ('staff', 'Staff only: Only logged-in staff accounts may browse'),
    )
    DEFAULT_PRIVACY = 'public'

    site = models.OneToOneField(KegbotSite, related_name='settings')
    volume_display_units = models.CharField(max_length=64,
        choices=VOLUME_DISPLAY_UNITS_CHOICES, default='imperial',
        help_text='Unit system to use when displaying volumetric data.')
    temperature_display_units = models.CharField(max_length=64,
        choices=TEMPERATURE_DISPLAY_UNITS_CHOICES, default='f',
        help_text='Unit system to use when displaying temperature data.')
    title = models.CharField(max_length=64, default='My Kegbot',
        help_text='The title of this site.')
    background_image = models.ForeignKey('Picture', blank=True, null=True,
        on_delete=models.SET_NULL,
        help_text='Background for this site.')
    google_analytics_id = models.CharField(blank=True, null=True, max_length=64,
        help_text='Set to your Google Analytics ID to enable tracking. '
        'Example: UA-XXXX-y')
    session_timeout_minutes = models.PositiveIntegerField(
        default=kb_common.DRINK_SESSION_TIME_MINUTES,
        help_text='Maximum time, in minutes, that a session may be idle (no pours) '
            'before it is considered to be finished.  '
            'Recommended value is %s.' % kb_common.DRINK_SESSION_TIME_MINUTES)
    privacy = models.CharField(max_length=63, choices=PRIVACY_CHOICES,
        default=DEFAULT_PRIVACY,
        help_text='Whole-system setting for system privacy.')
    guest_name = models.CharField(max_length=63, default='guest',
        help_text='Name to be shown in various places for unauthenticated pours.')
    guest_image = models.ForeignKey('Picture', blank=True, null=True,
        related_name='guest_images',
        on_delete=models.SET_NULL,
        help_text='Profile picture to be shown for unauthenticated pours.')
    default_user = models.ForeignKey(User, blank=True, null=True,
        help_text='Default user to set as owner for unauthenticated drinks. '
            'When set, the "guest" user will not be used. This is mostly '
            'useful for closed, single-user systems.')
    registration_allowed = models.BooleanField(default=True,
        help_text='Whether to allow new user registration.')
    registration_confirmation = models.BooleanField(default=False,
        help_text='Whether registration requires e-mail confirmation.')
    allowed_hosts = models.TextField(blank=True, null=True, default='',
        help_text='List of allowed hostnames. If blank, validation is disabled.')
    timezone = models.CharField(max_length=255, choices=TIMEZONE_CHOICES,
        default='UTC',
        help_text='Time zone for this system')
    hostname = models.CharField(max_length=255,
        help_text='Hostname (and optional port) for this system. Examples: mykegbot.example.com, 192.168.1.100:8000')
    use_ssl = models.BooleanField(default=False,
        help_text='Use SSL for URLs to this site.')

    class Meta:
        verbose_name_plural = "site settings"

    def GetSessionTimeoutDelta(self):
        return datetime.timedelta(minutes=self.session_timeout_minutes)

    def base_url(self):
        protocol = 'http'
        if self.use_ssl:
            protocol = 'https'
        return '%s://%s' % (protocol, self.hostname)

    def reverse_full(self, *args, **kwargs):
        """Calls reverse, and returns a full URL (includes base_url())."""
        return '%s%s' % (self.base_url(), reverse(*args, **kwargs))

    def format_volume(self, volume_ml):
        if SiteSettings.get().volume_display_units == 'metric':
            if volume_ml < 500:
                return '%d mL' % int(volume_ml)
            return '%.1f L' % (volume_ml / 1000.0)
        else:
            return '%1.f oz' % units.Quantity(volume_ml).InOunces()

    @classmethod
    def get(cls):
        """Gets the default site settings."""
        return KegbotSite.get().settings


class ApiKey(models.Model):
    """Grants access to certain API endpoints to a user via a secret key."""
    user = models.OneToOneField(User,
        help_text='User receiving API access.')
    key = models.CharField(max_length=127, editable=False, unique=True,
        help_text='The secret key.')
    active = models.BooleanField(default=True,
        help_text='Whether access by this key is currently allowed.')

    def is_active(self):
        """Returns true if both the key and the key's user are active."""
        return self.active and self.user.is_active

    def regenerate(self):
        """Discards and regenerates the key."""
        self.key = self.generate_key()
        self.save()

    @classmethod
    def generate_key(cls):
        """Returns a new random key."""
        return '%032x' % random.randint(0, 2**128 - 1)


class BeverageProducer(models.Model):
    """Information about a beverage producer (brewer, vineyard, etc)."""
    name = models.CharField(max_length=255,
        help_text='Name of the brewer')
    country = fields.CountryField(default='USA',
        help_text='Country of origin')
    origin_state = models.CharField(max_length=128,
        default='', blank=True, null=True,
        help_text='State of origin, if applicable')
    origin_city = models.CharField(max_length=128, default='', blank=True,
        null=True,
        help_text='City of origin, if known')
    is_homebrew = models.BooleanField(default=False)
    url = models.URLField(default='', blank=True, null=True,
        help_text='Brewer\'s home page')
    description = models.TextField(default='', blank=True, null=True,
        help_text='A short description of the brewer')
    picture = models.ForeignKey('Picture', blank=True, null=True,
        on_delete=models.SET_NULL)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class Beverage(models.Model):
    """Information about a beverage being served (beer, typically)."""
    TYPE_BEER = 'beer'
    TYPE_WINE = 'wine'
    TYPE_SODA = 'soda'
    TYPE_KOMBUCHA = 'kombucha'
    TYPE_OTHER = 'other'

    TYPES = (
        (TYPE_BEER, 'Beer'),
        (TYPE_WINE, 'Wine'),
        (TYPE_WINE, 'Soda'),
        (TYPE_WINE, 'Kombucha'),
        (TYPE_OTHER, 'Other/Unknown'),
    )

    name = models.CharField(max_length=255,
        help_text='Name of the beverage, such as "Potrero Pale".')
    producer = models.ForeignKey(BeverageProducer)

    beverage_type = models.CharField(max_length=32,
        choices=TYPES,
        default=TYPE_BEER)
    style = models.CharField(max_length=255, blank=True, null=True,
        help_text='Beverage style within type, eg "Pale Ale", "Pinot Noir".')
    description = models.TextField(blank=True, null=True,
        help_text='Free-form description of the beverage.')

    picture = models.ForeignKey('Picture', blank=True, null=True,
        help_text='Label image.')
    vintage_year = models.DateField(blank=True, null=True,
        help_text='Date of production, for wines or special/seasonal editions')

    abv_percent = models.FloatField(blank=True, null=True,
        help_text='Alcohol by volume, as percentage (0.0-100.0).')
    calories_per_ml = models.FloatField(blank=True, null=True,
        help_text='Calories per mL of beverage.')
    carbs_per_ml = models.FloatField(blank=True, null=True,
        help_text='Carbohydrates per mL of beverage.')

    original_gravity = models.FloatField(blank=True, null=True,
        help_text='Original gravity (beer only).')
    specific_gravity = models.FloatField(blank=True, null=True,
        help_text='Specific/final gravity (beer only).')
    untappd_beer_id = models.IntegerField(blank=True, null=True,
        help_text='Untappd.com resource ID (beer only).')

    beverage_backend = models.CharField(max_length=255, blank=True, null=True,
        help_text='Future use.')
    beverage_backend_id = models.CharField(max_length=255, blank=True, null=True,
        help_text='Future use.')

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return '%s by %s' % (self.name, self.producer)


class KegTap(models.Model):
    """A physical tap of beer."""
    meter_name = models.CharField(max_length=128, unique=True,
        help_text='Flow meter name for this tap, for example, "kegboard.flow0"')
    name = models.CharField(max_length=128,
        help_text='The display name for this tap, for example, "Main Tap".')
    relay_name = models.CharField(max_length=128, blank=True, null=True,
        help_text='Name of relay attached to this tap.')
    ml_per_tick = models.FloatField(default=kb_common.ML_PER_TICK,
        help_text='mL per flow meter tick.  Common values: %s '
        '(SwissFlow), 0.454545454545 (Vision 2000)' % kb_common.ML_PER_TICK)
    description = models.TextField(blank=True, null=True,
        help_text='User-visible description for this tap.')
    current_keg = models.OneToOneField('Keg', blank=True, null=True,
        related_name='current_tap',
        help_text='Keg currently connected to this tap.')
    temperature_sensor = models.ForeignKey('ThermoSensor', blank=True, null=True,
        on_delete=models.SET_NULL,
        help_text='Sensor monitoring the temperature of this Keg.')

    def __str__(self):
        return "%s: %s" % (self.meter_name, self.name)

    def is_active(self):
        """Returns True if the tap has an active Keg."""
        return self.current_keg is not None

    def Temperature(self):
        if self.temperature_sensor:
            last_rec = self.temperature_sensor.thermolog_set.all().order_by('-time')
            if last_rec:
                return last_rec[0]
        return None


class Keg(models.Model):
    """Record for each physical Keg."""
    type = models.ForeignKey(Beverage,
        on_delete=models.PROTECT,
        help_text='Beverage in this Keg.')
    keg_type = models.CharField(max_length=32,
        choices=keg_sizes.DESCRIPTIONS.items(),
        default=keg_sizes.HALF_BARREL,
        help_text='Keg container type, used to initialize keg\'s full volume')
    served_volume_ml = models.FloatField(default=0, editable=False,
        help_text='Computed served volume.')
    full_volume_ml = models.FloatField(default=0, editable=False,
        help_text='Full volume of this Keg; usually set automatically from keg_type.')
    start_time = models.DateTimeField(default=timezone.now,
        help_text='Time the Keg was first tapped.')
    end_time = models.DateTimeField(default=timezone.now,
        help_text='Time the Keg was finished or disconnected.')
    online = models.BooleanField(default=True, editable=False,
        help_text='True if the keg is currently assigned to a tap.')
    finished = models.BooleanField(default=True, editable=False,
        help_text='True when the Keg has been exhausted or discarded.')
    description = models.CharField(max_length=256, blank=True, null=True,
        help_text='User-visible description of the Keg.')
    spilled_ml = models.FloatField(default=0, editable=False,
        help_text='Amount of beverage poured without an associated Drink.')
    notes = models.TextField(blank=True, null=True,
        help_text='Private notes about this keg, viewable only by admins.')

    def get_absolute_url(self):
        return reverse('kb-keg', args=(str(self.id),))

    def full_url(self):
        return '%s%s' % (SiteSettings.get().base_url(), self.get_absolute_url())

    def full_volume(self):
        return self.full_volume_ml

    def served_volume(self):
        # Deprecated
        return self.served_volume_ml

    def remaining_volume_ml(self):
        return self.full_volume_ml - self.served_volume_ml - self.spilled_ml

    def percent_full(self):
        result = float(self.remaining_volume_ml()) / float(self.full_volume_ml) * 100
        result = max(min(result, 100), 0)
        return result

    def keg_age(self):
        if self.online:
            end = timezone.now()
        else:
            end = self.end_time
        return end - self.start_time

    def is_empty(self):
        return float(self.remaining_volume_ml()) <= 0

    def previous(self):
        q = Keg.objects.filter(start_time__lt=self.start_time).order_by('-start_time')
        if q.count():
            return q[0]
        return None

    def next(self):
        q = Keg.objects.filter(start_time__gt=self.start_time).order_by('start_time')
        if q.count():
            return q[0]
        return None

    def GetStatsRecord(self):
        qs = KegStats.objects.filter(keg=self).order_by('-id')
        if len(qs):
            return qs[0]
        return None

    def GetStats(self):
        ret = {}
        record = self.GetStatsRecord()
        if record:
            ret = record.stats
        return util.AttrDict(ret)

    def Sessions(self):
        chunks = SessionChunk.objects.filter(keg=self).order_by('-start_time').select_related(depth=2)
        sessions = []
        sess = None
        for c in chunks:
            # Skip same sessions
            if c.session == sess:
                continue
            sess = c.session
            sessions.append(sess)
        return sessions

    def TopDrinkers(self):
        stats = self.GetStats()
        if not stats:
            return []
        ret = []
        entries = stats.get('volume_by_drinker', {})
        for username, vol in entries.iteritems():
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                continue  # should not happen
            ret.append((vol, user))
        ret.sort(reverse=True)
        return ret

    def __str__(self):
        return "Keg #%s - %s" % (self.id, self.type)

def _keg_pre_save(sender, instance, **kwargs):
    keg = instance
    # We don't need to do anything if the keg is still online.
    if keg.online:
        return

    # Determine first drink date & set keg start date to it if earlier.
    drinks = keg.drinks.all().order_by('time')
    if drinks:
        drink = drinks[0]
        if drink.time < keg.start_time:
            keg.start_time = drink.time

    # Determine last drink date & set keg end date to it if later.
    drinks = keg.drinks.all().order_by('-time')
    if drinks:
        drink = drinks[0]
        if drink.time > keg.end_time:
            keg.end_time = drink.time

pre_save.connect(_keg_pre_save, sender=Keg)


class Drink(models.Model):
    """ Table of drinks records """
    class Meta:
        get_latest_by = 'time'
        ordering = ('-time',)

    ticks = models.PositiveIntegerField(editable=False,
        help_text='Flow sensor ticks, never changed once recorded.')
    volume_ml = models.FloatField(editable=False,
        help_text='Calculated (or set) Drink volume.')
    time = models.DateTimeField(editable=False,
      help_text='Date and time of pour.')
    duration = models.PositiveIntegerField(blank=True, default=0, editable=False,
        help_text='Time in seconds taken to pour this Drink.')
    user = models.ForeignKey(User, null=True, blank=True, related_name='drinks',
        editable=False,
        help_text='User responsible for this Drink, or None if anonymous/unknown.')
    keg = models.ForeignKey(Keg, null=True, blank=True, related_name='drinks',
        on_delete=models.PROTECT, editable=False,
        help_text='Keg against which this Drink is accounted.')
    session = models.ForeignKey('DrinkingSession',
        related_name='drinks', null=True, blank=True, editable=False,
        on_delete=models.PROTECT,
        help_text='Session where this Drink is grouped.')
    shout = models.TextField(blank=True, null=True,
        help_text='Comment from the drinker at the time of the pour.')
    tick_time_series = models.TextField(blank=True, null=True, editable=False,
        help_text='Tick update sequence that generated this drink (diagnostic data).')
    picture = models.OneToOneField('Picture', blank=True, null=True,
        on_delete=models.SET_NULL,
        help_text='Picture snapped with this drink.')

    def get_absolute_url(self):
        return reverse('kb-drink', args=(str(self.id),))

    def short_url(self):
        return '%s%s' % (SiteSettings.get().base_url(), reverse('kb-drink-short', args=(str(self.id),)))

    def Volume(self):
        return units.Quantity(self.volume_ml)

    def calories(self):
        if not self.keg or not self.keg.type:
            return 0
        ounces = self.Volume().InOunces()
        return self.keg.type.calories_oz * ounces

    def __str__(self):
        return "Drink %i by %s" % (self.id, self.user)


class AuthenticationToken(models.Model):
    """A secret token to authenticate a user, optionally pin-protected."""
    class Meta:
        unique_together = ('auth_device', 'token_value')

    auth_device = models.CharField(max_length=64,
        help_text='Namespace for this token.')
    token_value = models.CharField(max_length=128,
        help_text='Actual value of the token, unique within an auth_device.')
    nice_name = models.CharField(max_length=256, blank=True, null=True,
        help_text='A human-readable alias for the token, for example "Guest Key".')
    pin = models.CharField(max_length=256, blank=True, null=True,
        help_text='A secret value necessary to authenticate with this token.')
    user = models.ForeignKey(User, blank=True, null=True,
        related_name='tokens',
        help_text='User in possession of and authenticated by this token.')
    enabled = models.BooleanField(default=True,
        help_text='Whether this token is considered active.')
    created_time = models.DateTimeField(auto_now_add=True,
        help_text='Date token was first added to the system.')
    expire_time = models.DateTimeField(blank=True, null=True,
        help_text='Date after which token is treated as disabled.')

    def __str__(self):
        auth_device = self.auth_device
        if auth_device == 'core.rfid':
            auth_device = 'RFID'
        elif auth_device == 'core.onewire':
            auth_device = 'OneWire'

        ret = "%s %s" % (auth_device, self.token_value)
        if self.nice_name:
            ret += " (%s)" % self.nice_name
        return ret

    def get_auth_device(self):
        auth_device = self.auth_device
        if auth_device == 'core.rfid':
            auth_device = 'RFID'
        elif auth_device == 'core.onewire':
            auth_device = 'OneWire'
        return auth_device

    def IsAssigned(self):
        return self.user is not None

    def IsActive(self):
        if not self.enabled:
            return False
        if not self.expire_time:
            return True
        return timezone.now() < self.expire_time

def _auth_token_pre_save(sender, instance, **kwargs):
    if instance.auth_device in kb_common.AUTH_MODULE_NAMES_HEX_VALUES:
        instance.token_value = instance.token_value.lower()

pre_save.connect(_auth_token_pre_save, sender=AuthenticationToken)

class _AbstractChunk(models.Model):
    class Meta:
        abstract = True
        get_latest_by = 'start_time'
        ordering = ('-start_time',)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    volume_ml = models.FloatField(default=0)

    def Duration(self):
        return self.end_time - self.start_time

    def _AddDrinkNoSave(self, drink):
        session_delta = SiteSettings.get().GetSessionTimeoutDelta()
        session_end = drink.time + session_delta

        if self.start_time > drink.time:
            self.start_time = drink.time
        if self.end_time < session_end:
            self.end_time = session_end
        self.volume_ml += drink.volume_ml

    def AddDrink(self, drink):
        self._AddDrinkNoSave(drink)
        self.save()


class DrinkingSession(_AbstractChunk):
    """A collection of contiguous drinks. """
    class Meta:
        get_latest_by = 'start_time'
        ordering = ('-start_time',)

    objects = managers.SessionManager()
    name = models.CharField(max_length=256, blank=True, null=True)

    def __str__(self):
        return "Session #%s: %s" % (self.id, self.start_time)

    def short_url(self):
        return '%s%s' % (SiteSettings.get().base_url(), reverse('kb-session-short',
            args=(str(self.id),)))

    def full_url(self):
        return '%s%s' % (SiteSettings.get().base_url(), self.get_absolute_url())

    def get_highlighted_picture(self):
        pictures = self.pictures.all().order_by('-time')
        if pictures:
            return pictures[0]
        chunks = self.user_chunks.filter(user__ne=None).order_by('-volume_ml')
        if chunks:
            return chunks[0].user.mugshot

    def get_non_highlighted_pictures(self):
        pictures = self.pictures.all().order_by('-time')
        if pictures:
            return pictures[1:]
        return []

    def get_absolute_url(self):
        dt = timezone.localtime(self.start_time)
        return reverse('kb-session-detail', args=(), kwargs={
          'year' : dt.year,
          'month' : dt.month,
          'day' : dt.day,
          'pk' : self.pk})

    def GetStatsRecord(self):
        qs = SessionStats.objects.filter(session=self).order_by('-id')
        if len(qs):
            return qs[0]
        return None

    def GetStats(self):
        ret = {}
        record = self.GetStatsRecord()
        if record:
            ret = record.stats
        return util.AttrDict(ret)

    def summarize_drinkers(self):
        def fmt(user):
            url = '/drinkers/%s/' % (user.username,)
            return '<a href="%s">%s</a>' % (url, user.username)
        chunks = self.user_chunks.all().order_by('-volume_ml')
        users = tuple(c.user for c in chunks)
        names = tuple(fmt(u) for u in users if u)

        if None in users:
            guest_trailer = ' (and possibly others)'
        else:
            guest_trailer = ''

        num = len(names)
        if num == 0:
            return 'no known drinkers'
        elif num == 1:
            ret = names[0]
        elif num == 2:
            ret = '%s and %s' % names
        elif num == 3:
            ret = '%s, %s and %s' % names
        else:
            if guest_trailer:
                return '%s, %s and at least %i others' % (names[0], names[1], num-2)
            else:
                return '%s, %s and %i others' % (names[0], names[1], num-2)

        return '%s%s' % (ret, guest_trailer)

    def GetTitle(self):
        if self.name:
            return self.name
        else:
            if self.id:
                return 'Session %s' % (self.id,)
            else:
                # Not yet saved.
                return 'New Session'

    def AddDrink(self, drink):
        super(DrinkingSession, self).AddDrink(drink)
        session_delta = SiteSettings.get().GetSessionTimeoutDelta()

        defaults = {
          'start_time': drink.time,
          'end_time': drink.time + session_delta,
        }

        # Update or create a SessionChunk.
        chunk, created = SessionChunk.objects.get_or_create(session=self,
            user=drink.user, keg=drink.keg, defaults=defaults)
        chunk.AddDrink(drink)

        # Update or create a UserSessionChunk.
        chunk, created = UserSessionChunk.objects.get_or_create(session=self,
            user=drink.user, defaults=defaults)
        chunk.AddDrink(drink)

        # Update or create a KegSessionChunk.
        chunk, created = KegSessionChunk.objects.get_or_create(session=self,
            keg=drink.keg, defaults=defaults)
        chunk.AddDrink(drink)

    def UserChunksByVolume(self):
        chunks = self.user_chunks.all().order_by('-volume_ml')
        return chunks

    def IsActiveNow(self):
        return self.IsActive(timezone.now())

    def IsActive(self, now):
        return self.end_time > now

    def Rebuild(self):
        """Recomputes start and end time, and chunks, based on current drinks.

        This method should be called after changing the set of drinks
        belonging to this session.

        This method has no effect on statistics; see stats module.
        """
        self.volume_ml = 0
        self.chunks.all().delete()
        self.user_chunks.all().delete()
        self.keg_chunks.all().delete()

        drinks = self.drinks.all()
        if not drinks:
            self.delete()
            return

        session_delta = SiteSettings.get().GetSessionTimeoutDelta()
        min_time = None
        max_time = None
        for d in drinks:
            self.AddDrink(d)
            if min_time is None or d.time < min_time:
                min_time = d.time
            if max_time is None or d.time > max_time:
                max_time = d.time
        self.start_time = min_time
        self.end_time = max_time + session_delta
        self.save()

    @classmethod
    def AssignSessionForDrink(cls, drink):
        # Return existing session if already assigned.
        if drink.session:
            return drink.session

        # Return last session if one already exists
        q = DrinkingSession.objects.all().order_by('-end_time')[:1]
        if q and q[0].IsActive(drink.time):
            session = q[0]
            session.AddDrink(drink)
            drink.session = session
            drink.save()
            return session

        # Create a new session
        session = cls(start_time=drink.time, end_time=drink.time)
        session.save()
        session.AddDrink(drink)
        drink.session = session
        drink.save()
        return session


class SessionChunk(_AbstractChunk):
    """A specific user and keg contribution to a session."""
    class Meta:
        unique_together = ('session', 'user', 'keg')
        get_latest_by = 'start_time'
        ordering = ('-start_time',)

    session = models.ForeignKey(DrinkingSession, related_name='chunks')
    user = models.ForeignKey(User, related_name='session_chunks', blank=True,
        null=True)
    keg = models.ForeignKey(Keg, related_name='session_chunks', blank=True,
        null=True, on_delete=models.PROTECT)


class UserSessionChunk(_AbstractChunk):
    """A specific user's contribution to a session (spans all kegs)."""
    class Meta:
        unique_together = ('session', 'user')
        get_latest_by = 'start_time'
        ordering = ('-start_time',)

    session = models.ForeignKey(DrinkingSession, related_name='user_chunks')
    user = models.ForeignKey(User, related_name='user_session_chunks', blank=True,
        null=True)

    def GetTitle(self):
        return self.session.GetTitle()

    def GetDrinks(self):
        return self.session.drinks.filter(user=self.user).order_by('time')


class KegSessionChunk(_AbstractChunk):
    """A specific keg's contribution to a session (spans all users)."""
    class Meta:
        unique_together = ('session', 'keg')
        get_latest_by = 'start_time'
        ordering = ('-start_time',)

    objects = managers.SessionManager()
    session = models.ForeignKey(DrinkingSession, related_name='keg_chunks')
    keg = models.ForeignKey(Keg, related_name='keg_session_chunks', blank=True,
        null=True)

    def GetTitle(self):
        return self.session.GetTitle()


class ThermoSensor(models.Model):
    raw_name = models.CharField(max_length=256)
    nice_name = models.CharField(max_length=128)

    def __str__(self):
        if self.nice_name:
            return '%s (%s)' % (self.nice_name, self.raw_name)
        return self.raw_name

    def LastLog(self):
        try:
            return self.thermolog_set.latest()
        except Thermolog.DoesNotExist:
            return None


class Thermolog(models.Model):
    """ A log from an ITemperatureSensor device of periodic measurements. """
    class Meta:
        get_latest_by = 'time'
        ordering = ('-time',)

    sensor = models.ForeignKey(ThermoSensor)
    temp = models.FloatField()
    time = models.DateTimeField()

    def __str__(self):
        return '%s %.2f C / %.2f F [%s]' % (self.sensor, self.TempC(),
            self.TempF(), self.time)

    def TempC(self):
        return self.temp

    def TempF(self):
        return util.CtoF(self.temp)


class _StatsModel(models.Model):
    time = models.DateTimeField(default=timezone.now)
    stats = jsonfield.JSONField()
    drink = models.ForeignKey(Drink)

    class Meta:
        abstract = True
        get_latest_by = 'id'


class SystemStats(_StatsModel):
    pass

class UserStats(_StatsModel):
    user = models.ForeignKey(User, blank=True, null=True,
        related_name='stats')

    class Meta:
        unique_together = ('drink', 'user')

    def __str__(self):
        return 'UserStats for %s' % self.user


class KegStats(_StatsModel):
    keg = models.ForeignKey(Keg, related_name='stats')
    completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('drink', 'keg')

    def __str__(self):
        return 'KegStats for %s' % self.keg


class SessionStats(_StatsModel):
    session = models.ForeignKey(DrinkingSession, related_name='stats')
    completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ('drink', 'session')

    def __str__(self):
        return 'SessionStats for %s' % self.session


class SystemEvent(models.Model):
    class Meta:
        ordering = ('-id',)
        get_latest_by = 'time'

    DRINK_POURED = 'drink_poured'
    SESSION_STARTED = 'session_started'
    SESSION_JOINED = 'session_joined'
    KEG_TAPPED = 'keg_tapped'
    KEG_VOLUME_LOW = 'keg_volume_low'
    KEG_ENDED = 'keg_ended'

    KINDS = (
        (DRINK_POURED, 'Drink poured'),
        (SESSION_STARTED, 'Session started'),
        (SESSION_JOINED, 'User joined session'),
        (KEG_TAPPED, 'Keg tapped'),
        (KEG_VOLUME_LOW, 'Keg volume low'),
        (KEG_ENDED, 'Keg ended'),
    )

    kind = models.CharField(max_length=255, choices=KINDS,
        help_text='Type of event.')
    time = models.DateTimeField(help_text='Time of the event.')
    user = models.ForeignKey(User, blank=True, null=True,
        related_name='events',
        help_text='User responsible for the event, if any.')
    drink = models.ForeignKey(Drink, blank=True, null=True,
        related_name='events',
        help_text='Drink involved in the event, if any.')
    keg = models.ForeignKey(Keg, blank=True, null=True,
        related_name='events',
        help_text='Keg involved in the event, if any.')
    session = models.ForeignKey(DrinkingSession, blank=True, null=True,
        related_name='events',
        help_text='Session involved in the event, if any.')

    objects = managers.SystemEventManager()

    def __str__(self):
        if self.kind == self.DRINK_POURED:
            ret = 'Drink %i poured' % self.drink.id
        elif self.kind == self.SESSION_STARTED:
            ret = 'Session %s started by drink %s' % (self.session.id,
                self.drink.id)
        elif self.kind == self.SESSION_JOINED:
            ret = 'Session %s joined by %s (drink %s)' % (self.session.id,
                self.user.username, self.drink.id)
        elif self.kind == self.KEG_TAPPED:
            ret = 'Keg %s tapped' % self.keg.id
        elif self.kind == self.KEG_VOLUME_LOW:
            ret = 'Keg %s volume low' % self.keg.id
        elif self.kind == self.KEG_ENDED:
            ret = 'Keg %s ended' % self.keg.id
        else:
            ret = 'Unknown event type (%s)' % self.kind
        return 'Event %s: %s' % (self.id, ret)

    @classmethod
    def build_events_for_keg(cls, keg):
        '''Generates and returns system events for the keg.'''
        events = []
        if keg.online:
            q = keg.events.filter(kind=cls.KEG_TAPPED)
            if q.count() == 0:
                e = keg.events.create(kind=cls.KEG_TAPPED, time=keg.start_time, keg=keg)
                e.save()
                events.append(e)

        if not keg.online:
            q = keg.events.filter(kind=cls.KEG_ENDED)
            if q.count() == 0:
                e = keg.events.create(kind=cls.KEG_ENDED, time=keg.end_time, keg=keg)
                e.save()
                events.append(e)
        
        return events

    @classmethod
    def build_events_for_drink(cls, drink):
        keg = drink.keg
        session = drink.session
        user = drink.user

        events = []

        if session:
            q = session.events.filter(kind=cls.SESSION_STARTED)
            if q.count() == 0:
                e = session.events.create(kind=cls.SESSION_STARTED,
                    time=session.start_time, drink=drink, user=user)
                e.save()
                events.append(e)

        if user:
            q = user.events.filter(kind=cls.SESSION_JOINED, session=session)
            if q.count() == 0:
                e = user.events.create(kind=cls.SESSION_JOINED,
                    time=drink.time, session=session, drink=drink, user=user)
                e.save()
                events.append(e)

        e = drink.events.create(kind=cls.DRINK_POURED,
            time=drink.time, drink=drink, user=user, keg=keg,
            session=session)
        e.save()
        events.append(e)

        if keg:
            volume_now = keg.remaining_volume_ml()
            volume_before = volume_now + drink.volume_ml
            threshold = keg.full_volume_ml * kb_common.KEG_VOLUME_LOW_PERCENT

            if volume_now <= threshold and volume_before > threshold:
                e = drink.events.create(kind=cls.KEG_VOLUME_LOW,
                    time=drink.time, drink=drink, user=user, keg=keg,
                    session=session)
                e.save()
                events.append(e)

        return events


def _pics_file_name(instance, filename):
    rand_salt = random.randrange(0xffff)
    new_filename = '%04x-%s' % (rand_salt, filename)
    return os.path.join('pics', new_filename)

class Picture(models.Model):
    image = models.ImageField(upload_to=_pics_file_name,
        help_text='The image')
    resized = ImageSpecField(source='image',
        processors=[resize.ResizeToFit(1024, 1024)],
        format='JPEG',
        options={'quality': 100})
    small_resized = ImageSpecField(source='image',
        processors=[resize.ResizeToFit(256, 256)],
        format='JPEG',
        options={'quality': 100})
    thumbnail = ImageSpecField(source='image',
        processors=[Adjust(contrast=1.2, sharpness=1.1), resize.SmartResize(128, 128)],
        format='JPEG',
        options={'quality': 90})
    small_thumbnail = ImageSpecField(source='image',
        processors=[Adjust(contrast=1.2, sharpness=1.1), resize.SmartResize(32, 32)],
        format='JPEG',
        options={'quality': 90})

    time = models.DateTimeField(default=timezone.now,
        help_text='Time/date of image capture')
    caption = models.TextField(blank=True, null=True,
        help_text='Caption for the picture, if any.')
    user = models.ForeignKey(User, blank=True, null=True,
        related_name='pictures',
        help_text='User that owns/uploaded this picture')
    keg = models.ForeignKey(Keg, blank=True, null=True,
        related_name='pictures',
        on_delete=models.SET_NULL,
        help_text='Keg this picture was taken with, if any.')
    session = models.ForeignKey(DrinkingSession, blank=True, null=True,
        related_name='pictures',
        on_delete=models.SET_NULL,
        help_text='Session this picture was taken with, if any.')

    def __str__(self):
        return 'Picture: %s' % self.image

    def get_caption(self):
        if self.caption:
            return self.caption
        elif self.drink:
            if self.user:
                return '%s pouring drink %s' % (self.user.username, self.drink.id)
            else:
                return 'An unknown drinker pouring drink %s' % (self.drink.id,)
        return ''

