from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Submit, HTML, Button, Row, Field, Hidden, Div
from crispy_forms.bootstrap import AppendedText, PrependedText, FormActions

from kegbot.util import units
from pykeg.core import backend
from pykeg.core import keg_sizes
from pykeg.core import models

ALL_TAPS = models.KegTap.objects.all()
ALL_KEGS = models.Keg.objects.all()

class GeneralSettingsForm(forms.Form):
    name = forms.CharField(help_text='Name of this Kegbot system')

class ChangeKegForm(forms.Form):
    keg_size = forms.ChoiceField(choices=keg_sizes.CHOICES,
        initial=keg_sizes.HALF_BARREL,
        required=True)

    beverage_name = forms.CharField(required=True, label='Beer Name')
    beverage_id = forms.CharField(widget=forms.HiddenInput(), required=False)
    producer_name = forms.CharField(required=True, label='Brewer')
    producer_id = forms.CharField(widget=forms.HiddenInput(), required=False)
    style = forms.CharField(required=True, label='Style',
      help_text='Example: Pale Ale, Stout, etc.')

    helper = FormHelper()
    helper.form_class = 'form-horizontal beer-select'
    helper.layout = Layout(
        Field('beverage_name', css_class='input-xlarge'),
        Field('beverage_id', type='hidden'),
        Field('producer_name', css_class='input-xlarge'),
        Field('producer_id', type='hidden'),
        Field('style', css_class='input-xlarge'),
        Field('keg_size', css_class='input-xlarge'),
        FormActions(
            Submit('submit_change_keg_form', 'Activate Keg', css_class='btn-primary'),
        )
    )

    def save(self, tap):
        if not self.is_valid():
            raise ValueError('Form is not valid.')
        b = backend.KegbotBackend()

        if tap.is_active():
            b.end_keg(tap)

        # TODO(mikey): Support non-beer beverage types.
        cd = self.cleaned_data
        keg = b.start_keg(tap, beverage_name=cd['beverage_name'], producer_name=cd['producer_name'],
            beverage_type='beer', style_name=cd['style'], keg_type=cd['keg_size'])

        if cd.get('description'):
            keg.description = cd['description']
            keg.save()


class EndKegForm(forms.Form):
    keg = forms.ModelChoiceField(queryset=ALL_KEGS, widget=forms.HiddenInput)

    helper = FormHelper()
    helper.form_class = 'form-horizontal beer-select'
    helper.layout = Layout(
        Field('keg', type='hidden'),
        FormActions(
          Submit('submit_end_keg_form', 'End Keg', css_class='btn-danger'),
        )
    )


class TapForm(forms.ModelForm):
    class Meta:
        model = models.KegTap
        fields = ('name', 'meter_name', 'relay_name', 'description',
            'temperature_sensor', 'ml_per_tick')

    def __init__(self, *args, **kwargs):
        site = kwargs.pop('site', None)
        super(TapForm, self).__init__(*args, **kwargs)
        self.fields['temperature_sensor'].queryset = models.ThermoSensor.objects.all()
        self.fields['temperature_sensor'].empty_label = 'No sensor.'

    helper = FormHelper()
    helper.form_class = 'form-horizontal'
    helper.layout = Layout(
        Field('name', css_class='input-xlarge'),
        Field('meter_name', css_class='input-xlarge'),
        Field('relay_name', css_class='input-xlarge'),
        Field('temperature_sensor', css_class='input-xlarge'),
        Field('ml_per_tick', css_class='input-xlarge'),
        Field('description', css_class='input-xlarge'),
        FormActions(
            Submit('submit_tap_form', 'Save Settings', css_class='btn-success'),
        )
    )


class DeleteTapForm(forms.Form):
    helper = FormHelper()
    helper.form_class = 'form-horizontal'
    helper.layout = Layout(
        FormActions(
            Submit('submit_delete_tap_form', 'Delete Tap', css_class='btn-danger'),
        )
    )


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = models.SiteSettings
        fields = (
            'title',
            'privacy',
            'volume_display_units',
            'temperature_display_units',
            'timezone',
            'hostname',
            'use_ssl',
            'session_timeout_minutes',
            'google_analytics_id',
            'guest_name',
            'guest_image',
            'default_user',
            'registration_allowed',
            'registration_confirmation',
            'allowed_hosts',
        )

    helper = FormHelper()
    helper.form_class = 'form-horizontal'
    helper.layout = Layout(
        Field('title', css_class='input-xlarge'),
        Field('privacy', css_class='input-xlarge'),
        Field('volume_display_units', css_class='input-xlarge'),
        Field('temperature_display_units', css_class='input-xlarge'),
        Field('timezone'),
        Field('hostname'),
        Field('use_ssl'),
        Field('session_timeout_minutes'),
        Field('google_analytics_id'),
        Field('guest_name'),
        Field('guest_image'),
        Field('default_user'),
        Field('registration_allowed', css_class='input-xlarge'),
        Field('registration_confirmation', css_class='input-xlarge'),
        Field('allowed_hosts'),
        FormActions(
            Submit('submit', 'Save Settings', css_class='btn-primary'),
        )
    )

class BeverageForm(forms.ModelForm):
    class Meta:
        model = models.Beverage
        fields = ('name', 'style', 'producer', 'vintage_year', 'abv_percent',
            'original_gravity', 'specific_gravity',
            'untappd_beer_id')

    new_image = forms.ImageField(required=False,
        help_text='Set/replace image for this beer type.')

    helper = FormHelper()
    helper.form_class = 'form-horizontal'
    helper.layout = Layout(
        Field('name', css_class='input-xlarge'),
        Field('style', css_class='input-xlarge'),
        Field('producer'),
        Field('edition_year'),
        Field('abv_percent'),
        Field('untappd_beer_id'),
        Field('new_image'),
        FormActions(
            Submit('submit', 'Save', css_class='btn-primary'),
        )
    )

class BeverageProducerForm(forms.ModelForm):
    class Meta:
        model = models.BeverageProducer

    helper = FormHelper()
    helper.form_class = 'form-horizontal'
    helper.layout = Layout(
        Field('name', css_class='input-xlarge'),
        Field('country', css_class='input-xlarge'),
        Field('origin_state', css_class='input-xlarge'),
        Field('origin_city', css_class='input-xlarge'),
        Field('is_homebrew'),
        Field('url'),
        Field('description'),
        FormActions(
            Submit('submit', 'Save', css_class='btn-primary'),
        )
    )

class FindUserForm(forms.Form):
    username = forms.CharField()

class UserForm(forms.ModelForm):
    class Meta:
        model = models.User
        fields = (
            'username',
            'email',
            'password',
            'is_staff',
        )

    helper = FormHelper()
    helper.form_class = 'form-horizontal'
    helper.layout = Layout(
        Field('username', css_class='input-xlarge'),
        Field('email', css_class='input-xlarge'),
        'password',
        'is_staff',
        FormActions(
            Submit('submit', 'Save', css_class='btn-primary'),
        )
    )

class TokenForm(forms.ModelForm):
    class Meta:
        model = models.AuthenticationToken
        fields = (
            'nice_name',
            'enabled',
        )
    username = forms.CharField(required=False)

    helper = FormHelper()
    helper.form_class = 'form-horizontal user-select'
    helper.layout = Layout(
        Field('username', css_class='input-xlarge'),
        Field('nice_name', css_class='input-xlarge'),
        'enabled',
        FormActions(
            Submit('submit', 'Save', css_class='btn-primary'),
        )
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if username == '':
            self.cleaned_data['user'] = None
            return
        try:
            self.cleaned_data['user'] = models.User.objects.get(username=username)
        except models.User.DoesNotExist:
            raise forms.ValidationError('Invalid username; use a complete user name or leave blank.')
        return username


class AddTokenForm(forms.ModelForm):
    class Meta:
        model = models.AuthenticationToken
        fields = (
            'auth_device',
            'token_value',
            'enabled',
        )
    CHOICES = (
      ('core.rfid', 'RFID'),
      ('core.onewire', 'OneWire/iButton'),
      ('nfc', 'NFC'),
    )
    auth_device = forms.ChoiceField(choices=CHOICES)
    username = forms.CharField(required=False)

    helper = FormHelper()
    helper.form_class = 'form-horizontal user-select'
    helper.layout = Layout(
        Field('auth_device', css_class='input-xlarge'),
        Field('token_value', css_class='input-xlarge'),
        Field('username', css_class='input-xlarge'),
        'enabled',
        FormActions(
            Submit('submit', 'Save', css_class='btn-primary'),
        )
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if username == '':
            self.cleaned_data['user'] = None
            return
        try:
            self.cleaned_data['user'] = models.User.objects.get(username=username)
        except models.User.DoesNotExist:
            raise forms.ValidationError('Invalid username; use a complete user name or leave blank.')
        return username


class CancelDrinkForm(forms.Form):
    pass

class ReassignDrinkForm(forms.Form):
    username = forms.CharField(required=False)

class ChangeDrinkVolumeForm(forms.Form):
    UNIT_CHOICES = (
      ('mL', 'mL'),
      ('oz', 'oz')
    )
    units = forms.ChoiceField(required=True, choices=UNIT_CHOICES)
    volume = forms.FloatField(required=True, min_value=0)

    def clean_volume(self):
        volume = self.cleaned_data['volume']
        if self.cleaned_data['units'] == 'oz':
            self.cleaned_data['volume_ml'] = float(units.Quantity(volume, units.UNITS.Ounce).InMilliliters())
        else:
            self.cleaned_data['volume_ml'] = volume
        return volume

class RecordDrinkForm(forms.Form):
    units = forms.ChoiceField(required=True, choices=ChangeDrinkVolumeForm.UNIT_CHOICES)
    volume = forms.FloatField(required=True, min_value=0)
    username = forms.CharField(required=False)

    def clean_username(self):
        username = self.cleaned_data['username']
        if username == '':
            self.cleaned_data['user'] = None
            return
        try:
            self.cleaned_data['user'] = models.User.objects.get(username=username)
        except models.User.DoesNotExist:
            raise forms.ValidationError('Invalid username; use a complete user name or leave blank.')
        return username

    def clean_volume(self):
        volume = self.cleaned_data['volume']
        if self.cleaned_data['units'] == 'oz':
            self.cleaned_data['volume_ml'] = float(units.Quantity(volume, units.UNITS.Ounce).InMilliliters())
        else:
            self.cleaned_data['volume_ml'] = volume
        return volume
