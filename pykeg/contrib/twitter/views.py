# Copyright 2013 Mike Wakerly <opensource@hoho.com>
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

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from socialregistration.clients.oauth import OAuthError
from socialregistration.contrib.twitter.client import Twitter
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.shortcuts import render_to_response
from django.template import RequestContext

from httplib2 import HttpLib2Error

from . import forms


@staff_member_required
def admin_settings(request, plugin):
    context = RequestContext(request)

    consumer_key, consumer_secret = plugin.get_credentials()
    initial = {
      'consumer_key': consumer_key or '',
      'consumer_secret': consumer_secret or '',
    }

    credentials_form = forms.CredentialsForm(initial=initial)
    settings_form = forms.SiteSettingsForm()
    plugin.load_form_defaults(settings_form, 'site_settings')

    if request.method == 'POST':
        if 'submit-keys' in request.POST:
            credentials_form = forms.CredentialsForm(request.POST)
            if credentials_form.is_valid():
                consumer_key = credentials_form.cleaned_data['consumer_key']
                consumer_secret = credentials_form.cleaned_data['consumer_secret']
                plugin.set_credentials(consumer_key, consumer_secret)
                messages.success(request, 'Keys updated')

        elif 'submit-settings' in request.POST:
            settings_form = forms.SiteSettingsForm(request.POST)
            if settings_form.is_valid():
                plugin.save_form(settings_form, 'site_settings')
                messages.success(request, 'Settings updated')

    context['have_credentials'] = consumer_key and consumer_secret
    context['plugin'] = plugin
    context['site_profile'] = plugin.get_site_profile()
    context['credentials_form'] = credentials_form
    context['settings_form'] = settings_form

    return render_to_response('contrib/twitter/admin_settings.html', context_instance=context)


@login_required
def user_settings(request, plugin):
    context = RequestContext(request)
    user = request.user

    consumer_key, consumer_secret = plugin.get_credentials()

    settings_form = plugin.get_user_settings_form(user)

    if request.method == 'POST':
        if 'submit-settings' in request.POST:
            settings_form = forms.UserSettingsForm(request.POST)
            if settings_form.is_valid():
                plugin.save_user_settings_form(user, settings_form)
                messages.success(request, 'Settings updated')

    context['have_credentials'] = consumer_key and consumer_secret
    context['plugin'] = plugin
    context['profile'] = plugin.get_user_profile(user)
    context['settings_form'] = settings_form

    return render_to_response('contrib/twitter/twitter_user_settings.html', context_instance=context)


@staff_member_required
def site_twitter_redirect(request):
    if 'submit-remove' in request.POST:
        plugin = request.plugins.get('twitter')
        plugin.remove_site_profile()
        messages.success(request, 'Removed Twitter account.')
        return redirect('kegadmin-plugin-settings', plugin_name='twitter')

    plugin = request.plugins['twitter']

    client = plugin.get_client()
    url = request.kbsite.settings.reverse_full('plugin-twitter-site_twitter_callback')
    client.set_callback_url(url)

    return do_redirect(request, client, 'kegadmin-plugin-settings')


@staff_member_required
def site_twitter_callback(request):
    plugin = request.plugins.get('twitter')
    client = plugin.get_client()

    try:
        token = client.complete(dict(request.GET.items()))
    except KeyError:
        messages.error(request, 'Session expired.')
    except OAuthError, error:
        messages.error(request, str(error))
    else:
        user_info = client.get_user_info()
        plugin = request.plugins.get('twitter')
        plugin.save_site_profile(token.key, token.secret, user_info['screen_name'],
            int(user_info['user_id']))
        messages.success(request, 'Successfully linked to @%s' % user_info['screen_name'])

    return redirect('kegadmin-plugin-settings', plugin_name='twitter')


@login_required
def user_twitter_redirect(request):
    if 'submit-remove' in request.POST:
        plugin = request.plugins.get('twitter')
        plugin.remove_user_profile(request.user)
        messages.success(request, 'Removed Twitter account.')
        return redirect('account-plugin-settings', plugin_name='twitter')

    plugin = request.plugins['twitter']
    client = plugin.get_client()
    url = request.kbsite.settings.reverse_full('plugin-twitter-user_twitter_callback')
    client.set_callback_url(url)

    return do_redirect(request, client, 'account-plugin-settings')


@login_required
def user_twitter_callback(request):
    plugin = request.plugins['twitter']
    client = plugin.get_client()

    try:
        token = client.complete(dict(request.GET.items()))
    except KeyError:
        messages.error(request, 'Session expired.')
    except OAuthError, error:
        messages.error(request, str(error))
    else:
        user_info = client.get_user_info()
        plugin = request.plugins.get('twitter')
        plugin.save_user_profile(request.user, token.key, token.secret,
            user_info['screen_name'], int(user_info['user_id']))
        messages.success(request, 'Successfully linked to @%s' % user_info['screen_name'])

    return redirect('account-plugin-settings', plugin_name='twitter')


def do_redirect(request, client, next_url_name):
    """Common redirect method, handling any incidental errors.

    Args:
        request: the incoming request
        client: the TwitterClient context_instance
        next_url_name: Django URL name to redirect to upon error

    Returns:
        A redirect response, either to the OAuth redirect URL
        or to `next_url_name` on error.
    """
    try:
        return redirect(client.get_redirect_url())
    except OAuthError, e:
        messages.error(request, 'Error: %s' % str(e))
        return redirect(next_url_name, plugin_name='twitter')
    except HttpLib2Error, e:
        # This path can occur when api.twitter.com is unresolvable
        # or unreachable.
        messages.error(request, 'Twitter API server not available. Try again later. (%s)' % str(e))
        return redirect(next_url_name, plugin_name='twitter')

