import os, re, hmac, hashlib, json, time
import urllib.request, urllib.error, urllib.parse

from ged4py.parser import GedcomReader

from django.shortcuts import render, redirect
from django.db import transaction, IntegrityError, connection
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.query_utils import Q
from django.http import Http404
from django.contrib.postgres.search import SearchQuery, SearchVector
from django.db.utils import ProgrammingError

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
from users.models import Oauth, CreateUserMixin, IncognitoUser, Profile, TgGroup, \
    TempToken, UuidMixin, TelegramApiMixin, \
    TgPoll, TgPollAnswer
from contact.models import Key, KeyType, CurrentState, OperationType, Wish, Ability, ApiAddOperationMixin

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

class ApiAuthTelegram(CreateUserMixin, TelegramApiMixin, FrontendMixin, APIView):
    """
    Callback функция авторизации через telegram

     Принимает, при post запросе:
     {
        "id": 78342834,
        "first_name": Иван",
        "last_name": "Петров",
        "username": "petrov",
        "photo_url": "https://t.me/i/userpic/320/92dcFhXhdjdjdjFwsiBzo1_M9HT-fyfAxJhoY.jpg",
        "auth_date": 1615848699,
        "hash": "bfdd33573729c511ad5bb969487b2e2ce9714e88cd8268929c010711ede3ed5d"
        # необязательно
        "redirect_path: путь к <frontend-url>/, например "/profile/id=....'
     }
     При get запросе: аналогичные данные в строке запроса

    Проверяет правильность данных по hash,
    создает нового пользователя из telegram с id, при необходимости,

    Возвращает:
        при отсутствии redirect_path:
            {
                "user_uuid": <uuid пользователеля>,
                "auth_token": <его токен авторизации>,
            }
        при наличиии redirect_path:
            перенаправляет на <frontend>/<redirect_path>, с аналогичной кукой:
                key='auth_data',
                value=json.dumps({
                    provider=provider,
                    user_uuid=<uuid пользователеля>,
                    auth_token=<его токен авторизации>
                }),
                max_age=600,
                path='/',
                domain=<frontend domain>,
    """

    def check_input(self, request):
        if request.method == 'POST':
            rd = request.data
        elif request.method == 'GET':
            rd = request.GET
        msg_invalid_request = 'Неверный запрос'
        try:
            if not rd or not rd.get('auth_date') or not rd.get('hash') or not rd.get('id'):
                raise ServiceException(msg_invalid_request)
        except AttributeError:
            raise ServiceException(msg_invalid_request)
        if not settings.TELEGRAM_BOT_TOKEN:
            raise ServiceException('В системе не определен TELEGRAM_BOT_TOKEN')

        request_data = rd.copy()
        unix_time_now = int(time.time())
        unix_time_auth_date = int(rd['auth_date'])
        if unix_time_now - unix_time_auth_date > settings.TELEGRAM_AUTH_DATA_OUTDATED:
            raise ServiceException('Неверный запрос, данные устарели')

        request_data.pop("hash", None)
        try:
            request_data.pop("redirect_path", None)
        except KeyError:
            pass
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
        if calculated_hash != rd['hash']:
            raise ServiceException('Неверный запрос, данные не прошли проверку на hash')
        return rd

    def process_input(self, rd):
        photo_url = rd.get('photo_url', '')
        try:
            oauth = Oauth.objects.select_related('user', 'user__profile').get(
                provider = Oauth.PROVIDER_TELEGRAM,
                uid=rd['id'],
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
                if getattr(oauth, f) != rd.get(oauth_tg_field_map[f], ''):
                    changed = True
                    break
            if changed:
                for f in oauth_tg_field_map:
                    setattr(oauth, f, rd.get(oauth_tg_field_map[f], ''))
                oauth.update_timestamp = int(time.time())
                oauth.save()

            if user.last_name != '':
                user.last_name = ''
                changed = True
            first_name = Profile.make_first_name(rd['last_name'], rd['first_name'])
            if user.first_name != first_name:
                user.first_name = first_name
                changed = True
            was_not_active = False
            if not user.is_active:
                changed = True
                user.is_active = True
                was_not_active = True
            if changed:
                user.save()

            if was_not_active and profile.is_notified:
                fio = profile.user.first_name or 'Без имени'
                message = "Cвязанный профиль '%s' восстановлен" % fio
                self.send_to_telegram(message, user=user)

        except Oauth.DoesNotExist:
            last_name = rd.get('last_name', '')
            first_name = rd.get('first_name', '')
            user = self.create_user(
                last_name=last_name,
                first_name=first_name,
            )
            oauth = Oauth.objects.create(
                provider = Oauth.PROVIDER_TELEGRAM,
                uid=rd['id'],
                user=user,
                last_name=last_name,
                first_name=first_name,
                username=rd.get('username', ''),
                photo=photo_url,
            )
        token, created_token = Token.objects.get_or_create(user=user)

        if photo_url and oauth.photo != photo_url:
            user.profile.put_photo_from_url(photo_url)
        return dict(
            user_uuid=str(user.profile.uuid),
            auth_token=token.key,
        )

    def do_redirect(self, request, rd, data):
        redirect_path = rd.get('redirect_path')
        if redirect_path:
            response = redirect(self.get_frontend_url(
                request=request,
                path=redirect_path,
            ))
            to_cookie = dict(provider=Oauth.PROVIDER_TELEGRAM, )
            to_cookie.update(data)
            response.set_cookie(
                key='auth_data',
                value=json.dumps(to_cookie),
                max_age=600,
                path='/',
                domain=self.get_frontend_name(request),
            )
            return response
        else:
            return None

    @transaction.atomic
    def process_request(self, request):
        try:
            # request data, got by GET or POST
            #
            rd = self.check_input(request)

            # output data
            #
            data = self.process_input(rd)

            # redirect with output data as cookie или return output data
            #
            redirected_response = self.do_redirect(request, rd, data)
            if redirected_response:
                return redirected_response

            status_code = 200
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

    def get(self, request):
        return self.process_request(request)

    def post(self, request):
        return self.process_request(request)

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

class ApiProfile(CreateUserMixin, UuidMixin, GenderMixin, FrontendMixin, TelegramApiMixin, ApiAddOperationMixin, APIView):
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
            получить данные по одному пользователю, необязательно родственнику,
        с параметром tg_uid=...
            получить данные по пользователю телеграма
        с параметром tg_uids=...
            получить данные по пользователям телеграма, список с разделителями
            запятой, более короткая выборка, нежели по одному tg_uid
        с одним из параметров query, query_ability, query_wish, query_person:
            получить список профилей пользователей,
                - найденных по фио и ключам (query_person),
                - возможностям (query_ability),
                - потребностям (query_wish)
                - или по фио и ключам (query)
                При этом возможны еще параметры:
                from
                    (default 0), начиная с какой записи
                number.
                    Сколько записей отдавать. По умолчанию без ограничений
                thumb_size
                    если не пустой, то включать еще и thumb_url, квадрат этой ширины и длины.
                    Thumbnail можем делать только от файлов, которые лежат в апи.
                    Если фото имеется только от других источников (телеграм, google),
                    то берется оттуда полное фото
                operation: and или or, искать по И или ИЛИ
        с параметром tg_username:
            Это строка telegram @usernames (без @ вначале), разделенных запятой
            например, username1,username2 ...
            Ищем у нас в базе все эти телеграм- usernames, возвращаем
            "карточки пользователей", включая их telegram id
            заодно вернуть abilities, wishes, keys

    PUT
        Править родственника или себя.
        Если задан верный tg_token: токен бота, то не требует авторизации.
        Иначе требует авторизации
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
        * Добавить активного пользователя из бота телеграма.
            Не требует авторизации.
            На входе:
            Обязательны:
                tg_token: токен бота. Такой же записан в настройках АПИ
                tg_uid: uid пользователя в телеграме
                В этом случае не обязательны:
                    last_name
                    first_name
                    username
                        пользователя в телеграме
                    photo
                        путь, который можно включить в ссылку (действует 1 час):
                        https://api.telegram.org/file/bot<tg_token>/<tg_photo_path>,
                        скачать фото, записать в фото профиля.
                    activate
                        активировать пользователя, если был обезличен

        * Добавить родственника.
            - если из телеграм бота, обязательны:
                tg_token: токен бота. Такой же записан в настройках АПИ
                owner_id: id пользователя, владельца
            - иначе требует авторизации.
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

    parser_classes = (MultiPartParser, FormParser, )

    def check_dates(self, request):
        dob = dob_got = request.data.get('dob')
        dod = dod_got = request.data.get('dod')
        m = UnclearDate.check_safe_str(dob)
        if m:
            raise ServiceException('Дата рождения: %s' % m)
        m = UnclearDate.check_safe_str(dod)
        if m:
            raise ServiceException('Дата смерти: %s' % m)
        dob = UnclearDate.from_str_safe(dob)
        dod = UnclearDate.from_str_safe(dod)
        if dob is not None and dod is not None and dob > dod:
            raise ServiceException('Дата рождения: %(dob)s, позже даты смерти: %(dod)s ' % dict(
                dod=dod_got,
                dob=dob_got,
            ))
        return dob, dod

    def get(self, request):
        try:
            data = dict()
            if request.GET.get('tg_uid'):
                try:
                    oauth = Oauth.objects.select_related(
                            'user', 'user__profile', 'user__profile__ability'
                        ).get(uid=request.GET['tg_uid'])
                except Oauth.DoesNotExist:
                    raise ServiceException('Telegram user with uid=%s not found' % request.GET['tg_uid'])
                profile = oauth.user.profile
                data = profile.data_dict(request)
                data.update(tg_data=profile.tg_data())
                data.update(user_id=oauth.user.pk)
            elif request.GET.get('uuid'):
                if request.GET.get('with_owner'):
                    related = ('user', 'ability','owner','owner__profile')
                else:
                    related = ('user', 'ability',)
                user, profile = self.check_user_uuid(
                    request.GET['uuid'],
                    related=related,
                )
                data = profile.data_dict(request)
                data.update(profile.parents_dict(request))
                data.update(profile.data_WAK())
                data.update(
                    user_id=user.pk,
                    owner_id=profile.owner and profile.owner.pk or None,
                )
                data.update(tg_data=profile.tg_data())
                if request.GET.get('with_owner'):
                    data.update(profile.owner_dict())
            elif request.GET.get('tg_uids'):
                data = []
                uids = request.GET['tg_uids'].split(',')
                user_pks = set()
                for oauth in Oauth.objects.select_related(
                            'user', 'user__profile'
                        ).filter(
                            provider=Oauth.PROVIDER_TELEGRAM,
                            uid__in=uids,
                   ):
                    user = oauth.user
                    if user.pk not in user_pks:
                        # Учтём возможные два тг аккаунта у одного юзера
                        profile = user.profile
                        item = profile.data_dict(request)
                        item.update(tg_data=dict(tg_uid=oauth.uid, tg_username=oauth.username,))
                        data.append(item)
                        user_pks.add(user.pk)
            elif request.GET.get('tg_username'):
                data = []
                usernames = request.GET['tg_username'].split(',')
                user_pks = set()
                q = Q()
                for username in usernames:
                    q |= Q(username__iexact=username)
                q &= Q(provider=Oauth.PROVIDER_TELEGRAM)
                for oauth in Oauth.objects.select_related(
                            'user', 'user__profile'
                    ).filter(q):
                    user = oauth.user
                    if user.pk not in user_pks:
                        # Учтём возможные два тг аккаунта у одного юзера
                        profile = user.profile
                        item = profile.data_dict(request)
                        item.update(profile.parents_dict(request))
                        item.update(profile.data_WAK())
                        item.update(
                            user_id=user.pk,
                            owner_id=profile.owner and profile.owner.pk or None,
                        )
                        item.update(tg_data=profile.tg_data())
                        data.append(item)
                        user_pks.add(user.pk)
            elif request.GET.get('query_ability') or \
                 request.GET.get('query_wish') or \
                 request.GET.get('query_person') or \
                 request.GET.get('query'):
                data = []
                if request.GET.get('query_ability'):
                    query = request.GET['query_ability']
                    fields = ('ability__text',)
                    mode = 'fulltext'
                elif request.GET.get('query_wish'):
                    query = request.GET['query_wish']
                    fields = ('wish__text',)
                    mode = 'fulltext'
                elif request.GET.get('query_person'):
                    query = request.GET['query_person']
                    fields = ('first_name', 'key__value',)
                    mode = 'icontains'
                else:
                    # аналог query_person
                    query = request.GET['query']
                    fields = ('first_name', 'key__value',)
                    mode = 'icontains'
                if len(query) >= settings.MIN_LEN_SEARCHED_TEXT:
                    operation = request.GET.get('operation', 'and')
                    if operation not in ('and', 'or'):
                        # default:
                        operation = 'and'
                    words = query.split()
                    if mode == 'fulltext':
                        sep = ' & ' if operation == 'and' else ' | '
                        query = sep.join(words)
                    else:
                        # icontains
                        for i, word in enumerate(words):
                            words[i] = re.escape(words[i].lower().replace('ё', 'е')).replace('е','[её]')
                            for j, field in enumerate(fields):
                                dict_regex = {('%s__iregex' % fields[j]): words[i]}
                                if j == 0:
                                    q_word = Q(**dict_regex)
                                else:
                                    q_word |= Q(**dict_regex)
                            if i == 0:
                                q_icontains = q_word
                            else:
                                if operation == 'and':
                                    q_icontains &= q_word
                                else:
                                    q_icontains |= q_word
                    try:
                        from_ = int(request.GET.get('from', 0) or 0)
                    except (ValueError, TypeError,):
                        from_ = 0
                    try:
                        number = int(request.GET.get('number', 0) or 0)
                    except (ValueError, TypeError,):
                        number = 0
                    try:
                        thumb_size = int(request.GET.get('thumb_size', 0) or 0)
                    except (ValueError, TypeError,):
                        thumb_size = 0
                    try:
                        q_active = Q(is_superuser=False) & (Q(is_active=True) | Q(profile__owner__isnull=False))
                        select_related = ('profile',)
                        if mode == 'fulltext':
                            search_vector = SearchVector(*fields, config='russian')
                            search_query = SearchQuery(query, search_type="raw", config='russian')
                            users = User.objects.annotate(
                                search=search_vector
                            ).select_related(*select_related).filter(q_active, search=search_query).distinct('id')
                        else:
                            # icontains
                            users = User.objects.filter(q_active, q_icontains
                            ).select_related(*select_related).distinct('id')
                        if number:
                            users = users[from_:from_ + number]
                        for user in users:
                            profile = user.profile
                            item = profile.data_dict(request)
                            item.update(user_id=user.pk)
                            if thumb_size:
                                item.update(thumb_url=profile.choose_thumb(
                                    request, width=thumb_size, height=thumb_size,
                                    put_default_avatar=False,
                                ))
                            data.append(item)
                    except ProgrammingError:
                        raise ServiceException(
                            'Неверная строка поиска',
                            'programming_error'
                        )
            elif request.GET.get('uuid_owner'):
                data = []
                users_selected = Profile.objects.filter(owner__profile__uuid=request.GET['uuid_owner']). \
                    select_related('user', 'ability',).order_by('user__first_name',)
                for profile in users_selected:
                    data_item = profile.data_dict(request)
                    data_item.update(
                        user_id=profile.user.pk,
                        owner_id=profile.owner and profile.owner.pk or None,
                    )
                    data.append(data_item)
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
            try:
                code=excpt.args[1]
            except IndexError:
                code=''
            data.update(code=code)
            status_code = 400
        return Response(data=data, status=status_code)

    def save_photo(self, request, profile):
        if request.data.get('photo'):
            photo_content = request.data.get('photo_content', 'base64')
            photo = PhotoModel.get_photo(
                request=request,
                photo_content=photo_content,
            )
            profile.delete_from_media()
            profile.photo.save(getattr(request.data['photo'], 'name', PhotoModel.DEFAULT_FNAME), photo)

    def post_tg_data(self, request):
        """
        Сделать, если не существует, нового пользователя по telegram id
        """
        profile = None
        data = dict()
        if request.data.get('tg_token') != settings.TELEGRAM_BOT_TOKEN:
            raise ServiceException('Неверный токен телеграм бота')
        last_name=request.data.get('last_name', '')
        first_name=request.data.get('first_name', '')
        try:
            oauth = Oauth.objects.get(
                provider=Oauth.PROVIDER_TELEGRAM,
                uid=request.data['tg_uid'],
            )
            user = oauth.user
            profile = user.profile
            if user.is_active or request.data.get('activate'):
                save_ = False
                for f in ('last_name', 'first_name', 'username', ):
                    input_val = request.data.get(f, '')
                    if getattr(oauth, f) != input_val:
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
                username=request.data.get('username', ''),
            )
            token, created_token = Token.objects.get_or_create(user=user)
            self.save_photo(request, profile)
            data.update(created=True)

        if request.data.get('did_bot_start') and not profile.did_bot_start:
            profile.did_bot_start = True
            profile.save(update_fields=('did_bot_start',))

        if not user.is_active and request.data.get('activate'):
            token, created_token = Token.objects.get_or_create(user=user)
            user.last_name = ''
            user.first_name = Profile.make_first_name(last_name, first_name)
            user.is_active = True
            user.save()

        data.update(profile.data_dict(request))
        data.update(profile.parents_dict(request))
        data.update(user_id=user.pk, tg_data=profile.tg_data())
        data.update(owner_id=profile.owner and profile.owner.id or None)
        data.update(profile.data_WAK())
        return data

    @transaction.atomic
    def post(self, request):
        try:
            got_tg_token = False
            status_code = status.HTTP_200_OK
            if request.data.get('tg_token') and request.data.get('tg_uid'):
                data = self.post_tg_data(request)
                raise SkipException

            # Запрос на создание owned user из телеграма ?:
            if request.data.get('tg_token') and request.data.get('owner_id'):
                if request.data['tg_token'] != settings.TELEGRAM_BOT_TOKEN:
                    raise ServiceException('Неверный токен телеграм бота')
                try:
                    owner = User.objects.select_related('profile').get(pk=request.data['owner_id'])
                    owner_profile = owner.profile
                    got_tg_token = True
                except User.DoesNotExist:
                    raise ServiceException('Неверный ид пользователя владельца, для создания owned profile, из телеграм- бота')
            elif not request.user.is_authenticated:
                raise NotAuthenticated
            else:
                owner = request.user
                owner_profile = owner.profile
            if not request.data.get('last_name') and not request.data.get('first_name'):
                raise ServiceException('Фамилия или имя обязательно для нового')
            dob, dod =self.check_dates(request)
            is_dead = bool(request.data.get('is_dead'))
            if dod:
                is_dead = True
            self.check_gender(request)
            link_uuid = request.data.get('link_uuid')
            if link_uuid:
                link_user, link_profile = self.check_user_uuid(link_uuid)
                relation = request.data.get('link_relation', '')
                if relation not in ('new_is_father', 'new_is_mother', 'link_is_father', 'link_is_mother'):
                    raise ServiceException('При заданном link_uuid не получен или получен неправильный link_relation')
                if not (link_profile.owner == owner or link_user == owner):
                    if link_profile.owner:
                        msg_user_to = link_profile.owner
                    else:
                        msg_user_to = link_user
                    if not CurrentState.objects.filter(
                        user_from__in=(owner, msg_user_to,),
                        user_to__in=(owner, msg_user_to,),
                        user_to__isnull=False,
                        is_trust=False,
                       ).exists():
                        if link_profile.owner:
                            msg = '%s предлагает указать родственника для %s' % (
                                self.profile_link(request, owner_profile),
                                self.profile_link(request, link_profile),
                            )
                        else:
                            msg = '%s предлагает указать для Вас родственника' % self.profile_link(request, owner_profile)
                        self.send_to_telegram(msg, msg_user_to)
                    raise ServiceException('У Вас нет права указывать родственника к этому профилю')

            gender_new = request.data.get('gender', '').lower() or None
            if link_uuid:
                msg_female_is_father = 'Женщина не может быть папой'
                msg_male_is_mother = 'Мужчина не может быть мамой'
                gender_link = link_profile.gender or None
                if gender_new is not None:
                    if relation == 'new_is_father' and gender_new == self.GENDER_FEMALE:
                        raise ServiceException(msg_female_is_father)
                    if relation == 'new_is_mother' and gender_new == self.GENDER_MALE:
                        raise ServiceException(msg_male_is_mother)
                if gender_link is not None:
                    if relation == 'link_is_father' and gender_link == self.GENDER_FEMALE:
                        raise ServiceException(msg_female_is_father)
                    if relation == 'link_is_mother' and gender_link == self.GENDER_MALE:
                        raise ServiceException(msg_male_is_mother)

            user = self.create_user(
                last_name=request.data.get('last_name', ''),
                first_name=request.data.get('first_name', ''),
                middle_name=request.data.get('middle_name', ''),
                owner=owner,
                dob=dob,
                is_dead=is_dead,
                dod=dod,
                is_active=False,
                gender=gender_new,
                latitude=request.data['latitude'] if 'latitude' in request.data else None,
                longitude=request.data['longitude'] if 'longitude' in request.data else None,
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

                if got_tg_token:
                    operationtype_id = OperationType.SET_FATHER if is_father else OperationType.SET_MOTHER
                else:
                    operationtype_id = OperationType.FATHER if is_father else OperationType.MOTHER
                self.add_operation(
                    link_user_from,
                    link_user_to.profile,
                    operationtype_id = operationtype_id,
                    comment = None,
                    insert_timestamp = int(time.time()),
                )

            profile = user.profile
            self.save_photo(request, profile)
            data = profile.data_dict(request)
            data.update(
                user_id=user.pk,
                owner_id=profile.owner and profile.owner.pk or None,
                tg_data=profile.tg_data()
            )
            data.update(profile.data_WAK())
            data.update(profile.parents_dict(request))
            if got_tg_token and link_uuid and relation in ('new_is_father', 'new_is_mother',):
                user_from = link_user_from
                profile_from = user_from.profile
                profile_from_data=profile_from.data_dict(request)
                profile_from_data.update(
                    user_id=user_from.pk,
                    owner_id=profile_from.owner and profile_from.owner.pk or None,
                    tg_data=profile_from.tg_data()
                )
                profile_from_data.update(profile_from.data_WAK())
                profile_from_data.update(profile_from.parents_dict(request))
                data.update(
                    profile_from=profile_from_data,
                )
        except SkipException:
            pass
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

    @transaction.atomic
    def put(self, request):
        status_code = 200
        try:
            got_tg_token = False
            if request.data.get('tg_token'):
                if request.data['tg_token'] != settings.TELEGRAM_BOT_TOKEN:
                    raise ServiceException('Неверный токен телеграм бота')
                got_tg_token = True
                user, profile = self.check_user_uuid(request.data.get('uuid'))
            elif not request.user.is_authenticated:
                raise NotAuthenticated
            else:
                user, profile = self.check_user_or_owned_uuid(request, need_uuid=True)

            if request.data.get('did_bot_start'):
                profile.did_bot_start = True

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
            if 'is_dead' in request.data:
                profile.is_dead = bool(request.data['is_dead'])
            if 'dod' in request.data:
                profile.dod = dod
                if dod:
                    profile.is_dead = True

            if request.data.get('last_name') or request.data.get('first_name'):
                first_name = Profile.make_first_name(
                    request.data.get('last_name', ''),
                    request.data.get('first_name', ''),
                    request.data.get('middle_name', ''),
                )
                user.last_name = ''
                user.first_name = first_name

            for f in ('comment', 'gender', ):
                if f in  request.data:
                    setattr(profile, f, request.data[f] or None)
            if 'latitude' in request.data and 'longitude' in request.data:
                latitude = longitude = None
                try:
                    latitude = float(request.data['latitude'])
                    longitude = float(request.data['longitude'])
                except (ValueError, TypeError,):
                    pass
                profile.put_geodata(latitude, longitude, save=False)
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
            data.update(profile.data_WAK())
            data.update(
                user_id=user.pk,
                owner_id=profile.owner and profile.owner.pk or None,
            )
            if got_tg_token:
                data.update(tg_data=profile.tg_data())
        except SkipException:
            pass
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

    @transaction.atomic
    def delete(self, request):
        """
        Деактивировать профиль пользователя (обезличить) или удалить собственного

        Если из телеграма, задан tg_token, то в принимаемых данных:
            - нужен uuid, свой или удаляемого собственного
            - еще owner_id, в любом случе id удаляющего юзера
        Иначе должен быть авторизован

        Обезличить активного:
        Устанавливаются:
            ФИО: Обезличен
        Удаляются:
            фото - в профиле и во всех профилях соцсетей
            ключи
            возможности
            желания
            токен авторизации
            широта, долгота,
            пол
        Отметить а auth_user пользователя is_active = False
        """
        try:
            tg_token = request.data.get('tg_token')
            if tg_token:
                if tg_token != settings.TELEGRAM_BOT_TOKEN:
                    raise ServiceException('Неверный токен телеграм бота')
                owner_id = request.data.get('owner_id')
                if not owner_id:
                    raise ServiceException('Не задан owner_id')
                user, profile = self.check_user_uuid(request.data.get('uuid'), related=('user',))
                if profile.owner:
                    try:
                        owner = User.objects.get(pk=owner_id)
                    except User.DoesNotExist:
                        raise ServiceException('Не верен owner_id')
                    if str(profile.owner.pk) != str(owner_id):
                        raise ServiceException(
                            "owner_id %s не имеет прав на профиль '%s'" % (owner_id, profile.uuid,)
                        )
                else:
                    if str(owner_id) != str(user.pk):
                        ServiceException('Вы не тот, за кого себя выдаете')
            else:
                if not request.user.is_authenticated:
                    raise NotAuthenticated
                user, profile = self.check_user_or_owned_uuid(request, need_uuid=False)
            if profile.owner:
                profile.delete()
                user.delete()
                data = {}
            else:
                for f in ('photo', 'photo_original_filename', 'middle_name',):
                        setattr(profile, f, '')
                for f in ('latitude', 'longitude', 'gender', 'ability', 'comment', 'address', 'dob', 'dod'):
                    setattr(profile, f, None)
                profile.is_dead = False
                profile.delete_from_media()
                profile.photo = None
                profile.photo_original_filename = ''
                profile.save()

                Key.objects.filter(owner=user).delete()
                Ability.objects.filter(owner=user).delete()
                Wish.objects.filter(owner=user).delete()
                Token.objects.filter(user=user).delete()

                CurrentState.objects.filter(
                    (Q(user_from=user) | Q(user_to=user)) & (Q(is_father=True) | Q(is_mother=True))
                ).update(is_father=False, is_mother=False, is_child=False)

                for oauth in Oauth.objects.filter(user=user):
                    for f in ('last_name', 'first_name', 'display_name', 'email', 'photo', 'username'):
                        setattr(oauth, f, '')
                    oauth.update_timestamp = int(time.time())
                    oauth.save()
                for f in ('last_name', 'email'):
                    setattr(user, f, '')
                user.first_name = "Обезличен"
                user.is_active = False
                user.save()
                data = profile.data_dict(request)
                data.update(user_id=user.pk, owner_id=None,)
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_profile = ApiProfile.as_view()

class ApiUserRelations(UuidMixin, APIView):
    """
    Как user_id_to относится к user_id_from

    Пример:
        api/user/relations?user_id_to=...&user_id_from=...я все ключи
    Возвращает
        {
        "from_to": {
            "is_trust": True,
            "thanks_count": 2,
            },
        "to_from": {
            "is_trust": null,
            "thanks_count": 0,
            },
        }
    """
    def get(self, request):
        try:
            status_code = status.HTTP_200_OK
            user_from, profile_from = self.check_user_uuid(
                request.GET.get('user_id_from'),
                comment='user_id_from. ',
            )
            user_to, profile_to = self.check_user_uuid(
                request.GET.get('user_id_to'),
                comment='user_id_to. ',
            )
            data = dict(
                from_to=dict(is_trust=None, thanks_count=0),
                to_from=dict(is_trust=None, thanks_count=0),
            )
            users = (user_from, user_to,)
            for cs in CurrentState.objects.filter(
                user_from__in=users,
                user_to__in=users,
                is_reverse=False,
                ):
                if cs.user_from == user_from:
                    data['from_to']['is_trust'] = cs.is_trust
                    data['from_to']['thanks_count'] = cs.thanks_count
                elif cs.user_from == user_to:
                    data['to_from']['is_trust'] = cs.is_trust
                    data['to_from']['thanks_count'] = cs.thanks_count
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_user_relations = ApiUserRelations.as_view()

class ApiTestGoToLink(FrontendMixin, APIView):

    """
    Тест для проверки авторизованного get запроса с временным токеном
    """
    def get(self, request, temp_token):
        try:
            try:
                user = User.objects.get(auth_token__key=temp_token)
            except User.DoesNotExist:
                raise Http404()
            uuid = request.GET.get('uuid')
            if uuid:
                path = '/profile/?id=%s' % uuid
            else:
                path = '/'
            provider = Oauth.PROVIDER_TELEGRAM
            redirect_from_callback = self.get_frontend_url(
                request,
                path,
            )
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
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

test_goto_auth_link = ApiTestGoToLink.as_view()

class ApiBotStat(APIView):
    """
    Статистика по пользователям для бота

    Количество пользователей - всего в нашей базе
    Всего сколько нажало старт
    Всего с заданными координатами
    """
    def get(self, request):
        data = {
            'active': Profile.objects.filter(user__is_superuser=False, owner__isnull=True).count(),
            'owned': Profile.objects.filter(owner__isnull=False).count(),
            'did_bot_start': Profile.objects.filter(did_bot_start=True, owner__isnull=True).count(),
            'with_geodata': Profile.objects.filter(latitude__isnull=False, owner__isnull=True).count(),
        }
        return Response(data=data, status=200)

api_bot_stat = ApiBotStat.as_view()

class ApiBotGroupMixin(APIView):

    def group_post(self, data):
        """
        Создать, если необходимо группу из ее данных, data
        """
        title = data.get('title', '')
        type_ = data.get('type', '')
        tg_group, created_ = TgGroup.objects.get_or_create(
            chat_id = data['chat_id'],
            defaults={
                'title': title,
                'type': type_,
        })
        if not created_:
            do_save = False
            if title and tg_group.title != title:
                do_save = True
                tg_group.title = title
            if type_ and tg_group.type != type_:
                do_save = True
                tg_group.type = type_
            if do_save:
                tg_group.save()
        status_code = status.HTTP_200_OK
        return tg_group, created_

class ApiBotGroup(ApiBotGroupMixin, APIView):
    """
    Записать в таблицу TgGroup информацию о группе. Или удалить из таблицы
    """

    def get(self, request):
        """
        Получить информацию о группе/каналу по chat_id
        """
        data = {}
        status_code = 404
        try:
            chat_id = int(request.GET.get('chat_id', ''))
            data = TgGroup.objects.get(chat_id=chat_id).data_dict()
            status_code = status.HTTP_200_OK
        except (ValueError, TypeError, TgGroup.DoesNotExist,):
            pass
        return Response(data=data, status=status_code)

    def check_data(self, request):
        if request.data.get('tg_token', '') != settings.TELEGRAM_BOT_TOKEN:
            raise ServiceException('Неверный токен телеграм бота')
        try:
            chat_id = int(request.data.get('chat_id') or 0)
        except (ValueError, TypeError,):
            chat_id = 0
        if not chat_id:
            raise ServiceException('Не верный chat_id')

    def post(self, request):
        try:
            self.check_data(request)
            tg_group, created_ = self.group_post(request.data)
            data = tg_group.data_dict()
            data.update(created=created_)
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

    def delete(self, request):
        try:
            self.check_data(request)
            chat_id = request.data['chat_id']
            try:
                TgGroup.objects.get(chat_id=chat_id).delete()
            except TgGroup.DoesNotExist:
                raise ServiceException('Группа с chat_id = %s не найдена среди назначенных боту' % chat_id)
            status_code = status.HTTP_200_OK
            data = {}
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_bot_group = ApiBotGroup.as_view()

class ApiBotGroupMember(ApiBotGroupMixin, APIView):
    """
    Добавить/удалить пользователя телеграм в группу
    """

    def check_data(self, request):
        """
        Проверка данных при добавлении/удаления пользователя из группы

        Данные на входе:
            tg_token
            group
                chat_id
                title
                type
            user
                tg_uid
        На выходе:  (объекты из б.д)
            oauth
            tggroup

        """
        if request.data.get('tg_token', '') != settings.TELEGRAM_BOT_TOKEN:
            raise ServiceException('Неверный токен телеграм бота')
        try:
            group = request.data['group']
            user = request.data['user']
        except KeyError:
            raise ServiceException('Не хватает данных: group и/или user')
        try:
            chat_id = int(group.get('chat_id') or 0)
        except (ValueError, TypeError, AttributeError):
            chat_id = 0
        if not chat_id:
            raise ServiceException('Не верный или отсутствует chat_id для группы')
        tg_group, created = self.group_post(group)
        try:
            tg_uid = user.get('tg_uid') or None
        except (AttributeError):
            tg_uid = None
        if not tg_uid:
            raise ServiceException('Не верный или отсутствует user.tg_uid')
        try:
            oauth = Oauth.objects.get(provider=Oauth.PROVIDER_TELEGRAM, uid=str(tg_uid))
        except Oauth.DoesNotExist:
            raise ServiceException('Нет такого tg_uid среди зарегистрированных пользователей телеграма в апи')
        return oauth, tg_group

    def post(self, request):
        try:
            oauth, tg_group = self.check_data(request)
            oauth.groups.add(tg_group)
            data = dict()
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

    def delete(self, request):
        try:
            oauth, tg_group = self.check_data(request)
            oauth.groups.remove(tg_group)
            status_code = 200
            data = {}
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_bot_groupmember = ApiBotGroupMember.as_view()

class ApiUserPoints(FrontendMixin, TelegramApiMixin, UuidMixin, APIView):

    # Фото пользователя, когда в карте щелкаешь на балун
    #
    THUMB_SIZE_POPUP = 64

    # Фото пользователя, по которому есть параметр uuid
    #
    THUMB_SIZE_ICON_FOUND = 48

    # Фото остальных пользователей
    #
    THUMB_SIZE_ICON = 32

    def get(self, request):
        """
        Вернуть пользователй с координатами
        """

        # Если точек нет, то пусть будут координаты Москвы
        # Чтобы не показывался в этом случае в Атлантическом океане
        #
        lat_avg = 55.7522200
        lng_avg = 37.6155600
        found_coordinates = False
        first_name = ''
        address = None
        chat_id = chat_title = chat_type = None
        if request.GET.get('uuid'):
            try:
                found_user, found_profile = self.check_user_uuid(request.GET['uuid'], related=('user',))
                first_name = found_user.first_name
                found_coordinates = bool(found_profile.latitude and found_profile.longitude)
                if found_coordinates:
                    lat_avg = found_profile.latitude
                    lng_avg = found_profile.longitude
                    address = found_profile.address
            except ServiceException:
                pass
        elif request.GET.get('chat_id'):
            chat_id = request.GET['chat_id']
        bot_username = self.get_bot_username()
        lat_sum = lng_sum = 0
        points = []
        q = Q(
            latitude__isnull=False,
            longitude__isnull=False,
        )
        if chat_id:
            try:
                tggroup = TgGroup.objects.get(chat_id=chat_id)
                chat_title = tggroup.title
                chat_type = tggroup.type
                q &= Q(user__oauth__groups__chat_id=chat_id)
            except (ValueError, TgGroup.DoesNotExist,):
                pass
        if chat_id and not chat_title:
            qs = Profile.objects.none()
        elif chat_id:
            qs = Profile.objects.filter(q).select_related('user').distinct()
        else:
            # Или задан uuid, или ничего
            qq_or = []
            if request.GET.get('participants'):
                qq_or.append(Q(owner__isnull=True))
            if request.GET.get('owned'):
                qq_or.append(Q(owner__isnull=False))
            if qq_or:
                for i, qq in enumerate(qq_or):
                    if i == 0:
                        q_or = qq
                    else:
                        q_or |= qq
                q &= q_or
                if found_coordinates:
                    q |= Q(pk=found_profile.pk)
                qs = Profile.objects.filter(q).select_related('user').distinct()
            else:
                if found_coordinates:
                    qs = Profile.objects.filter(pk=found_profile.pk).select_related('user').distinct()
                else:
                    qs = Profile.objects.none()
        for profile in qs:
            url_profile = self.profile_url(request, profile)
            if bot_username:
                url_deeplink = self.get_deeplink(profile, bot_username)
            else:
                url_deeplink = url_profile
            dict_user = dict(
                full_name = profile.user.first_name,
                trust_count=profile.trust_count,
                url_deeplink=url_deeplink,
                url_profile=url_profile,
                url_photo_popup=profile.choose_thumb(
                    request,
                    width=self.THUMB_SIZE_POPUP,
                    height=self.THUMB_SIZE_POPUP,
                    put_default_avatar=True,
                ),
                thumb_size_popup = self.THUMB_SIZE_POPUP,
            )
            popup = (
                '<table><tr>'
                    '<td>'
                       '<img src="%(url_photo_popup)s" width=%(thumb_size_popup)s height=%(thumb_size_popup)s>'
                    '</td>'
                    '<td>'
                        ' <a href="%(url_deeplink)s" target="_blank">%(full_name)s</a> (%(trust_count)s)'
                        '<br /><br />'
                        ' <a href="%(url_profile)s" target="_blank">Доверия</a>'
                    '</td>'
                '</tr></table>'
            ) % dict_user
            point = dict(
                latitude=profile.latitude,
                longitude=profile.longitude,
                title='(%(trust_count)s) %(full_name)s' % dict_user,
                popup=popup,
            )
            if found_coordinates and profile == found_profile:
                point.update(
                    is_of_found_user=True,
                    icon=profile.choose_thumb(
                        request,
                        width=self.THUMB_SIZE_ICON_FOUND, height=self.THUMB_SIZE_ICON_FOUND,
                        put_default_avatar=True,
                    ),
                    size_icon=self.THUMB_SIZE_ICON_FOUND,
                )
            else:
                point.update(
                    is_of_found_user=False,
                    icon=profile.choose_thumb(
                        request,
                        width=self.THUMB_SIZE_ICON, height=self.THUMB_SIZE_ICON,
                        put_default_avatar=True,
                    ),
                    size_icon=self.THUMB_SIZE_ICON,
                )
            points.append(point)
            if not found_coordinates:
                lat_sum += profile.latitude
                lng_sum += profile.longitude
        if points and not found_coordinates:
            lat_avg = lat_sum / len(points)
            lng_avg = lng_sum / len(points)
        data = dict(
            first_name=first_name,
            found_coordinates=found_coordinates,
            address=address,
            lat_avg=lat_avg,
            lng_avg=lng_avg,
            points=points,
            chat_id=chat_id,
            chat_title=chat_title,
            chat_type=chat_type,
        )
        return Response(data=data, status=200)

api_user_points = ApiUserPoints.as_view()

class ApiImportGedcom(ApiAddOperationMixin, UuidMixin, CreateUserMixin, APIView):

    def do_import(self, owner_uuid, bytes_io, indi_to_merge):
        """
        Импорт из gedcom файла

        owner_uuid:         uuid владельца импорируемых персон
        bytes_io:           считанный в BytesIO gedcom файл
        indi_to_merge:      в файле может быть владелец,
                            его сливаем с пользователем c owner_uuid
        """
        owner, owner_profile = self.check_user_uuid(owner_uuid, related=[])
        if owner_profile.owner:
            raise ServiceException('Допускается owner_id только активного пользователя')

        with GedcomReader(bytes_io) as parser:

            #   (ged)xref_id:
            #       first_name, first_name, gender, dob, dod, is_dead
            #       father_xref_id
            #       mother_xref_id
            #
            indis = dict()

            for indi in parser.records0('INDI'):
                xref_id = indi.xref_id
                first_name = indi.name.format() or ''
                gender = indi.sub_tag_value('SEX')
                if gender:
                    gender = gender.lower()
                    if gender not in (GenderMixin.GENDER_MALE, GenderMixin.GENDER_FEMALE):
                        gender = None
                dob = indi.sub_tag_value('BIRT/DATE') or None
                if dob:
                    dob = UnclearDate.from_str_safe(str(dob), format='d M y')
                is_dead = bool(indi.sub_tag_value('DEAT'))
                dod = indi.sub_tag_value('DEAT/DATE') or None
                if dod:
                    dod = UnclearDate.from_str_safe(str(dod), format='d M y')
                    is_dead = True
                item = dict(
                    first_name=first_name,
                    gender=gender,
                    dob=dob,
                    is_dead=is_dead,
                    dod=dod,
                    father_xref_id=indi.father and indi.father.xref_id or None,
                    mother_xref_id=indi.mother and indi.mother.xref_id or None,
                )
                indis[xref_id] = item

        if indi_to_merge not in indis:
            raise ServiceException('В gedcom данных не обнаружен человек, который будет владельцем')

        for key in indis:
            item = indis[key]
            # Сначала создать пользователей, потом родительские связи
            user = self.create_user(
                first_name=item['first_name'] or 'Без имени',
                owner=owner,
                dob=item['dob'],
                is_dead=item['is_dead'],
                dod=item['dod'],
                is_active=False,
                gender=item['gender'],
            )
            item.update(user_id=user.pk)

        for key in indis:
            item = indis[key]
            if item['father_xref_id']:
                user_from = User.objects.select_related('profile').get(pk=item['user_id'])
                user_to = User.objects.select_related('profile').get(pk=indis[item['father_xref_id']]['user_id'])
                self.add_operation(
                    user_from,
                    user_to.profile,
                    operationtype_id = OperationType.SET_FATHER,
                    comment = None,
                    insert_timestamp = int(time.time()),
                )
            if item['mother_xref_id']:
                user_from = User.objects.select_related('profile').get(pk=item['user_id'])
                user_to = User.objects.select_related('profile').get(pk=indis[item['mother_xref_id']]['user_id'])
                self.add_operation(
                    user_from,
                    user_to.profile,
                    operationtype_id = OperationType.SET_MOTHER,
                    comment = None,
                    insert_timestamp = int(time.time()),
                )

        user_to_merge = User.objects.select_related('profile').get(pk=indis[indi_to_merge]['user_id'])
        owner.profile.merge(user_to_merge.profile)

api_import_gedcom = ApiImportGedcom.as_view()

class ApiBotPoll(APIView):

    @transaction.atomic
    def post(self, request):
        """
        Создать телеграм опрос

        Принимает то, что отдает телеграм при создании опроса:
        {
            "message_id": 13052,
            "from": {"id": 12345, "is_bot": true, "first_name": "SevTrusts", "username": "DevBlagoBot"},
            "chat": {"id": 54321, "first_name": "Евгений", "last_name": "Фамилия", "username": "his_username", "type": "private"},
            "date": 1677680550,
            "poll": {
                "id": "987654321",
                "question": "Как дела",
                "options": [
                        {"text": "Отлично", "voter_count": 0},
                        {"text": "Хорошо", "voter_count": 0},
                        {"text": "Плохо", "voter_count": 0}
                    ],
                    "total_voter_count": 0, "is_closed": false, "is_anonymous": false, "type": "regular", "allows_multiple_answers": false
                }
        }
        Но не всё использует
        Еще в исходных данных должно быть: request.data.get('tg_token') == settings.TELEGRAM_BOT_TOKEN
        Проверок не производим: если бот правильно отдаст запрос, и здесь всё будет правильно
        """
        try:
            if request.data.get('tg_token') != settings.TELEGRAM_BOT_TOKEN:
                raise ServiceException('Неверный токен телеграм бота')
            tgpoll, created_ = TgPoll.objects.get_or_create(
                poll_id=request.data['poll']['id'],
                defaults=dict(
                    question=request.data['poll']['question'],
                    message_id=request.data['message_id'],
                    chat_id=request.data['chat']['id'],
            ))
            if created_:
                TgPollAnswer.objects.create(tgpoll=tgpoll, number=0, answer='')
                for i, option in enumerate(request.data['poll']['options']):
                    TgPollAnswer.objects.create(tgpoll=tgpoll, number=i+1, answer=option['text'])
            data = tgpoll.data_dict()
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)


    def get(self, request):
        try:
            poll_id = int(request.GET.get('poll_id'))
            tgpoll = TgPoll.objects.get(poll_id=poll_id)
            data = tgpoll.data_dict()
            status_code = status.HTTP_200_OK
        except (TypeError, ValueError, TgPoll.DoesNotExist,):
            data = {}
            status_code = status.HTTP_404_NOT_FOUND
        return Response(data=data, status=status_code)

api_bot_poll = ApiBotPoll.as_view()

class ApiBotPollAnswer(APIView):

    @transaction.atomic
    def post(self, request):
        """
        Послать или отменить голос в телеграм опросу

        {
            "poll_id": "54321",
            "user": {
                "id": 12345, "is_bot": false, "first_name": "Eugene",
                "last_name": "Surname", "username": "his_username", "language_code": "ru"
            },
            "option_ids": [0]
        }
        Принимает то, что отдает телеграм при получении голоса:
        Но не всё использует
        Еще в исходных данных должно быть: request.data.get('tg_token') == settings.TELEGRAM_BOT_TOKEN
        Проверок не производим: если бот правильно отдаст запрос, и здесь всё будет правильно
        """
        try:
            if request.data.get('tg_token') != settings.TELEGRAM_BOT_TOKEN:
                raise ServiceException('Неверный токен телеграм бота')
            try:
                tgpoll = TgPoll.objects.get(poll_id=request.data['poll_id'])
            except (KeyError, TgPoll.DoesNotExist,):
                raise ServiceException('Не найден опрос')
            try:
                oauth = Oauth.objects.get(
                    provider = Oauth.PROVIDER_TELEGRAM,
                    uid=str(request.data['user']['id']),
                )
            except (KeyError, Oauth.DoesNotExist,):
                raise ServiceException('Телеграм пользователь не найден')
            oauth.tg_poll_answers.clear()
            try:
                if request.data['option_ids']:
                    for o in request.data['option_ids']:
                        number = o + 1
                        tgpollanswer = TgPollAnswer.objects.get(tgpoll=tgpoll, number=number)
                        oauth.tg_poll_answers.add(tgpollanswer)
                else:
                    tgpollanswer = TgPollAnswer.objects.get(tgpoll=tgpoll, number=0)
                    oauth.tg_poll_answers.add(tgpollanswer)
            except (KeyError, TgPollAnswer.DoesNotExist,):
                raise ServiceException('Получен не существующий ответ')
            data = {}
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

api_bot_poll_answer = ApiBotPollAnswer.as_view()
