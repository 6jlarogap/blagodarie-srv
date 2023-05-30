import datetime, string, random, os, binascii, time
import urllib.request, urllib.error, urllib.parse
from urllib.parse import urlencode
import json, uuid, re, hashlib

from django.conf import settings
from django.db import models, transaction, IntegrityError
from django.db.models import Sum, F, Prefetch
from django.db.models.query_utils import Q
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django.apps import apps
get_model = apps.get_model

from app.models import UnclearDateModelField, GenderMixin

from app.models import BaseModelInsertUpdateTimestamp, BaseModelInsertTimestamp, PhotoModel, GeoPointAddressModel
from app.utils import ServiceException

class TgGroup(BaseModelInsertTimestamp):
    """
    В каких группах присутствует бот
    """

    chat_id = models.BigIntegerField(_("Chat Id"), unique=True, db_index=True)
    title = models.CharField(_("Имя"), max_length=256)
    type = models.CharField(_("Тип"), max_length=50)

    def data_dict(self):
        return {
            'id': self.pk,
            'type': self.type,
            'title': self.title,
            'chat_id': self.chat_id,
            'insert_timestamp': self.insert_timestamp,
        }

    def __str__(self):
        return '%s (%s)' % (self.title, self.chat_id)

class Oauth(BaseModelInsertUpdateTimestamp):

    PROVIDER_GOOGLE = 'google'
    PROVIDER_TELEGRAM = 'telegram'
    PROVIDER_YANDEX = 'yandex'
    PROVIDER_VKONTAKTE = 'vk'
    PROVIDER_ODNOKLASSNIKI = 'odnoklassniki'

    OAUTH_PROVIDERS = (
        (PROVIDER_GOOGLE, _("Google")),
        (PROVIDER_TELEGRAM, _("Telegram")),
        (PROVIDER_YANDEX, _("Яндекс")),
        (PROVIDER_VKONTAKTE, _("ВКонтакте")),
        (PROVIDER_ODNOKLASSNIKI, _("Одноклассники")),
    )

    PROVIDER_DETAILS = {
        PROVIDER_YANDEX: {
            'url': "https://login.yandex.ru/info?format=json&oauth_token=%(token)s",
            'uid': 'id',
            'first_name': "first_name",
            'last_name': "last_name",
            'display_name': "real_name",
            'email': 'default_email',
            'username': 'login',
            'photo': 'default_avatar_id',
            'photo_template': 'https://avatars.yandex.net/get-yapic/%(photo_id)s/islands-200',
            'no_photo_re': r'^[0\-\/]+$',

            # Получаем от yandex:
                #{
                    #"id": "2731235527",
                    #"login": "supdghhdhd",
                    #"client_id": "cf3f076367fda00041eaa223761237623476",
                    #"display_name": "ivanov",
                    #"real_name": "Иван Иванов",
                    #"first_name": "Иван",
                    #"last_name": "Иванов",
                    #"sex": "male",
                    #"default_email": "shjhashsh@yandex.by",
                    #"emails": [
                        #"supsdhdh@yandex.by"
                    #],
                    #"birthday": "1999-06-20",
                    #"default_avatar_id": "45848/6ZJ0cT3Y3c3cDasdgjasdghasd0oqHevdVQ-1",
                    #"is_avatar_empty": false,
                    #"psuid": "1.AAcEbg.0ezg0dsfjsdfjhsdfRA4qpCA.tR78f2grSo0kZfx5IZlOqQ"
                #}
        },
        PROVIDER_VKONTAKTE: {
            'url': "https://api.vk.com/method/users.get?access_token=%(token)s"
                   "&fields=uid,first_name,last_name,photo_200,sex"
                   "&v=5.89",
            'uid': 'id',
            'first_name': "first_name",
            'last_name': "last_name",
            'display_name': None,
            'photo': 'photo_200',
            # Если такое приходит в фото, то это заглушка под отсутствие фото,
            # например, http://vk.com/images/camera_200.png
            'no_photo_re': r'/images/camera_\S*\.\S{3}$',
            'site': 'site',

            # Получаем от vkontakte
            #{
                #"response":[
                    #{
                        #"first_name":"Евгений",
                        #"id":56262662627,
                        #"last_name":"Супрун",
                        #"can_access_closed":True,
                        #"is_closed":False,
                        #"photo_200":"https://sun2.beltelecom-by-minsk.userapi.com/hshshsh.jpg"
                                    #"?size=200x0&quality=96&crop=113,101,593,593&ava=1"
                    #}
                #]
            #}
        },
        PROVIDER_ODNOKLASSNIKI: {
            # Внимание! Именно http://
            'url': "http://api.ok.ru/fb.do?method=users.getCurrentUser&"
                   "access_token=%(token)s&"
                   "application_key=%(public_key)s&"
                   "fields=user.*&"
                   "format=json&"
                   "sig=%(signature)s",
            'uid': 'uid',
            'first_name': "first_name",
            'last_name': "last_name",
            'display_name': "name",
            'email': 'email',
            'photo': 'pic190x190',
        },

        # Получаем от одноклассников
        #{
            #'uid': '5626262',
            #'birthday': '1978-06-22',
            #'birthdaySet': True,
            #'age': 42,
            #'first_name': 'Петр',
            #'last_name': 'Иванов',
            #'name': 'Петр Иванов',
            #'locale': 'ru',
            #'gender': 'male',
            #'has_email': True,
            #'location': {
                #'city': 'Минск',
                #'country': 'BELARUS',
                #'countryCode': 'BY',
                #'countryName': 'Беларусь'
                #},
            #'online': 'web',
            #'photo_id': '8363576312366123',
            #'pic_1': 'https://pic_1',
            #'pic_2': 'https://pic_2',
            #'pic_3': 'https://pic_3',
            #'pic_4': 'https://pic_4',
            #'pic_5': 'https://pic_5',
            #'pic50x50': 'https://pic_1',
            #'pic128x128': 'https://pic_5',
            #'pic128max': 'https://pic_2',
            #'pic180min': 'https://pic180min',
            #'pic240min': 'https://pic240min',
            #'pic320min': 'https://pic320min',
            #'pic190x190': 'https://pic_3',
            #'pic640x480': 'https://pic_4',
            #'pic1024x768': 'https://pic1024x768',
            #'pic_full': 'https://pic_full',
            #'pic_base': 'https://pic_base',
            #'url_profile': 'https://ok.ru/profile/56105959595',
            #'url_profile_mobile': 'https://m.ok.ru/profile/56105959595',
            #'premium': False,
            #'has_phone': True
        #}
    }

    # Поля, кроме provider, uid, user, которые запоминаем в таблице Oauth

    OAUTH_EXTRA_FIELDS = (
        'first_name',
        'last_name',
        'display_name',
        'username',
        # 'email',
        'photo',
    )

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    provider = models.CharField(_("Провайдер"), max_length=100, choices=OAUTH_PROVIDERS)
    uid = models.CharField(_("Ид пользователя у провайдера"), max_length=255,)

    # Эти данные пока не заносятся. В дальнейшем, с согласия клиента
    #
    last_name = models.CharField(_("Фамилия у провайдера"), max_length=255, default='')
    first_name = models.CharField(_("Имя у провайдера"), max_length=255, default='')
    username = models.CharField(_("Логин у провайдера"), max_length=255, default='')
    display_name = models.CharField(_("Отображаемое имя у провайдера"), max_length=255, default='')
    email = models.EmailField(_("Email у провайдера"), max_length=255, default='')
    photo = models.URLField(_("Фото у провайдера"), max_length=255, default='')
    groups = models.ManyToManyField(TgGroup, verbose_name=_("Группы telegram пользователя"))
    tg_poll_answers = models.ManyToManyField('users.TgPollAnswer', verbose_name=_("Ответы на опросы телеграм"))

    class Meta:
        unique_together = ('provider', 'uid')

    def get_display_name(self):
        return self.display_name or \
               " ".join((self.first_name, self.last_name, )).strip()

    def __str__(self):
        dn = self.get_display_name()
        if dn:
            dn = "%s (%s)" % (dn, self.provider)
        else:
            dn = "%s (uid=%s)" % (self.provider, self.uid)
        return dn

    def tg_data(self):
        return dict(tg_uid=self.uid, tg_username=self.username)

    @classmethod
    def check_token(cls, oauth_dict):
        """
        Проверить token у провайдера Oauth. Token & provider в входном oauth_dict
        
        oauth_dict:
        {
            "provider": "google",
            "token": ".....",
        }
        Вернуть словарь из необходимого для записи в auth.User & users.Oauth:
            last_name, first_name, display_name, email, photo
        А также
            message (сообщение об ошибке)
            code: если 401, то Unaiuhorized, иначе 200 или 400
        """

        result = dict(
            uid='',

            last_name='',
            first_name='',
            display_name='',
            email='',
            photo='',
            username='',

            message='',
            code=200,
        )
        try:
            try:
                provider = oauth_dict['provider']
                provider_details = Oauth.PROVIDER_DETAILS[oauth_dict['provider']]
                oauth_dict['token'] = urllib.parse.quote_plus(oauth_dict['token'])
            except KeyError:
                raise ServiceException(_('Провайдер Oauth не задан или не поддерживается, или не задан token'))

            if provider == Oauth.PROVIDER_ODNOKLASSNIKI:
                oauth_dict['public_key'] = settings.OAUTH_PROVIDERS[provider]['public_key']
                #
                # <signature> = md5(
                #    "application_key={$public_key}format=jsonmethod=users.getCurrentUser" .
                #     md5("{$tokenInfo['access_token']}{$client_secret}")) (php код)
                #
                m = hashlib.md5()
                m.update(("%s%s" % (
                        oauth_dict['token'],
                        settings.OAUTH_PROVIDERS[provider]['client_secret'],
                    )).encode()
                )
                m2 = m.hexdigest()
                m = hashlib.md5()
                m.update((
                    "application_key=%sfields=user.*format=jsonmethod=users.getCurrentUser%s" % (
                        settings.OAUTH_PROVIDERS[provider]['public_key'],
                        m2,
                    )).encode()
                )
                oauth_dict['signature'] = m.hexdigest()

            url = provider_details['url'] % oauth_dict

            try:
                msg_debug = ", url: %s" % url if settings.DEBUG else ""
                r = urllib.request.urlopen(url)
                raw_data = r.read().decode(r.headers.get_content_charset('utf-8'))
            except urllib.error.HTTPError as excpt:
                result['code'] = 401
                raise ServiceException(
                    _('Ошибка в ответе от провайдера %(provider)s, '
                      'код: %(code)s, статус: %(reason)s%(msg_debug)s') % dict(
                        provider=provider,
                        code=excpt.getcode(),
                        reason=excpt.reason,
                        msg_debug=msg_debug
                ))
            except urllib.error.URLError as excpt:
                reason = ": %s" % excpt.reason if excpt.reason else ''
                raise ServiceException(
                    _('Ошибка связи с провайдером%(reason)s%(msg_debug)s') % dict(
                        reason=reason,
                        msg_debug=msg_debug,
            ))

            try:
                data = json.loads(raw_data)
                if provider == Oauth.PROVIDER_VKONTAKTE:
                    data = data['response'][0]
            except (KeyError, ValueError, IndexError,):
                msg_debug = " DEBUG: Request: %s. Response: %s" % (url, raw_data, ) \
                            if settings.DEBUG else ""
                raise ServiceException(
                    _("Ошибка интерпретации ответа от провайдера %(provider)s.%(msg_debug)s") % dict(
                        provider=provider, msg_debug=msg_debug,
                ))
            try:
                uid = data[provider_details['uid']]
            except KeyError:
                result['code'] = 401
                raise ServiceException(_('Не получен (id) от провайдера'))
            if not uid:
                result['code'] = 401
                raise ServiceException(_('Получен пустой (id) от провайдера'))

            result['uid'] = str(uid)
            for key in Oauth.OAUTH_EXTRA_FIELDS:
                real_key = provider_details.get(key)
                if real_key:
                    result[key] = data.get(real_key) or ''
                    if isinstance(result[key], str):
                        result[key] = result[key].strip()
                    if result[key]:
                        if key == 'photo':
                            if provider == Oauth.PROVIDER_YANDEX:
                                if data.get('is_avatar_empty') or \
                                   re.search(provider_details['no_photo_re'], result[key]):
                                    result[key] = ''
                                else:
                                    result[key] = provider_details['photo_template'] % \
                                                        dict(photo_id=result[key])
                            elif provider == Oauth.PROVIDER_VKONTAKTE:
                                if re.search(provider_details['no_photo_re'], result[key]):
                                    result[key] = ''
        except ServiceException as excpt:
            result['message'] = excpt.args[0]
            if result['code'] == 200:
                result['code'] = 400
        return result

class Profile(PhotoModel, GeoPointAddressModel):

    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    middle_name = models.CharField(_("Отчество"), max_length=255, blank=True, default='')
    is_notified = models.BooleanField(_("Принимает уведомления"), default=True)
    fame = models.PositiveIntegerField(_("Известность"), default=0)
    sum_thanks_count = models.PositiveIntegerField(_("Число благодарностей"), default=0)
    trust_count = models.PositiveIntegerField(_("Число оказанных доверий"), default=0)
    mistrust_count = models.PositiveIntegerField(_("Число утрат доверия"), default=0)
    did_bot_start = models.BooleanField(_("Стартовал телеграм бот"), default=False)
    ability = models.ForeignKey('contact.Ability', verbose_name=_("Способность"), null=True, on_delete=models.SET_NULL)
    # Для родни:
    owner = models.ForeignKey('auth.User', on_delete=models.CASCADE, null=True, related_name='profile_owner_set')
    gender = models.CharField(_("Пол"), max_length=1, choices=GenderMixin.GENDER_CHOICES, null=True)
    dob = UnclearDateModelField("Дата рождения", null=True, blank=True)

    # Может быть умершим, но дата смерти не задана
    is_dead = models.BooleanField(_("Умер ли?"), default=False)
    dod = UnclearDateModelField("Дата смерти", null=True, blank=True)

    comment = models.TextField(verbose_name=_("Примечание"), null=True)
    offer_answers = models.ManyToManyField('users.OfferAnswer', verbose_name=_("Ответы на опросы/предложения"))

    class Meta:
        ordering = ('user__first_name', )

    def __str__(self):
        return self.user.first_name or str(self.pk)

    def data_dict(self, request=None, short=False, fmt='d3js', mark_dead=False):
        user = self.user
        result = dict()
        if short:
            if fmt == '3d-force-graph':
                mark_dead = mark_dead and self.is_dead
                # Если задано отметить умершего и если умер, то фото в рамке
                result.update(
                    id=user.pk,
                    uuid=self.uuid,
                    first_name=user.first_name,
                    photo=self.choose_thumb(
                        request,
                        width=128,
                        height=128,
                        put_default_avatar=False,
                        mark_dead=mark_dead,
                    ) if request else '',
                    gender=self.gender,
                    is_dead = self.is_dead,
                )
            else:
                result.update(
                    uuid=str(self.uuid),
                    first_name=user.first_name,
                    photo=self.choose_photo(request) if request else '',
                )
        else:
            result.update(
                uuid=self.uuid,
                last_name=user.last_name,
                first_name=user.first_name,
                middle_name=self.middle_name,
                photo=self.choose_photo(request) if request else '',
                is_notified=self.is_notified,
                sum_thanks_count=self.sum_thanks_count,
                fame=self.fame,
                mistrust_count=self.mistrust_count,
                trust_count=self.trust_count,
                is_active=user.is_active,
                latitude=self.latitude,
                longitude=self.longitude,
                address=self.address,
                ability=self.ability and self.ability.text or None,
                gender=self.gender,
                dob=self.dob and self.dob.str_safe() or None,
                is_dead=self.is_dead or bool(self.dod),
                dod=self.dod and self.dod.str_safe() or None,
                comment=self.comment or '',
            )
        return result

    def owner_dict(self, request=None):
        if self.owner:
            owner_profile = self.owner.profile
            owner = owner_profile.data_dict(request)
            owner.update(tg_data=owner_profile.tg_data())
        else:
            owner = None
        return dict(owner=owner)

    def tg_data(self):
        """
        Найти профиль среди telegtam ouath's, вернуть данные
        """
        return [ oauth.tg_data()
            for oauth in Oauth.objects.filter(user=self.user, provider=Oauth.PROVIDER_TELEGRAM)
        ]

    def data_WAK(self):
        Wish = get_model('contact', 'Wish')
        Ability = get_model('contact', 'Ability')
        Key = get_model('contact', 'Key')
        user = self.user
        wishes = [
            wish.data_dict(
            ) for wish in Wish.objects.filter(owner=user).order_by('insert_timestamp')
        ]
        abilities = [
            ability.data_dict(
            ) for ability in Ability.objects.filter(owner=user).order_by('insert_timestamp')
        ]
        keys = [
            key.data_dict(
            )  for key in Key.objects.filter(owner=user).order_by('type__pk', 'pk')
        ]
        return dict(wishes=wishes, abilities=abilities, keys=keys)

    @transaction.atomic
    def merge(self, profile_from):
        # Проверку на один и тот же профиль производить
        # в вызывающей этот метод функции!
        #
        if self == profile_from:
            return

        CurrentState = get_model('contact', 'CurrentState')
        Journal = get_model('contact', 'Journal')

        Wish = get_model('contact', 'Wish')
        Ability = get_model('contact', 'Ability')
        Key = get_model('contact', 'Key')
        TgMessageJournal = get_model('contact', 'TgMessageJournal')

        user = self.user
        user_from = profile_from.user
        Oauth.objects.filter(user=user_from).update(user=user)

        Journal.objects.filter(user_from=user_from).update(user_from=user)
        Journal.objects.filter(user_from=user, user_to=user).delete()
        Journal.objects.filter(user_to=user_from).update(user_to=user)
        Journal.objects.filter(user_from=user, user_to=user).delete()

        TgMessageJournal.objects.filter(user_from=user_from).update(user_from=user)
        TgMessageJournal.objects.filter(user_to=user_from).update(user_to=user)
        TgMessageJournal.objects.filter(user_to_delivered=user_from).update(user_to_delivered=user)

        for cs in CurrentState.objects.filter(user_from=user_from, user_to__isnull=False):
            try:
                with transaction.atomic():
                    thanks_count = cs.thanks_count
                    user_to = cs.user_to
                    CurrentState.objects.filter(pk=cs.pk).update(user_from=user)
            except IntegrityError:
                CurrentState.objects.filter(pk=cs.pk).delete()
                CurrentState.objects.filter(
                    user_from=user,
                    user_to=user_to
                ).update(thanks_count=F('thanks_count') + thanks_count)
        CurrentState.objects.filter(user_from=user, user_to=user).delete()

        for cs in CurrentState.objects.filter(user_to=user_from):
            try:
                with transaction.atomic():
                    thanks_count = cs.thanks_count
                    user_from_ = cs.user_from
                    CurrentState.objects.filter(pk=cs.pk).update(user_to=user)
            except IntegrityError:
                CurrentState.objects.filter(pk=cs.pk).delete()
                CurrentState.objects.filter(
                    user_from=user_from_,
                    user_to=user
                ).update(thanks_count=F('thanks_count') + thanks_count)
        CurrentState.objects.filter(user_from=user, user_to=user).delete()

        for cs in CurrentState.objects.filter(user_from=user_from, anytext__isnull=False):
            try:
                with transaction.atomic():
                    anytext = cs.anytext
                    thanks_count = cs.thanks_count
                    CurrentState.objects.filter(pk=cs.pk).update(user_from=user)
            except IntegrityError:
                CurrentState.objects.filter(pk=cs.pk).delete()
                CurrentState.objects.filter(
                    user_from=user,
                    anytext=anytext
                ).update(thanks_count=F('thanks_count') + thanks_count)

        Wish.objects.filter(owner=user_from).update(owner=user)

        Ability.objects.filter(owner=user_from).update(owner=user)
        try:
            self.ability = user.ability_set.all().order_by('insert_timestamp')[0]
        except IndexError:
            self.ability = None
        self.save(update_fields=('ability',))

        for key in Key.objects.filter(owner=user_from):
            try:
                with transaction.atomic():
                    Key.objects.filter(pk=key.pk).update(owner=user)
            except IntegrityError:
                Key.objects.filter(pk=key.pk).delete()
        try:
            self_token = Token.objects.get(user=user)
        except Token.DoesNotExist:
            Token.objects.filter(user=user_from).update(user=user)

        Offer.objects.filter(owner=user_from).update(owner=user)

        do_save = False
        if not self.photo and profile_from.photo:
            self.photo = profile_from.photo
            profile_from.photo = ''
            do_save = True
        for f in (
            'photo_original_filename',
            'did_bot_start',
            'address', 'dob', 'dod', 'gender', 'comment', 'is_dead',
           ):
            if not getattr(self, f) and getattr(profile_from, f):
                setattr(self, f, getattr(profile_from, f))
                do_save = True
        for f in ('latitude', 'longitude'):
            if getattr(self, f) is None and getattr(profile_from, f) is not None:
                setattr(self, f, getattr(profile_from, f))
                do_save = True
        if do_save:
            self.save()

        Profile.objects.filter(owner=user_from).update(owner=user)

        profile_from_deleted = False
        if self.owner and not profile_from.owner:

            # Мигрируем not owned user (profile_from, user_from) -> owned user (self, user)
            # - uuid берем от активного (not-owned user)
            # - owned user пестает быть owned
            # -     посему делаем ему Token
            # - у мигрируемого пользователя могут быть owned. Пусть сам удаляет!
            #       TODO: рассмотреть это как опцию

            profile_from_uuid = profile_from.uuid
            profile_from.delete()
            profile_from_deleted = True
            self.uuid = profile_from_uuid
            self.owner = None
            self.save(update_fields=('uuid', 'owner',))
            Token.objects.get_or_create(user=user)
            user.is_active = True
            user.save(update_fields=('is_active',))

        if not profile_from_deleted:
            # Просто user_from.delete() удаляет profile из базы,
            # но не отрабатывект метод Profile.delete()
            profile_from.delete()

        user_from_id = user_from.id
        user_from.delete()

        self.recount_sum_thanks_count()
        self.recount_trust_fame()

    def recount_sum_thanks_count(self, do_save=True):
        CurrentState = get_model('contact', 'CurrentState')
        user = self.user
        self.sum_thanks_count = CurrentState.objects.filter(
            user_to=user,
        ).distinct().aggregate(Sum('thanks_count'))['thanks_count__sum'] or 0
        if do_save:
            self.save(update_fields=('sum_thanks_count',))

    def recount_trust_fame(self, do_save=True):
        CurrentState = get_model('contact', 'CurrentState')
        user = self.user
        self.trust_count = CurrentState.objects.filter(
            is_reverse=False,
            user_to=user,
            is_trust=True,
        ).distinct().count()
        self.mistrust_count = CurrentState.objects.filter(
            is_reverse=False,
            user_to=user,
            is_trust=False,
        ).distinct().count()
        self.fame = self.trust_count + self.mistrust_count
        if do_save:
            self.save(update_fields=('fame', 'trust_count', 'mistrust_count',))

    @classmethod
    def make_first_name(cls, last_name, first_name, middle_name=''):
        """
        В user.first_name будет и о ф
        """
        if middle_name and not first_name:
            result = (last_name or '').strip()
        else:
            result = " ".join(((first_name or ''), (middle_name or ''), (last_name or ''),)).strip()
        result = re.sub(r'\s{2,}', ' ', result)
        return result or 'Без имени'

    def parents_dict(self, request):
        """
        Вернуть папу, маму и детей из CurrentState
        """
        result = dict(father=None, mother=None, children=[])
        q = Q(user_to__isnull=False) & (Q(is_father=True) | Q(is_mother=True))
        for parent_link in self.user.currentstate_user_from_set.filter(q). \
                           select_related('user_to', 'user_to__profile', 'user_to__profile__ability'). \
                           order_by('user_to__first_name').distinct():
            human = parent_link.user_to.profile.data_dict(request)
            if parent_link.is_child:
                result['children'].append(human)
            elif parent_link.is_father:
                result['father'] = human
            elif parent_link.is_mother:
                result['mother'] = human
        return result

class CreateUserMixin(object):

    MSG_FAILED_CREATE_USER = 'Не удалось создать пользователя с уникальным именем. Попробуйте еще раз.'

    def create_user(self,
        last_name='',
        first_name='',
        middle_name='',
        email='',
        owner=None,
        dob=None,
        is_dead=False,
        dod=None,
        is_active=True,
        gender=None,
        latitude=None,
        longitude=None,
        comment=None,
    ):
        user = None
        random.seed()
        chars = string.ascii_lowercase + string.digits
        for c in '0Ol1':
            chars = chars.replace(c, '')
        dt_str = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        for i in range(100):
            with transaction.atomic():
                try:
                    username = "%s-%s" % (dt_str, ''.join(random.choice(chars) for x in range(5)),)
                    user = User.objects.create(
                        username=username,
                        last_name='',
                        first_name=Profile.make_first_name(last_name, first_name, middle_name),
                        email=email,
                        is_active=is_active,
                    )
                    break
                except IntegrityError:
                    continue
        if user:
            try:
                latitude = float(latitude)
                longitude = float(longitude)
            except (ValueError, TypeError,):
                latitude = longitude = None
            if dod:
                is_dead = True
            Profile.objects.create(
                user=user,
                middle_name='',
                owner=owner,
                dob=dob,
                is_dead=is_dead,
                dod=dod,
                gender=gender,
                latitude=latitude,
                longitude=longitude,
                address=GeoPointAddressModel.coordinates_to_address(latitude, longitude),
                comment=comment,
            )
        return user

    def update_oauth(self, oauth, oauth_result):
        changed = False
        for f in Oauth.OAUTH_EXTRA_FIELDS:
            if getattr(oauth, f) != oauth_result[f]:
                setattr(oauth, f, oauth_result[f])
                changed = True
        if changed:
            oauth.update_timestamp = int(time.time())
            oauth.save(update_fields=Oauth.OAUTH_EXTRA_FIELDS + ('update_timestamp',))

        user = oauth.user
        changed = False
        if user.last_name != '':
            user.last_name = ''
            changed = True
        first_name = Profile.make_first_name(oauth_result['last_name'], oauth_result['first_name'])
        if user.first_name != first_name:
            user.first_name = first_name
            changed = True
        user_fields = ('email',)
        for f in user_fields:
            if oauth_result[f] and getattr(user, f) != oauth_result[f]:
                setattr(user, f, oauth_result[f])
                changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if changed:
            user.save(update_fields=user_fields + ('is_active',))

        if oauth_result['photo'] and oauth.photo != oauth_result['photo']:
            user.profile.put_photo_from_url(oauth_result['photo'])

class IncognitoUser(BaseModelInsertUpdateTimestamp):

    private_key = models.CharField(_("Личный ключ"), max_length=36, unique=True, db_index=True)
    public_key = models.CharField(_("Публичный ключ"), max_length=36, null=True, unique=True, db_index=True)

class TempToken(BaseModelInsertTimestamp):
    """
    Для разного рода временных токенов
    """

    TYPE_INVITE = 1

    type = models.PositiveIntegerField(editable=False, db_index=True)
    ct = models.ForeignKey('contenttypes.ContentType', editable=False, on_delete=models.CASCADE)
    obj_id = models.PositiveIntegerField(editable=False, db_index=True)
    obj = GenericForeignKey(ct_field='ct', fk_field='obj_id')
    token = models.CharField(max_length=40, primary_key=True)
    ttl = models.PositiveIntegerField(editable=False)

    @classmethod
    def create(cls, type_, obj, ttl):
        temptoken = cls(
            type = type_,
            ct=ContentType.objects.get_for_model(obj),
            obj_id=obj.pk,
            token=binascii.hexlify(os.urandom(20)).decode(),
            ttl=ttl,
        )
        return temptoken

    def __str__(self):
        return "%s - %s" % (self.type, self.token, )

class UuidMixin(object):

    MSG_NO_UUID = 'Не задан uuid пользователя'

    def check_user_uuid(self, uuid, related=('user', 'ability',), comment=''):
        if not uuid:
            raise ServiceException(comment + self.MSG_NO_UUID)
        try:
            profile = Profile.objects.select_related(*related).get(uuid=uuid)
            user = profile.user
        except ValidationError:
            raise ServiceException('Неверный uuid = %s' % uuid)
        except Profile.DoesNotExist:
            raise ServiceException('Не найден пользователь с uuid = %s' % uuid)
        return user, profile

    def check_user_or_owned_uuid(
            self, request,
            uuid_field='uuid',
            related=('user', 'ability',),
            need_uuid=False,
        ):
        """
        Кого правим: авторизованного пользователя или заданного по uuid
        """
        uuid = request.data.get(uuid_field)
        if need_uuid and not uuid:
            raise ServiceException(self.MSG_NO_UUID)
        err_message = 'Профиль, uuid = "%s" не подлежит правке Вами' % uuid
        if uuid:
            user, profile = self.check_user_uuid(uuid, related=related)
        else:
            user = request.user
            profile = Profile.objects.select_related(*related).get(user=user)
        if profile.owner:
            if request.user != profile.owner:
                raise ServiceException(err_message)
        else:
            if user != request.user:
                raise ServiceException(err_message)
        return user, profile


class TelegramApiMixin(object):

    API_TELEGRAM = 'https://api.telegram.org'
    API_TIMEOUT = 20

    def send_to_telegram(self, message, user=None, telegram_uid=None):
        """
        Сообщение в телеграм или пользователю user, или по telegram uid
        """
        if not settings.SEND_TO_TELEGRAM:
            return

        uids = []
        if user:
            uids = [oauth.user_id for oauth in Oauth.objects.filter(user=user, provider=Oauth.PROVIDER_TELEGRAM)]
        elif telegram_uid:
            uids = [telegram_uid]

        for uid in uids:
            url = '%s/bot%s/sendMessage?' % (self.API_TELEGRAM, settings.TELEGRAM_BOT_TOKEN)
            parms = dict(
                chat_id=uid,
                parse_mode='html',
                text=message
            )
            url += urlencode(parms)
            try:
                req = urllib.request.Request(url)
                urllib.request.urlopen(req, timeout=self.API_TIMEOUT)
            except (urllib.error.URLError, ):
                pass

    def get_bot_data(self):
        """
        Получить данные бота
        """
        result = None
        url = '%s/bot%s/getMe' % (self.API_TELEGRAM, settings.TELEGRAM_BOT_TOKEN)
        try:
            req = urllib.request.Request(url)
            r = urllib.request.urlopen(req, timeout=self.API_TIMEOUT)
            raw_data = r.read().decode(r.headers.get_content_charset('utf-8'))
            try:
                data = json.loads(raw_data)
                if data['ok'] and data['result']:
                    result = data['result']
            except (KeyError, ValueError):
                pass
        except (urllib.error.URLError, ):
            pass
        return result

    def get_bot_username(self):
        """
        Получить имя бота
        """
        bot_data = self.get_bot_data()
        if bot_data and bot_data.get('username'):
            return bot_data['username']
        else:
            return None

    def get_deeplink(self, profile, bot_username=None):
        result = ''
        if not bot_username:
            bot_username = self.get_bot_username()
        if bot_username:
            result = 'https://t.me/%s?start=%s' % (bot_username, profile.uuid)
        return result

    def get_deeplink_name(self, profile, bot_username=None, target_blank=False):
        result = ''
        deeplink = self.get_deeplink(profile, bot_username)
        if deeplink:
            if target_blank:
                target = ' target="_blank"'
            else:
                target = ''
            result = '<a href="%(deeplink)s"%(target)s>%(full_name)s</a>' % dict(
                deeplink=deeplink,
                target=target,
                full_name=profile.user.first_name,
            )
        return result

class TgPoll(BaseModelInsertTimestamp):
    """
    Опрос в телеграме
    """

    poll_id = models.BigIntegerField(_("Poll Id"), unique=True, db_index=True)
    question = models.CharField(_("Вопрос"), max_length=256)
    # Сообщение с опросом и где это сообщение
    message_id = models.BigIntegerField(_("Message Id"))
    chat_id = models.BigIntegerField(_("Chat Id"))

    def data_dict(self):
        result = dict(
            poll_id=self.poll_id,
            question=self.question,
            message_id=self.message_id,
            chat_id=self.chat_id,
        )
        result.update(answers=[
            answer.data_dict() for answer in TgPollAnswer.objects.filter(
                tgpoll=self).order_by('number')
        ])
        return result

class TgPollAnswer(BaseModelInsertTimestamp):
    """
    Ответы на опросы в телеграме
    """
    tgpoll = models.ForeignKey(TgPoll, on_delete=models.CASCADE)
    # 0-й ответ резервируем для тех, кто сбросил свой голос
    number = models.PositiveIntegerField(_("Номер"), default=0)
    answer = models.CharField(_("Ответ"), max_length=255, blank=True, default='')

    class Meta:
        unique_together = ('tgpoll', 'number',)
        ordering = ('tgpoll', 'number',)

    def data_dict(self):
        return dict(
            number=self.number,
            answer=self.answer,
        )

    def __str__(self):
        return '%s: %s' % (self.number, self.answer)

class Offer(BaseModelInsertTimestamp):
    """
    Самодельный опрос в телеграме

    Теоретически может быть и не в телеграме, например сделанный в web приложении
    """

    MAX_NUM_ANSWERS = 9

    owner = models.ForeignKey('auth.User', verbose_name=_("Владелец"), on_delete=models.CASCADE)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    question = models.CharField(_("Вопрос"), max_length=256)
    closed_timestamp = models.PositiveIntegerField(_("Приостановлен"), null=True, default=None)
    is_multi = models.BooleanField(_("Множественный выбор"), default=False)

    def data_dict(self, request=None, user_ids_only=False):
        result = dict(
            uuid=self.uuid,
            owner={
                'first_name': self.owner.first_name,
                'uuid':self.owner.profile.uuid,
                'id': self.owner.pk,
            },
            question=self.question,
            timestamp=self.closed_timestamp if self.closed_timestamp else int(time.time()),
            closed_timestamp=self.closed_timestamp,
            is_multi=self.is_multi,
        )
        prefetch = Prefetch('profile_set', queryset=Profile.objects.select_related('user',).all())
        queryset = OfferAnswer.objects.prefetch_related(prefetch).select_related('offer').filter(offer=self)
        answers = []
        user_answered = dict()
        for answer in queryset:
            answer_dict = answer.data_dict()
            users = []
            for profile in answer.profile_set.all():
                user_id = profile.user.pk
                if user_ids_only:
                    users.append(user_id)
                else:
                    users.append(profile.data_dict(request, short=True, fmt='3d-force-graph'))
                if user_answered.get(user_id):
                    user_answered[user_id]['answers'].append(answer_dict['number'])
                else:
                    user_answered[user_id] = dict(answers=[answer_dict['number']])
            answer_dict.update(users=users)
            answers.append(answer_dict)
        result.update(answers=answers, user_answered=user_answered)
        return result

class OfferAnswer(BaseModelInsertTimestamp):
    """
    Ответы на опросы типа offer
    """
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE)
    # 0-й ответ резервируем для тех, кто сбросил свой голос
    number = models.PositiveIntegerField(_("Номер"), default=0)
    answer = models.CharField(_("Ответ"), max_length=255, blank=True, default='')

    class Meta:
        unique_together = ('offer', 'number',)
        ordering = ('offer', 'number',)

    def data_dict(self):
        return dict(
            number=self.number,
            answer=self.answer,
        )

    def __str__(self):
        return '%s: %s' % (self.number, self.answer)
