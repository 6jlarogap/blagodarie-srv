import datetime, string, random
import urllib.request, urllib.error, urllib.parse
import json, uuid

from django.conf import settings
from django.db import models, transaction, IntegrityError
from django.utils.translation import ugettext_lazy as _

from django.contrib.auth.models import User

from app.models import BaseModelInsertUpdateTimestamp, PhotoModel
from django.contrib.auth.models import User
from app.utils import ServiceException

class Oauth(BaseModelInsertUpdateTimestamp):

    PROVIDER_GOOGLE = 'google'

    OAUTH_PROVIDERS = (
        (PROVIDER_GOOGLE, _("Google")),
    )

    PROVIDER_DETAILS = {
        PROVIDER_GOOGLE: {
            'url': "https://oauth2.googleapis.com/tokeninfo?id_token=%(token)s",

            # Для отладки разработчиком
            #
            # 'url': "http://127.0.0.1:8000/api/auth/dummy?token=%(token)s",

            'uid': 'sub',
            'first_name': "given_name",
            'last_name': "family_name",
            'display_name': "name",
            'email': 'email',
            'photo': 'picture',

            # Это не от oauth провайдера, а из нашей таблицы ключей,
            # где может быть уже пользователь с таким ид от oauth,
            #
            'key_type_title': None,
        },
    }

    OAUTH_EXTRA_FIELDS = (
        'first_name',
        'last_name',
        'display_name',
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
    display_name = models.CharField(_("Отображаемое имя у провайдера"), max_length=255, default='')
    email = models.EmailField(_("Email у провайдера"), max_length=255, default='')
    photo = models.URLField(_("Фото у провайдера"), max_length=255, default='')

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

    @classmethod
    def check_token(cls, oauth_dict):
        """
        Проверить token у провайдера Oauth. Token & provider в входном oauth_dict
        
        oauth_dict:
        {
            "provider": "google",
            "token": ".....",
            "id": "..." # ID у провайдера
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

            key_type_title = None,
            message='',
            code=200,
        )
        try:
            try:
                provider = oauth_dict['provider']
                provider_details = Oauth.PROVIDER_DETAILS[oauth_dict['provider']]
                oauth_dict['token'] = urllib.parse.quote(oauth_dict['token'])
            except KeyError:
                raise ServiceException(_('Провайдер Oauth не задан или не поддерживается, или не задан token'))

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
            except ValueError:
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
            result['key_type_title'] = provider_details.get('key_type_title')
            for key in Oauth.OAUTH_EXTRA_FIELDS:
                real_key = provider_details.get(key)
                if real_key:
                    result[key] = data.get(real_key, '')
                    if isinstance(result[key], str):
                        result[key] = result[key].strip()
        except ServiceException as excpt:
            result['message'] = excpt.args[0]
            if result['code'] == 200:
                result['code'] = 400
        return result

class Profile(PhotoModel):
    user = models.OneToOneField('auth.User', on_delete=models.CASCADE)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    middle_name = models.CharField(_("Отчество"), max_length=255, blank=True, default='')
    photo_url = models.URLField(_("Фото из соц. сети"), max_length=255, default='')
    fame = models.PositiveIntegerField(_("Известность"), default=0)
    sum_thanks_count = models.PositiveIntegerField(_("Число благодарностей"), default=0)
    trustless_count = models.PositiveIntegerField(_("Число утрат доверия"), default=0)

    class Meta:
        ordering = ('user__last_name', 'user__first_name', 'middle_name', )

    def __str__(self):
        return self.full_name() or str(self.pk)

    def full_name(self, put_middle_name=True):
        name = ""
        if self.user.last_name:
            name = self.user.last_name
            if self.user.first_name:
                name = "{0} {1}".format(name, self.user.first_name)
                if put_middle_name and self.middle_name:
                    name = "{0} {1}".format(name, self.middle_name)
        if not name:
            name = self.user.get_full_name()
        return name

    @classmethod
    def choose_photo_of(cls, photo, photo_url):
        result = ''
        if photo:
            result = photo
        elif photo_url:
            result = photo_url
        return result

    def choose_photo(self):
        """
        Выбрать фото пользователя

        Если есть выданное пользователем фото (photo), то оно,
        иначе photo_url
        """
        return Profile.choose_photo_of(self.photo, self.photo_url)


class CreateUserMixin(object):

    MSG_FAILED_CREATE_USER = 'Не удалось создать пользователя с уникальным именем. Попробуйте еще раз.'

    def create_user(self, last_name='', first_name='', middle_name='', email=''):
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
                        last_name=last_name,
                        first_name=first_name,
                        email=email,
                    )
                    break
                except IntegrityError:
                    continue
        if user:
            Profile.objects.create(
                user=user,
                middle_name=middle_name,
            )
        return user

    def update_oauth(self, oauth, oauth_result):
        changed = False
        user_data_changed = False
        user_fields = ('last_name', 'first_name', 'email',)
        for f in Oauth.OAUTH_EXTRA_FIELDS:
            if getattr(oauth, f) != oauth_result[f]:
                changed = True
                if f in user_fields:
                    user_data_changed = True
        if changed:
            for f in Oauth.OAUTH_EXTRA_FIELDS:
                setattr(oauth, f, oauth_result[f])
            oauth.save()
            if user_data_changed:
                for f in user_fields:
                    setattr(oauth.user, f, oauth_result[f])
                oauth.user.save()
        if 'photo' in oauth_result:
            try:
                profile = Profile.objects.get(user=oauth.user)
                profile.photo_url = oauth_result['photo'] or ''
                profile.save(update_fields=('photo_url',))
            except Profile.DoesNotExist:
                pass

class IncognitoUser(BaseModelInsertUpdateTimestamp):

    private_key = models.CharField(_("Личный ключ"), max_length=36, unique=True, db_index=True)
    public_key = models.CharField(_("Публичный ключ"), max_length=36, null=True, unique=True, db_index=True)
