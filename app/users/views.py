import os, re, hmac, hashlib, json, time
import urllib.request, urllib.error, urllib.parse

from django.shortcuts import render, redirect
from django.db import transaction, IntegrityError, connection
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.query_utils import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated

from app.utils import ServiceException, SkipException, FrontendMixin
from app.models import UnclearDate, PhotoModel, GenderMixin

from django.contrib.auth.models import User
from users.models import Oauth, CreateUserMixin, IncognitoUser, Profile, TempToken, UuidMixin
from contact.models import Key, KeyType, CurrentState, OperationType, Wish, Ability
from contact.views import SendMessageMixin, ApiAddOperationMixin

class ApiGetProfileInfo(UuidMixin, APIView):

    def get(self, request):
        """
        Получение информации о профиле пользователя

        Возвращает информацию о пользователе, заданным get- параметром
        uuid: ФИО, фото, известность, общее количество благодарностей,
        количество утрат доверия и др.
        Если в запросе присутствует токен авторизации, то нужно вернуть и
        текущее состояние между пользователем, который запрашивает информацию,
        и пользователем, о котором он запрашивает информацию.

        Пример вызова:
        /api/getprofileinfo?uuid=9e936638-3c48-4e7b-bab4-7f968824acd5
        /api/getprofileinfo : для авторизованного пользователя

        Пример возвращаемых данных:
        {
            "first_name": "Иван",
            "middle_name": "Иванович",
            "last_name": "Иванов",
            "photo": "photo/url",
            "sum_thanks_count": 300,
            "fame": 3,
            "mistrust_count": 1,
            "is_notified": True,
            "trust_count": 3,
            "is_active": true,
        }
        """

        try:
            uuid=request.GET.get('uuid')
            if uuid:
                user, profile = self.check_user_uuid(uuid)
            else:
                if request.user.is_authenticated:
                    user = request.user
                    profile = user.profile
                else:
                    raise ServiceException("Не задан uuid или пользователь не вошел в систему")
            data = profile.data_dict(request)
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_get_profileinfo = ApiGetProfileInfo.as_view()

class ApiDownloadApkDetails(APIView):
    """
    Получить с github каталога данные о последней версии мобильного приложения
    """

    def post(self, request):
        try:
            header_signature = 'X-Hub-Signature'
            encoding_eq_signature = request.headers.get('X-Hub-Signature')
            if not encoding_eq_signature:
                raise ServiceException('No "%s" header with signature' % header_signature)
            encoding_eq_signature = encoding_eq_signature.lower()
            payload = request.body
            # Do not use any request.data stuff after that!

            # Example of encoding_signature:
            # 'sha1=5aaabbbcccdddeeefff11122233344455fffaaaa'
            #
            m = re.search(r'^([^\=]+)\=([^\=]+)$', encoding_eq_signature)
            if not m:
                raise ServiceException('Invalid "%s" header' % header_signature)
            encoding = getattr(hashlib, m.group(1), None)
            if not encoding:
                raise ServiceException('No "<encoding>=" in "%s" header' % header_signature)
            key = settings.GITHUB_WEBHOOK_SECRET
            key = key.encode('utf-8')
            if hmac.new(key, payload, encoding).hexdigest().lower() != m.group(2):
                raise ServiceException('Request is not properly signed')

            try:
                req = urllib.request.Request(settings.APK_OPTIONS_URL)
                response = urllib.request.urlopen(req, timeout=20)
                raw_data = response.read()
            except urllib.error.HTTPError as excpt:
                raise ServiceException('HTTPError: %s' % settings.APK_OPTIONS_URL)
            except urllib.error.URLError as excpt:
                raise ServiceException('URLError: %s' % settings.APK_OPTIONS_URL)
            fname = os.path.join(settings.MEDIA_ROOT, settings.APK_OPTIONS_DOWNLOAD)
            try:
                with open(fname, 'wb') as f:
                    f.write(raw_data)
            except IOError:
                raise ServiceException('Ошибка настройки сервера, не удалось записать в файл: %s' % fname)
            data = dict(message='Success: downloaded %s into %s' % (
                settings.APK_OPTIONS_URL,
                fname,
            ))
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_download_apk_details = ApiDownloadApkDetails.as_view()

class ApiGetLatestVersion(APIView):

    def get(self, request):
        """
        Получить последнюю версию кода апк

        Запрос возвращает последнюю версию кода апк,
        а также анонимный публичный ключ пользователя и
        таймштамп публичного ключа,
        соответствующих полученного приватному ключу
        в get параметре incognito_private_key
        """
        try:
            data = dict(
                url=settings.APK_URL,
                incognito_public_key=None,
                incognito_public_key_timestamp=None,
            )
            try:
                with open(os.path.join(settings.MEDIA_ROOT, settings.APK_OPTIONS_DOWNLOAD), 'r') as f:
                    raw_output = f.read()
            except IOError:
                raise ServiceException('Не нашел, не смог прочитать output.json')
            try:
                output = json.loads(raw_output)
            except ValueError:
                raise ServiceException('Неверные данные в output.json')
            try:
                data.update(
                    version_code=output['elements'][0]['versionCode'],
                    version_name=output['elements'][0]['versionName'],
                    google_play_url=settings.GOOGLE_PLAY_URL,
                    google_play_update=settings.GOOGLE_PLAY_UPDATE,
                )
            except (KeyError, IndexError,):
                raise ServiceException('Не нашел данные о версии мобильного приложения в output.json')
            private_key = request.GET.get('incognito_private_key')
            if private_key:
                try:
                    incognitouser = IncognitoUser.objects.get(private_key=private_key)
                    public_key = incognitouser.public_key
                    if public_key:
                        data['incognito_public_key'] = public_key
                        data['incognito_public_key_timestamp'] = incognitouser.update_timestamp
                except IncognitoUser.DoesNotExist:
                    pass
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 500
        return Response(data=data, status=200)

api_latest_version = ApiGetLatestVersion.as_view()

class ApiDownloadRatingApkDetails(APIView):
    """
    Получить с github каталога данные о последней версии мобильного приложения rating
    """

    def post(self, request):
        try:
            header_signature = 'X-Hub-Signature'
            encoding_eq_signature = request.headers.get('X-Hub-Signature')
            if not encoding_eq_signature:
                raise ServiceException('No "%s" header with signature' % header_signature)
            encoding_eq_signature = encoding_eq_signature.lower()
            payload = request.body
            # Do not use any request.data stuff after that!

            # Example of encoding_signature:
            # 'sha1=5aaabbbcccdddeeefff11122233344455fffaaaa'
            #
            m = re.search(r'^([^\=]+)\=([^\=]+)$', encoding_eq_signature)
            if not m:
                raise ServiceException('Invalid "%s" header' % header_signature)
            encoding = getattr(hashlib, m.group(1), None)
            if not encoding:
                raise ServiceException('No "<encoding>=" in "%s" header' % header_signature)
            key = settings.RATING_GITHUB_WEBHOOK_SECRET
            key = key.encode('utf-8')
            if hmac.new(key, payload, encoding).hexdigest().lower() != m.group(2):
                raise ServiceException('Request is not properly signed')

            try:
                ref = json.loads(payload)['ref']
            except (ValueError, KeyError,):
                raise ServiceException('No ref element in payload or invalid payload')
            m = re.search(r'^refs/heads/(%s)$' % settings.RATING_APK_BRANCHES, ref)
            if not m:
                raise ServiceException('Invalid ref element in payload or invalid branch value in ref')
            branch = m.group(1)

            apk_options_url = settings.RATING_APK_OPTIONS_URL % dict(
                branch=branch,
                build='debug' if branch == 'dev' else 'release',
            )
            apk_options_download = settings.RATING_APK_OPTIONS_DOWNLOAD % dict(branch=branch)
            try:
                req = urllib.request.Request(apk_options_url)
                response = urllib.request.urlopen(req, timeout=20)
                raw_data = response.read()
            except urllib.error.HTTPError as excpt:
                raise ServiceException('HTTPError: %s' % apk_options_url)
            except urllib.error.URLError as excpt:
                raise ServiceException('URLError: %s' % apk_options_url)
            fname = os.path.join(settings.MEDIA_ROOT, apk_options_download)
            try:
                with open(fname, 'wb') as f:
                    f.write(raw_data)
            except IOError:
                raise ServiceException('Ошибка настройки сервера, не удалось записать в файл: %s' % fname)
            data = dict(message='Success: downloaded %s into %s' % (
                apk_options_url,
                fname,
            ))
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_download_rating_apk_details = ApiDownloadRatingApkDetails.as_view()

class ApiGetRatingLatestVersion(APIView):

    def get(self, request):
        """
        Получить последнюю версию кода апк Rating
        """
        rating_apk_options_download = settings.RATING_APK_OPTIONS_DOWNLOAD % dict(
            branch=settings.RATING_APK_BRANCH,
        )
        try:
            try:
                with open(os.path.join(settings.MEDIA_ROOT, rating_apk_options_download), 'r') as f:
                    raw_output = f.read()
            except IOError:
                raise ServiceException('Не нашел, не смог прочитать output-metadata.json')
            try:
                output = json.loads(raw_output)
            except ValueError:
                raise ServiceException('Неверные данные в output-metadata.json')
            try:
                apk_fname = output['elements'][0]['outputFile']
                rating_apk_url = settings.RATING_APK_URL % dict(
                    branch=settings.RATING_APK_BRANCH,
                    apk_fname=apk_fname,
                    build='debug' if settings.RATING_APK_BRANCH == 'dev' else 'release',
                )
                data = dict(
                    path=rating_apk_url,
                    version_code=output['elements'][0]['versionCode'],
                    version_name=output['elements'][0]['versionName'],
                    rating_google_play_update=settings.RATING_GOOGLE_PLAY_UPDATE,
                )
            except (KeyError, IndexError,):
                raise ServiceException('Не нашел данные о версии мобильного приложения в output.json')
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 500
        return Response(data=data, status=200)

api_rating_latest_version = ApiGetRatingLatestVersion.as_view()

class ApiAuthSignUpIncognito(APIView):

    @transaction.atomic
    def post(self, request):
        """
        Создание анонимного пользователя

        На вход поступает, например:
        {
            "incognito": {
                "private_key": "becd79d8-9741-4d23-88fe-9c6a75ac881e",
                "public_key": "cf81884f-be1e-401e-a90b-1f70e2295a73"
            }
        }
        Возвращает:
        {
            "incognito_user_id": 12345
        }
        В таблице IncognitoUser создает запись с полученными ключами,
        если таковой не существует, либо, если запись с таким private_key уже существует,
        и при этом public_key пуст, то устанавливает public_key равным полученному значению
        """
        try:
            incognito = request.data.get('incognito')
            if not incognito or not incognito.get('private_key'):
                raise ServiceException('Не задан incognito ии incognito.private_key')
            try:
                incognito_user, created_ = IncognitoUser.objects.get_or_create(
                    private_key=incognito['private_key'].lower(),
                    defaults = dict(
                        public_key=incognito.get('public_key') and incognito['public_key'].lower() or None,
                ))
                if not created_ and 'public_key' in incognito:
                    public_key = incognito['public_key'] and incognito['public_key'].lower() or None
                    if incognito_user.public_key != public_key:
                        incognito_user.public_key = public_key
                        incognito_user.save()
                data = dict(
                    incognito_user_id = incognito_user.pk,
                )
                status_code = 200
            except IntegrityError:
                raise ServiceException('Не выполнено условие уникальности ключа')
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_auth_signup_incognito = ApiAuthSignUpIncognito.as_view()

class ApiAuthTelegram(CreateUserMixin, SendMessageMixin, APIView):
    """
    Callback функция авторизации через telegram

     Принимает:
     {
        "id": 78342834,
        "first_name": Иван",
        "last_name": "Петров",
        "username": "petrov",
        "photo_url": "https://t.me/i/userpic/320/92dcFhXhdjdjdjFwsiBzo1_M9HT-fyfAxJhoY.jpg",
        "auth_date": 1615848699,
        "hash": "bfdd33573729c511ad5bb969487b2e2ce9714e88cd8268929c010711ede3ed5d"
     }

    Проверяет правильность данных по hash,
    создает нового пользователя из telegram с id, при необходимости,
    выполняет его login()
    """

    @transaction.atomic
    def post(self, request):
        try:
            tg = request.data
            if not tg or not tg.get('auth_date') or not tg.get('hash') or not tg.get('id'):
                raise ServiceException('Неверный запрос')

            if not settings.TELEGRAM_BOT_TOKEN:
                raise ServiceException('В системе не определен TELEGRAM_BOT_TOKEN')

            request_data = tg.copy()
            unix_time_now = int(time.time())
            unix_time_auth_date = int(tg['auth_date'])
            if unix_time_now - unix_time_auth_date > settings.TELEGRAM_AUTH_DATA_OUTDATED:
                raise ServiceException('Неверный запрос, данные устарели')

            request_data.pop("hash", None)
            request_data_alphabetical_order = sorted(request_data.items(), key=lambda x: x[0])
            data_check_string = []
            for data_pair in request_data_alphabetical_order:
                key, value = data_pair[0], data_pair[1]
                data_check_string.append(key + "=" + str(value))
            data_check_string = "\n".join(data_check_string)
            secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
            calculated_hash = hmac.new(
                secret_key,
                msg=data_check_string.encode(),
                digestmod=hashlib.sha256,
            ).hexdigest()
            if calculated_hash != tg['hash']:
                raise ServiceException('Неверный запрос, данные не прошли проверку на hash')

            try:
                oauth = Oauth.objects.select_related('user', 'user__profile').get(
                    provider = Oauth.PROVIDER_TELEGRAM,
                    uid=tg['id'],
                )
                # При повторном логине проверяется, не изменились ли данные пользователя
                #
                user = oauth.user
                profile = user.profile

                oauth_tg_field_map = dict(
                    last_name='last_name',
                    first_name='first_name',
                    username='username',
                    photo='photo_url',
                )
                changed = False
                for f in oauth_tg_field_map:
                    if getattr(oauth, f) != tg.get(oauth_tg_field_map[f], ''):
                        changed = True
                        break
                if changed:
                    for f in oauth_tg_field_map:
                        setattr(oauth, f, tg.get(oauth_tg_field_map[f], ''))
                    oauth.update_timestamp = int(time.time())
                    oauth.save()

                user_tg_field_map = dict(
                    last_name='last_name',
                    first_name='first_name',
                )
                changed = False
                for f in user_tg_field_map:
                    if getattr(user, f) != tg.get(user_tg_field_map[f], ''):
                        changed = True
                        break
                was_not_active = False
                if not user.is_active:
                    changed = True
                    user.is_active = True
                    was_not_active = True
                if changed:
                    for f in user_tg_field_map:
                        setattr(user, f, tg.get(user_tg_field_map[f], ''))
                    user.save()

                profile_tg_field_map = dict(
                    photo_url='photo_url',
                )
                changed = False
                for f in profile_tg_field_map:
                    if getattr(profile, f) != tg.get(profile_tg_field_map[f], ''):
                        changed = True
                        break
                if changed:
                    for f in profile_tg_field_map:
                        setattr(profile, f, tg.get(profile_tg_field_map[f], ''))
                    profile.save()
                if was_not_active and profile.is_notified:
                    try:
                        telegram_uid = Oauth.objects.filter(user=user, provider=Oauth.PROVIDER_TELEGRAM)[0].uid
                        fio = profile.full_name(last_name_first=False) or 'Без имени'
                        message = "Cвязанный профиль '%s' восстановлен" % fio
                        self.send_to_telegram(message, telegram_uid=telegram_uid)
                    except IndexError:
                        pass
            except Oauth.DoesNotExist:
                last_name = tg.get('last_name', '')
                first_name = tg.get('first_name', '')
                photo_url = tg.get('photo_url', '')
                user = self.create_user(
                    last_name=last_name,
                    first_name=first_name,
                    photo_url=photo_url,
                )
                oauth = Oauth.objects.create(
                    provider = Oauth.PROVIDER_TELEGRAM,
                    uid=tg['id'],
                    user=user,
                    last_name=last_name,
                    first_name=first_name,
                    username=tg.get('username', ''),
                    photo=photo_url,
                )
            token, created_token = Token.objects.get_or_create(user=user)

            data = dict(
                user_uuid=user.profile.uuid,
                auth_token=token.key,
            )
            status_code = 200

        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_auth_telegram = ApiAuthTelegram.as_view()

class ApiOauthCallback(FrontendMixin, CreateUserMixin, APIView):

    OAUTH_PROVIDERS = {
        Oauth.PROVIDER_YANDEX: {
            # В вызове от провайдера могут прийти get параметры
            # имена которых для разных провайдеров могут отличаться
            #   'm_error': 'error',
            #   'm_error_description': 'error_description',

            # Имена полей для запроса токена, если они
            # отличаются от стандартных:
            #   't_grant_type': 'grant_type',
            #   't_authorization_code' = 'authorization_code',
            #   't_code': 'code',
            #   't_client_id': 'client_id',
            #   't_client_secret': 'client_secret',

            # Куда идём за токеном:
            #
            'request_token_url': 'https://oauth.yandex.ru/token',

            # Как идём за токеном, GET или POST
            #
            # 'request_token_method': 'POST',

            # Нужно ли добавлять redirect_uri и как может называться
            # redirect_uri.
            # Если не задан или пуст, то redirect_uri=<redirect_uri>
            # не добавляется в запрос токена
            #   't_redirect_uri': None,

            # В ответ ожидаем 'access_token': ..., но имя параметра
            # может отличаться
            #
            #   't_access_token': 'access_token',
        },
        Oauth.PROVIDER_VKONTAKTE: {
            'request_token_url': 'https://oauth.vk.com/access_token',
            'request_token_method': 'GET',
            't_redirect_uri': 'redirect_uri',
        },
        Oauth.PROVIDER_ODNOKLASSNIKI: {
            'request_token_url': 'https://api.ok.ru/oauth/token.do',
            't_redirect_uri': 'redirect_uri',
        },
    }

    @transaction.atomic
    def get(self, request, provider):
        """
        Callback функция для различных Oauth2 провайдеров (yandex, vk...)
        """
        try:
            s_provider = settings.OAUTH_PROVIDERS.get(provider)
            d_provider = self.OAUTH_PROVIDERS.get(provider)
            if not s_provider or not d_provider:
                return redirect(self.get_frontend_url(request) + '?error=provider_not_implemetnted')

            redirect_from_callback = self.get_frontend_url(request, settings.REDIRECT_FROM_CALLBACK)

            m_error = d_provider.get('m_error') or 'error'
            m_error_description = d_provider.get('m_error_description') or 'error_description'
            s_error = request.GET.get(m_error)
            if s_error:
                s_errors = '?error=%s' % urllib.parse.quote_plus(s_error)
                s_error_description = request.GET.get(m_error_description)
                if s_error_description:
                    s_errors += '&' + 'error_description=%s' % urllib.parse.quote_plus(s_error_description)
                return redirect(redirect_from_callback + s_errors)

            code = request.GET.get('code')
            if not code:
                return redirect(redirect_from_callback + '?error=no_code_received_in_callback')

            d_post_for_token = {}
            if provider in (Oauth.PROVIDER_YANDEX, Oauth.PROVIDER_ODNOKLASSNIKI):
                t_grant_type = d_provider.get('t_grant_type') or 'grant_type'
                t_authorization_code = d_provider.get('t_authorization_code') or 'authorization_code'
                d_post_for_token[t_grant_type] = t_authorization_code

            t_code = d_provider.get('t_code') or 'code'
            d_post_for_token[t_code] = code
            t_client_id = d_provider.get('t_client_id') or 'client_id'
            d_post_for_token[t_client_id] = s_provider['client_id']
            t_client_secret = d_provider.get('t_client_secret') or 'client_secret'
            d_post_for_token[t_client_secret] = s_provider['client_secret']

            t_redirect_uri = d_provider.get('t_redirect_uri')
            if t_redirect_uri:
                redirect_uri = request.build_absolute_uri()
                redirect_uri = re.sub(r'\?.*$', '', redirect_uri)
                d_post_for_token[t_redirect_uri] = redirect_uri

            t_request_token_method = d_provider.get('t_request_token_method') or 'POST'
            d_post_for_token = urllib.parse.urlencode(d_post_for_token)
            d_post_for_token = d_post_for_token.encode()
            if t_request_token_method == 'POST':
                req_post_for_token = urllib.request.Request(
                    d_provider['request_token_url'],
                    d_post_for_token
                )
            else:
                # GET, для vk
                req_post_for_token = urllib.request.Request(
                    d_provider['request_token_url'] + '?' + \
                    d_post_for_token
                )

            s_errors = '?error=error_getting_token_from_%s' %provider
            t_access_token = d_provider.get('t_access_token') or 'access_token'
            try:
                response_post_for_token = urllib.request.urlopen(req_post_for_token)
                raw_data = response_post_for_token.read().decode(
                    response_post_for_token.headers.get_content_charset('utf-8')
                )
                data = json.loads(raw_data)
                access_token = data.get(t_access_token)
                if not access_token:
                    return redirect(redirect_from_callback + s_errors)
            except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
                return redirect(redirect_from_callback + s_errors)

            oauth_dict = dict(
                provider=provider,
                token=access_token,
            )

            oauth_result = Oauth.check_token(oauth_dict)
            if oauth_result['message']:
                s_errors = '?error=error_getting_user_data_by_token'
                s_errors += '&' + 'error_description=%s' % \
                        urllib.parse.quote_plus(oauth_result['message'])
                return redirect(redirect_from_callback + s_errors)

            try:
                oauth = Oauth.objects.select_related(
                    'user',
                    'user__profile',
                    'user__auth_token',
                ).get(
                    provider=provider,
                    uid=oauth_result['uid'],
                )
                user = oauth.user
            except Oauth.DoesNotExist:
                user = self.create_user()
                oauth = Oauth.objects.create(
                    provider=provider,
                    uid=oauth_result['uid'],
                    user=user,
                )
                Token.objects.create(user=user)
            self.update_oauth(oauth, oauth_result)

            response = redirect(redirect_from_callback)
            to_cookie = dict(
                provider=provider,
                user_uuid=str(user.profile.uuid),
                auth_token=user.auth_token.key
            )
            response.set_cookie(
                key='auth_data',
                value=json.dumps(to_cookie),
                max_age=600,
                path='/',
                domain=self.get_frontend_name(request),
            )
            return response
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
            return Response(data=data, status=status_code)

api_oauth_callback = ApiOauthCallback.as_view()

class ApiUpdateFrontendSite(APIView):
    """
    Получить с github каталога сигнал об обновлении ветки frontend site и обновить эту ветку
    """

    def post(self, request):
        try:
            header_signature = 'X-Hub-Signature'
            encoding_eq_signature = request.headers.get('X-Hub-Signature')
            if not encoding_eq_signature:
                raise ServiceException('No "%s" header with signature' % header_signature)
            encoding_eq_signature = encoding_eq_signature.lower()
            payload = request.body
            # Do not use any request.data stuff after that!

            # Example of encoding_signature:
            # 'sha1=5aaabbbcccdddeeefff11122233344455fffaaaa'
            #
            m = re.search(r'^([^\=]+)\=([^\=]+)$', encoding_eq_signature)
            if not m:
                raise ServiceException('Invalid "%s" header' % header_signature)
            encoding = getattr(hashlib, m.group(1), None)
            if not encoding:
                raise ServiceException('No "<encoding>=" in "%s" header' % header_signature)
            key = settings.FRONTEND_GITHUB_WEBHOOK_SECRET
            key = key.encode('utf-8')
            if hmac.new(key, payload, encoding).hexdigest().lower() != m.group(2):
                raise ServiceException('Request is not properly signed')

            try:
                ref = json.loads(payload)['ref']
            except (ValueError, KeyError,):
                raise ServiceException('No ref key in payload or invalid payload')
            m = re.search(r'^refs/heads/([\w\-]+)$', ref)
            if not m:
                raise ServiceException("Invalid 'ref' value")
            branch = m.group(1)
            script = settings.FRONTEND_UPDATE_SCRIPT.get(branch)
            if not script:
                raise ServiceException("Unknown branch '%s' in frontend github repository" % branch)
            rc = os.system(script)
            if rc:
                raise ServiceException("Update script '%s' failed, rc = %s" % (script, rc,))
            data = dict(message="Success: updated branch '%s'" % branch)
            print(data['message'])
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_update_frontend_site = ApiUpdateFrontendSite.as_view()

class ApiInviteGetToken(APIView):
    permission_classes = (IsAuthenticated, )

    def post(self, request):
        token = TempToken.create(
            type_=TempToken.TYPE_INVITE,
            obj=request.user,
            ttl=86400*31,
        )
        token.save(force_insert=True)
        data = dict(token=token.token)
        status_code = status.HTTP_200_OK
        return Response(data=data, status=status_code)

api_invite_get_token = ApiInviteGetToken.as_view()

class ApiProfile(CreateUserMixin, UuidMixin, GenderMixin, SendMessageMixin, ApiAddOperationMixin, APIView):
    """
    Получить своих родственников (без связей), добавить/править/обезличить родственника. Правка своего профиля.

    GET
        Не требует авторизации
        без параметров:
            получить всех родственников авторизованного пользователя,
            массив json структур в формате, см. метод PUT.
            Возможны параметры для пагинации запроса: from (по умолчанию 0):
            с какого начинать, number (по умолчанию 50) сколько на странице.
            На любой странице будут еще данные авторизованного пользователя,
            если запрос авторизован.
        с параметром uuid=...
            получить данные по одному пользователю, необязательно родственнику

    PUT
        Править родственника или себя.
        Требует авторизации.
        На входе:
        form-data. Или multipart/form-data при наличии файла фото.
        При отсутствии файла photo можно передать в json структуре
            uuid:
                # обязательно
                # остальные поля могут отсутствовать. По отсутствующим полям
                # правка профиля не производится
            last_name
            first_name
            middle_name
            gender
            dob: дата рождения
                # гггг-мм-дд, гггг-мм, гггг или пустая строка (удаляет дату)
            dob: дата смерти
                # гггг-мм-дд, гггг-мм, гггг или пустая строка (удаляет дату)
            photo:
                # файл фото или строка:
                    - base64 encoded строка,
                    - файл с base64-encoded содержимым,
                    - “обычный” файл фото.
                  Размер строки/файла не должен превышать 10Мб
                  (для base64- строки/файла - не более 10Мб *4/3).
                    - или пустая строка, тогда текущее фото, если имеется, то удаляется
    POST
        * Добавить пользователя из бота телеграма.
        Не требует авторизации.
        На входе:
        Обязательны:
            tg_token: токен бота. Такой же записан в настройках АПИ
            tg_uid: uid пользователя в телеграме
        Не обязательны:
            last_name
            first_name
            username
                пользователя в телеграме
            photo
                путь, который можно включить в ссылку (действует 1 час):
                https://api.telegram.org/file/bot<tg_token>/<tg_photo_path>,
                скачать фото, записать в фото профиля.

        * Добавить родственника.
        Требует авторизации.
        На входе:
        form-data. Или multipart/form-data при наличии файла фото.
        При отсутствии файла photo можно передать в json структуре
            last_name
            first_name
                # Наличие last_name или first_name обязательно
                # остальные поля могут отсутствовать. По отсутствующим полям
                # заносятся пустые или null значения
            middle_name
            gender
            dob: дата рождения
                # гггг-мм-дд, гггг-мм, гггг или пустая строка (дата отсутствует)
            dob: дата смерти
                # гггг-мм-дд, гггг-мм, гггг или пустая строка (дата отсутствует)
            photo:
                # файл фото или строка:
                    - base64 encoded строка,
                    - файл с base64-encoded содержимым,
                    - “обычный” файл фото.
                  Размер строки/файла не должен превышать 10Мб
                  (для base64- строки/файла - не более 10Мб *4/3).

        Возможно вместе с созданием родственника сразу указать степень его родства
        к существующему пользователю (или пользователю - родственнику)

        link_uuid
            родитель или ребенок создаваемого профиля, должен существовать.
        link_relation, одно из:
            new_is_father: создаваемый родич является папой по отношению к link_uuid
            new_is_mother: создаваемая родственница является мамой по отношению к link_uuid
            link_is_father: link_uuid – это папа создаваемого родственника (создаваемой родственницы)
            link_is_mother: link_uuid – это мама создаваемого родственника (создаваемой родственницы)

        Если заданы link_uuid & link_relation, то новый пользователь становится прямым
        родственником по отношению к link_uuid. Вид родства, см. link_relation.
        Задать таким образом родство можно или если link_uuid
        это сам авторизованный пользователь или его родственник
        (владелец link_uuid - авторизованный пользователь).
        Иначе ошибка, а если нет недоверия между авторизованным пользователем и
        владельцем link_uuid или самим link_uuid, если им никто не владеет,
        то еще и уведомление в телеграм, что кто-то предлагает link_uuid назначить родственика

    DELETE
        uuid:
            # обязательно
    """

    parser_classes = (MultiPartParser, FormParser)

    def check_dates(self, request):
        dob = request.data.get('dob')
        dod = request.data.get('dod')
        m = UnclearDate.check_safe_str(dob)
        if m:
            raise ServiceException('Дата рождения: %s' % m)
        m = UnclearDate.check_safe_str(dod)
        if m:
            raise ServiceException('Дата смерти: %s' % m)
        dob = UnclearDate.from_str_safe(dob)
        dod = UnclearDate.from_str_safe(dod)
        return dob, dod

    def get(self, request):
        try:
            uuid = request.GET.get('uuid')
            if uuid:
                user, profile = self.check_user_uuid(uuid)
                data = profile.data_dict(request)
                data.update(profile.parents_dict(request))
            else:
                if not request.user.is_authenticated:
                    raise NotAuthenticated
                my_data = [request.user.profile.data_dict(request)]
                try:
                    from_ = abs(int(request.GET.get("from")))
                except (ValueError, TypeError, ):
                    from_ = 0
                try:
                    number_ = abs(int(request.GET.get("number")))
                except (ValueError, TypeError, ):
                    number_ = settings.PAGINATE_USERS_COUNT
                users_selected = Profile.objects.filter(owner=request.user). \
                    select_related('user', 'ability',).order_by(
                        '-user__date_joined',
                    )[from_:from_ + number_]
                data = my_data + [p.data_dict(request) for p in users_selected]
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

    def save_photo(self, request, profile):
        if request.data.get('photo'):
            photo_content = request.data.get('photo_content', 'base64')
            photo = PhotoModel.get_photo(
                request,
                photo_content=photo_content,
            )
            profile.delete_from_media()
            profile.photo.save(getattr(request.data['photo'], 'name', 'photo.png'), photo)

    def post_tg_data(self, request):
        status_code = status.HTTP_200_OK
        if request.data.get('tg_token') != settings.TELEGRAM_BOT_TOKEN:
            raise ServiceException('Неверный токен телеграм бота')
        last_name=request.data.get('last_name', '')
        first_name=request.data.get('first_name', '')
        created_ = False
        try:
            oauth = Oauth.objects.get(
                provider=Oauth.PROVIDER_TELEGRAM,
                uid=request.data.get('tg_uid'),
            )
            user = oauth.user
            profile = user.profile
            save_ = False
            for f in ('last_name', 'first_name', 'username', ):
                input_val = request.data.get(f, '')
                if getattr(oauth, f) != input_val and (input_val or f == 'username'):
                    setattr(oauth, f, input_val)
                    save_ = True
            if save_:
                oauth.update_timestamp = int(time.time())
                oauth.save()

        except Oauth.DoesNotExist:
            user = self.create_user(
                last_name=last_name,
                first_name=first_name,
            )
            profile = user.profile
            oauth = Oauth.objects.create(
                provider = Oauth.PROVIDER_TELEGRAM,
                uid=request.data.get('tg_uid'),
                user=user,
                last_name=last_name,
                first_name=first_name,
                username=request.data.get('username'),
            )
            token, created_token = Token.objects.get_or_create(user=user)
            self.save_photo(request, profile)
            created_ = True
        data = profile.data_dict(request)
        data.update(dict(created=created_, user_id=user.pk))
        return status_code, data

    @transaction.atomic
    def post(self, request):
        try:
            if request.data.get('tg_token') and request.data.get('tg_uid'):
                status_code, data = self.post_tg_data(request)
                raise SkipException

            status_code = status.HTTP_200_OK
            if not request.user.is_authenticated:
                raise NotAuthenticated
            if not request.data.get('last_name') and not request.data.get('first_name'):
                raise ServiceException('Фамилия или имя обязательно для нового')
            dob, dod =self.check_dates(request)
            self.check_gender(request)
            link_uuid = request.data.get('link_uuid')
            if link_uuid:
                link_user, link_profile = self.check_user_uuid(link_uuid)
                relation = request.data.get('link_relation', '')
                if relation not in ('new_is_father', 'new_is_mother', 'link_is_father', 'link_is_mother'):
                    raise ServiceException('При заданном link_uuid не получен или получен неправильный link_relation')
                if not (link_profile.owner == request.user or link_user == request.user):
                    if link_profile.owner:
                        msg_user_to = link_profile.owner
                    else:
                        msg_user_to = link_user
                    if not CurrentState.objects.filter(
                        user_from__in=(request.user, msg_user_to,),
                        user_to__in=(request.user, msg_user_to,),
                        user_to__isnull=False,
                        is_trust=False,
                       ).exists():
                        if link_profile.owner:
                            msg = '%s предлагает указать родственника для %s' % (
                                self.profile_link(request, request.user.profile),
                                self.profile_link(request, link_profile),
                            )
                        else:
                            msg = '%s предлагает указать для Вас родственника' % self.profile_link(request, request.user.profile)
                        self.send_to_telegram(msg, msg_user_to)
                    raise ServiceException('У Вас нет права указывать родственника к этому профилю')
            user = self.create_user(
                last_name=request.data.get('last_name', ''),
                first_name=request.data.get('first_name', ''),
                middle_name=request.data.get('middle_name', ''),
                owner=request.user,
                dob=dob,
                dod=dod,
                is_active=False,
                gender=request.data.get('gender') or None,
                latitude=request.data.get('latitude') or None,
                longitude=request.data.get('longitude') or None,
                comment=request.data.get('comment') or None,
            )

            if link_uuid:
                if relation == 'new_is_father':
                    is_father = True
                    link_user_from = link_user
                    link_user_to = user
                elif relation == 'new_is_mother':
                    is_father = False
                    link_user_from = link_user
                    link_user_to = user
                elif relation == 'link_is_father':
                    is_father = True
                    link_user_from = user
                    link_user_to = link_user
                elif relation == 'link_is_mother':
                    is_father = False
                    link_user_from = user
                    link_user_to = link_user

                self.add_operation(
                    link_user_from,
                    link_user_to.profile,
                    operationtype_id = OperationType.FATHER if is_father else OperationType.MOTHER,
                    comment = None,
                    insert_timestamp = int(time.time()),
                )

            profile = user.profile
            self.save_photo(request, profile)
            data = profile.data_dict(request)
        except SkipException:
            pass
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

    @transaction.atomic
    def put(self, request):
        if not request.user.is_authenticated:
            raise NotAuthenticated
        try:
            user, profile = self.check_user_or_owned_uuid(request, need_uuid=True)
            owner_uuid = request.data.get('owner_uuid')
            if owner_uuid:
                new_owner, new_owner_profile = self.check_user_uuid(owner_uuid)
                if not profile.owner:
                    raise ServiceException('Нельзя назначать владельца профилю зарегистрированного пользователя')
                if new_owner_profile.owner:
                    raise ServiceException('Нельзя делать владельцем профиль, которым кто-то владеет')
                profile.owner = new_owner
            dob, dod =self.check_dates(request)
            self.check_gender(request)
            if 'dob' in request.data:
                profile.dob = dob
            if 'dod' in request.data:
                profile.dod = dod
            for f in ('last_name', 'first_name',):
                if f in request.data:
                    setattr(user, f, request.data.get(f) or '')
            for f in ('middle_name',):
                if f in request.data:
                    setattr(profile, f, request.data.get(f) or '')
            for f in ('gender', 'latitude', 'longitude', 'comment',):
                if f in  request.data:
                    setattr(profile, f, request.data.get(f) or None)
            if 'is_notified' in request.data and user == request.user:
                profile.is_notified = bool(request.data.get('is_notified'))
            if 'photo' in request.data:
                if request.data.get('photo'):
                    self.save_photo(request, profile)
                else:
                    profile.delete_from_media()
                    profile.photo = None
                    profile.photo_original_filename = ''
            user.save()
            profile.save()
            data = profile.data_dict(request)
            data.update(profile.parents_dict(request))
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

    @transaction.atomic
    def delete(self, request):
        """
        Деактивировать профиль пользователя (обезличить)

        Если задан uuid, обезличиваем 
        Удалить:
            ФИО, фото - в профиле и во всех профилях соцсетей
            ключи
            возможности
            желания
            токен авторизации
            широта, долгота,
            пол
        Отметить а auth_user пользователя is_active = False
        Отправить сообщение в телеграм
        """
        try:
            if not request.user.is_authenticated:
                raise NotAuthenticated
            user, profile = self.check_user_or_owned_uuid(request, need_uuid=False)
            message = telegram_uid = None
            if profile.is_notified:
                try:
                    telegram = Oauth.objects.filter(user=user, provider=Oauth.PROVIDER_TELEGRAM)[0]
                    telegram_uid = telegram.uid
                    fio = (telegram.first_name + ' ' + telegram.last_name).strip()
                    message = "Cвязанный профиль '%s' обезличен пользователем" % fio
                except IndexError:
                    pass
            for f in ('photo', 'photo_original_filename', 'photo_url', 'middle_name',):
                setattr(profile, f, '')
            for f in ('latitude', 'longitude', 'gender', 'ability', 'comment',):
                setattr(profile, f, None)
            profile.delete_from_media()
            profile.photo = None
            profile.photo_original_filename = ''
            profile.save()

            Key.objects.filter(owner=user).delete()
            Ability.objects.filter(owner=user).delete()
            Wish.objects.filter(owner=user).delete()
            Token.objects.filter(user=user).delete()

            for oauth in Oauth.objects.filter(user=user):
                for f in ('last_name', 'first_name', 'display_name', 'email', 'photo', 'username'):
                    setattr(oauth, f, '')
                oauth.update_timestamp = int(time.time())
                oauth.save()
            for f in ('first_name', 'email'):
                setattr(user, f, '')
            user.last_name = "Обезличен"
            user.is_active = False
            user.save()
            if message:
                self.send_to_telegram(message, telegram_uid=telegram_uid)
            data = profile.data_dict(request)
            data.update(profile.parents_dict(request))
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_profile = ApiProfile.as_view()
