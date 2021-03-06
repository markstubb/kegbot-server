#!/usr/bin/env python
#
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

import cStringIO
import datetime

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import Http404
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.forms import widgets
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.http import require_http_methods

from kegbot.util import kbjson
from kegbot.util import units

from pykeg.core import backend
from pykeg.core import logger
from pykeg.core import models

from pykeg.web.kegadmin import forms

@staff_member_required
def dashboard(request):
    context = RequestContext(request)
    recent_time = timezone.now() - datetime.timedelta(days=30)
    active_users = models.User.objects.filter(is_active=True)
    new_users = models.User.objects.filter(date_joined__gte=recent_time)
    context['num_users'] = len(active_users)
    context['num_new_users'] = len(new_users)
    return render_to_response('kegadmin/dashboard.html', context_instance=context)

@staff_member_required
def general_settings(request):
    context = RequestContext(request)
    settings = models.SiteSettings.get()
    form = forms.SiteSettingsForm(instance=settings)
    if request.method == 'POST':
        form = forms.SiteSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Site settings were successfully updated.')
    context['settings_form'] = form
    return render_to_response('kegadmin/index.html', context_instance=context)

@staff_member_required
def tap_list(request):
    context = RequestContext(request)
    context['taps'] = models.KegTap.objects.all()
    return render_to_response('kegadmin/tap_list.html', context_instance=context)

@staff_member_required
def add_tap(request):
    context = RequestContext(request)
    form = forms.TapForm(site=request.kbsite)
    if request.method == 'POST':
        form = forms.TapForm(request.POST, site=request.kbsite)
        if form.is_valid():
            new_tap = form.save(commit=False)
            new_tap.site = request.kbsite
            new_tap.save()
            messages.success(request, 'Tap created.')
            return redirect('kegadmin-taps')
    context['form'] = form
    return render_to_response('kegadmin/add_tap.html', context_instance=context)

@staff_member_required
def tap_detail(request, tap_id):
    tap = get_object_or_404(models.KegTap, id=tap_id)

    record_drink_form = forms.RecordDrinkForm()
    activate_keg_form = forms.ChangeKegForm()
    tap_settings_form = forms.TapForm(instance=tap, site=request.kbsite)

    if request.method == 'POST':
        if 'submit_change_keg_form' in request.POST:
            activate_keg_form = forms.ChangeKegForm(request.POST)
            if activate_keg_form.is_valid():
                activate_keg_form.save(tap)
                messages.success(request, 'The new keg was activated. Bottoms up!')
                return redirect('kegadmin-taps')

        elif 'submit_tap_form' in request.POST:
            tap_settings_form = forms.TapForm(request.POST, instance=tap, site=request.kbsite)
            if tap_settings_form.is_valid():
                tap_settings_form.save()
                messages.success(request, 'Tap settings saved.')
                tap_settings_form = forms.TapForm(instance=tap, site=request.kbsite)

        elif 'submit_delete_tap_form' in request.POST:
            delete_form = forms.DeleteTapForm(request.POST)
            if delete_form.is_valid():
                if tap.current_keg:
                    request.backend.end_keg(tap)
                tap.delete()
                messages.success(request, 'Tap deleted.')
                return redirect('kegadmin-taps')

        elif 'submit_end_keg_form' in request.POST:
            end_keg_form = forms.EndKegForm(request.POST)
            if end_keg_form.is_valid():
                old_keg = request.backend.end_keg(tap)
                messages.success(request, 'Keg %s was ended.' % old_keg.id)

        elif 'submit_record_drink' in request.POST:
            record_drink_form = forms.RecordDrinkForm(request.POST)
            if record_drink_form.is_valid():
                user = record_drink_form.cleaned_data.get('user')
                volume_ml = record_drink_form.cleaned_data.get('volume_ml')
                d = request.backend.record_drink(tap.meter_name, ticks=0, username=user,
                    volume_ml=volume_ml)
                messages.success(request, 'Drink %s recorded.' % d.id)
            else:
                messages.error(request, 'Please enter a valid volume and user.')

        else:
            messages.warning(request, 'No form data was found. Bug?')

    end_keg_form = forms.EndKegForm(initial={'keg':tap.current_keg})

    context = RequestContext(request)
    context['tap'] = tap
    context['current_keg'] = tap.current_keg
    context['activate_keg_form'] = activate_keg_form
    context['record_drink_form'] = record_drink_form
    context['end_keg_form'] = end_keg_form
    context['tap_settings_form'] = tap_settings_form
    context['delete_tap_form'] = forms.DeleteTapForm()
    return render_to_response('kegadmin/tap_detail.html', context_instance=context)

@staff_member_required
def user_list(request):
    context = RequestContext(request)

    if request.method == 'POST':
        form = forms.FindUserForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            try:
                user = models.User.objects.get(username=username)
                return redirect('kegadmin-edit-user', user.id)
            except models.User.DoesNotExist:
                messages.error(request, 'User "%s" does not exist.' % username)

    users = models.User.objects.all().order_by('-id')
    paginator = Paginator(users, 25)

    page = request.GET.get('page')
    try:
        users = paginator.page(page)
    except PageNotAnInteger:
        users = paginator.page(1)
    except EmptyPage:
        users = paginator.page(paginator.num_pages)

    context['users'] = users
    return render_to_response('kegadmin/user_list.html', context_instance=context)

@staff_member_required
def add_user(request):
    context = RequestContext(request)
    form = forms.UserForm()
    if request.method == 'POST':
        form = forms.UserForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.set_password(form.cleaned_data.get('password'))
            instance.save()
            messages.success(request, 'User "%s" created.' % instance.username)
            return redirect('kegadmin-users')
    context['form'] = form
    return render_to_response('kegadmin/add_user.html', context_instance=context)

@staff_member_required
def user_detail(request, user_id):
    user = get_object_or_404(models.User, id=user_id)

    if request.method == 'POST':
        if 'submit_enable' in request.POST:
            if user.is_active:
                messages.error(request, 'User is already enabled.')
            else:
                user.is_active = True
                user.save()
                messages.success(request, 'User %s was enabled.' % user.username)

        elif 'submit_disable' in request.POST:
            if not user.is_active:
                messages.error(request, 'User is already disabled.')
            else:
                user.is_active = False
                user.save()
                messages.success(request, 'User %s was disabled.' % user.username)

    context = RequestContext(request)
    context['user'] = user
    context['stats'] = context['profile'].GetStats()

    context['tokens'] = user.tokens.all().order_by('created_time')

    return render_to_response('kegadmin/user_detail.html', context_instance=context)

@staff_member_required
def drink_list(request):
    context = RequestContext(request)
    drinks = models.Drink.objects.all().order_by('-time')
    paginator = Paginator(drinks, 25)

    page = request.GET.get('page')
    try:
        drinks = paginator.page(page)
    except PageNotAnInteger:
        drinks = paginator.page(1)
    except EmptyPage:
        drinks = paginator.page(paginator.num_pages)

    context['drinks'] = drinks
    return render_to_response('kegadmin/drink_list.html', context_instance=context)


@staff_member_required
@require_http_methods(["POST"])
def drink_edit(request, drink_id):
    drink = get_object_or_404(models.Drink, id=drink_id)

    if 'submit_cancel' in request.POST:
        form = forms.CancelDrinkForm(request.POST)
        old_keg = drink.keg
        if form.is_valid():
            request.backend.cancel_drink(drink)
            messages.success(request, 'Drink %s was cancelled.' % drink_id)
            return redirect(old_keg.get_absolute_url())
        else:
            messages.error(request, 'Invalid request')
            return redirect(drink.get_absolute_url())

    elif 'submit_reassign' in request.POST:
        form = forms.ReassignDrinkForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username', None)
            try:
                request.backend.assign_drink(drink, username)
                messages.success(request, 'Drink %s was reassigned.' % drink_id)
            except models.User.DoesNotExist:
                messages.error(request, 'No such user')
        else:
            messages.error(request, 'Invalid request')
        return redirect(drink.get_absolute_url())

    elif 'submit_edit_volume' in request.POST:
        form = forms.ChangeDrinkVolumeForm(request.POST)
        if form.is_valid():
            volume_ml = form.cleaned_data.get('volume_ml')
            if volume_ml == drink.volume_ml:
                messages.warning(request, 'Drink volume unchanged.')
            else:
                request.backend.set_drink_volume(drink, volume_ml)
                messages.success(request, 'Drink %s was updated.' % drink_id)
        else:
            messages.error(request, 'Please provide a valid volume.')
        return redirect(drink.get_absolute_url())

    message.error(request, 'Unknown action.')
    return redirect(drink.get_absolute_url())


@staff_member_required
def token_list(request):
    context = RequestContext(request)
    tokens = models.AuthenticationToken.objects.all().order_by('-created_time')
    paginator = Paginator(tokens, 25)

    page = request.GET.get('page')
    try:
        tokens = paginator.page(page)
    except PageNotAnInteger:
        tokens = paginator.page(1)
    except EmptyPage:
        tokens = paginator.page(paginator.num_pages)

    context['tokens'] = tokens
    return render_to_response('kegadmin/token_list.html', context_instance=context)


@staff_member_required
def token_detail(request, token_id):
    token = get_object_or_404(models.AuthenticationToken, id=token_id)

    username = ''
    if token.user:
        username = token.user.username

    form = forms.TokenForm(instance=token, initial={'username': username})
    if request.method == 'POST':
        form = forms.TokenForm(request.POST, instance=token)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.user = form.cleaned_data['user']
            instance.save()
            messages.success(request, 'Token updated.')

    context = RequestContext(request)
    context['token'] = token
    context['form'] = form
    return render_to_response('kegadmin/token_detail.html', context_instance=context)

@staff_member_required
def add_token(request):
    context = RequestContext(request)
    form = forms.AddTokenForm()
    if request.method == 'POST':
        form = forms.AddTokenForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            instance.user = form.cleaned_data['user']
            instance.site = request.kbsite
            instance.save()
            messages.success(request, 'Token created.')
            return redirect('kegadmin-tokens')
    context['form'] = form
    return render_to_response('kegadmin/add_token.html', context_instance=context)


@staff_member_required
def beverages_list(request):
    context = RequestContext(request)
    beers = models.Beverage.objects.all().order_by('name')
    paginator = Paginator(beers, 25)

    page = request.GET.get('page')
    try:
        beers = paginator.page(page)
    except PageNotAnInteger:
        beers = paginator.page(1)
    except EmptyPage:
        beers = paginator.page(paginator.num_pages)

    context['beverages'] = beers
    return render_to_response('kegadmin/beer_type_list.html', context_instance=context)


@staff_member_required
def beverage_detail(request, beer_id):
    btype = get_object_or_404(models.Beverage, id=beer_id)

    form = forms.BeverageForm(instance=btype)
    if request.method == 'POST':
        form = forms.BeverageForm(request.POST, instance=btype)
        if form.is_valid():
            btype = form.save()
            new_image = request.FILES.get('new_image')
            if new_image:
                pic = models.Picture.objects.create()
                pic.image.save(new_image.name, new_image)
                pic.save()
                btype.image = pic
                btype.save()

            messages.success(request, 'Beer type updated.')

    context = RequestContext(request)
    context['beer_type'] = btype
    context['form'] = form
    return render_to_response('kegadmin/beer_type_detail.html', context_instance=context)


@staff_member_required
def beverage_producer_list(request):
    context = RequestContext(request)
    brewers = models.BeverageProducer.objects.all().order_by('name')
    paginator = Paginator(brewers, 25)

    page = request.GET.get('page')
    try:
        brewers = paginator.page(page)
    except PageNotAnInteger:
        brewers = paginator.page(1)
    except EmptyPage:
        brewers = paginator.page(paginator.num_pages)

    context['brewers'] = brewers
    return render_to_response('kegadmin/brewer_list.html', context_instance=context)

@staff_member_required
def beverage_producer_detail(request, brewer_id):
    brewer = get_object_or_404(models.BeverageProducer, id=brewer_id)

    form = forms.BeverageProducerForm(instance=brewer)
    if request.method == 'POST':
        form = forms.BeverageProducerForm(request.POST, instance=brewer)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brewer updated.')

    context = RequestContext(request)
    context['brewer'] = brewer
    context['form'] = form
    return render_to_response('kegadmin/brewer_detail.html', context_instance=context)

@staff_member_required
def autocomplete_beverage(request):
    context = RequestContext(request)
    search = request.GET.get('q')
    if search:
        beverages = models.Beverage.objects.filter(Q(name__icontains=search) | Q(producer__name__icontains=search))
    else:
        beverages = models.Beverage.objects.all()
    beverages = beverages[:10]  # autocomplete widget limited to 10
    values = []
    for beverage in beverages:
        values.append({
          'name': beverage.name,
          'id': beverage.id,
          'producer_name': beverage.producer.name,
          'producer_id': beverage.producer.id,
          'style': beverage.style,
      })
    return HttpResponse(kbjson.dumps(values, indent=None),
      mimetype='application/json', status=200)

@staff_member_required
def autocomplete_user(request):
    context = RequestContext(request)
    search = request.GET.get('q')
    if search:
        users = models.User.objects.filter(Q(username__icontains=search) | Q(email__icontains=search))
    else:
        users = models.User.objects.all()
    users = users[:10]  # autocomplete widget limited to 10
    values = []
    for user in users:
        values.append({
          'username': user.username,
          'id': user.id,
          'email': user.email,
          'is_active': user.is_active,
      })
    return HttpResponse(kbjson.dumps(values, indent=None),
      mimetype='application/json', status=200)

@staff_member_required
def autocomplete_token(request):
    context = RequestContext(request)
    search = request.GET.get('q')
    if search:
        tokens = models.AuthenticationToken.objects.filter(
            Q(token_value__icontains=search) | Q(nice_name__icontains=search))
    else:
        tokens = models.AuthenticationToken.objects.all()
    tokens = tokens[:10]  # autocomplete widget limited to 10
    values = []
    for token in tokens:
        values.append({
          'username': token.user.username,
          'id': token.id,
          'auth_device': token.auth_device,
          'token_value': token.token_value,
          'enabled': token.enabled,
      })
    return HttpResponse(kbjson.dumps(values, indent=None),
      mimetype='application/json', status=200)

@staff_member_required
def plugin_settings(request, plugin_name):
    context = RequestContext(request)
    plugin = request.plugins.get(plugin_name, None)
    if not plugin:
        raise Http404('Plugin "%s" not loaded' % plugin_name)

    view = plugin.get_admin_settings_view()
    if not view:
        raise Http404('No settings for this plugin')

    return view(request, plugin)

@staff_member_required
def logs(request):
    context = RequestContext(request)
    context['errors'] = logger.get_cached_logs()
    return render_to_response('kegadmin/logs.html', context_instance=context)
