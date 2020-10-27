import os, re, hmac, hashlib, json
import urllib.request, urllib.error

from django.shortcuts import render
from django.db import transaction, IntegrityError, connection
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.query_utils import Q

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

from app.utils import ServiceException, dictfetchall

from django.contrib.auth.models import User
from users.models import Oauth, CreateUserMixin, IncognitoUser, Profile
from contact.models import Key, KeyType, CurrentState, OperationType

class ApiGetProfileInfo(APIView):

    def get(self, request):
        """
        Получение информации о профиле пользователя

        Возвращает информацию о пользователе, заданным get- параметром
        uuid: ФИО, кредитную карту, фото, известность,
        общее количество благодарностей, количество утрат доверия.
        Если в запросе присутствует токен авторизации, то нужно вернуть и
        текущее состояние между пользователем, который запрашивает информацию,
        и пользователем, о котором он запрашивает информацию.
        То есть информацию из таблицы CurrentState,
        где user_id_from = id_пользователя_из_токена,
        а user_id_to = id_пользователя_из_запроса.
        Если в CurrentState нет записи по заданным пользователям,
        то возвратить thanks_count = null и is_trust = null.
        Также нужно возвратить массив пользователей (их фото и UUID),
        которые благодарили, либо были благодаримы пользователем,
        о котором запрашивается информация.
        Массив пользователей должен быть отсортирован по убыванию
        известности пользователей.

        Пример вызова:
        /api/getprofileinfo?uuid=9e936638-3c48-4e7b-bab4-7f968824acd5

        Пример возвращаемых данных:
        {
            "first_name": "Иван",
            "middle_name": "Иванович",
            "last_name": "Иванов",
            "photo": "photo/url",
            "sum_thanks_count": 300,
            "fame": 3,
            "trustless_count": 1,
            "thanks_count": 12, // только при авторизованном запросе
            "is_trust": true,   // только при авторизованном запросе
            "thanks_users": [
                {
                "photo": "photo/url",
                "user_uuid": "6e14d54b-9371-431f-8bf0-6688f2cf2451"
                },
                {
                "photo": "photo/url",
                "user_uuid": "5548a8ba-ac47-400e-96f3-f3c9caa75383"
                },
                {
                "photo": "photo/url",
                "user_uuid": "7ced71b2-3b55-45bf-a622-57311dbc6c9f"
                }
            ]
        }

        """

        try:
            uuid=request.GET.get('uuid')
            if not uuid:
                raise ServiceException("Не задан uuid")
            try:
                profile = Profile.objects.select_related('user').get(uuid=uuid)
            except (ValidationError, Profile.DoesNotExist, ):
                raise ServiceException("Не найден пользователь с uuid = %s или uuid неверен" % uuid)
            user = profile.user
            data = dict(
                last_name=user.last_name,
                first_name=user.first_name,
                middle_name=profile.middle_name,
                photo=profile.choose_photo(),
                sum_thanks_count=profile.sum_thanks_count,
                fame=profile.fame,
                trustless_count=profile.trustless_count,
            )
            user_from = request.user
            if user_from.is_authenticated:
                thanks_count = is_trust = None
                try:
                    currentstate = CurrentState.objects.get(
                        user_from=user_from,
                        user_to=user,
                        is_reverse=False,
                    )
                    thanks_count = currentstate.thanks_count
                    is_trust = currentstate.is_trust
                except CurrentState.DoesNotExist:
                    pass
                data.update(
                    thanks_count=thanks_count,
                    is_trust=is_trust,
                )
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_get_profileinfo = ApiGetProfileInfo.as_view()

class ApiUpdateProfileInfo(APIView):
    permission_classes = (IsAuthenticated, )
    parser_classes = (FormParser, MultiPartParser, JSONParser,)

    @transaction.atomic
    def post(self, request, signin=False):
        """
        Обновить информацию о пользователе

        Пока только credit_card
        """
        try:
            credit_card = request.data.get('credit_card')
            if credit_card:
                keytype = KeyType.objects.get(pk=KeyType.CREDIT_CARD_ID)
                key, created_ = Key.objects.get_or_create(
                    owner=request.user,
                    type=keytype,
                    defaults=dict(
                        value=credit_card,
                ))
                if not created_:
                    key.value = credit_card
                    key.save(update_fields=('value',))
            status_code = 200
            data = dict()
        except ServiceException as excpt:
            transaction.set_rollback(True)
            status_code = 400
            data = dict(message=excpt.args[0])
        return Response(data=data, status=status_code)

api_update_profileinfo = ApiUpdateProfileInfo.as_view()

class ApiAuthSignUp(CreateUserMixin, APIView):
    """
    Регистрация (signup) или вход пользователя в систему

    Исходные данные
    {
    "oauth": {
        "provider":"google",
        "id":"234234234234234231413",
        "token":"ajjjkelr8k4234msfsdf898fs6fs3sd8"
        },
        "user_uuid": "6e14d54b-9371-431f-8bf0-6688f2cf2451"
                //  только для signin. Будет проверка,
                //  что существующий в системе пользователь
                //  имеет тот же uuid
    }
    Возвращает JSON:
    {
        "user_uuid":"6e14d54b-9371-431f-8bf0-6688f2cf2451",
        "token":"po4r4i9340tut4093uirf9340fi9340it"
    }
    """
    
    @transaction.atomic
    def post(self, request, signin=False):
        signup = not signin
        try:
            if signin:
                user_uuid = request.data.get('user_uuid')
                if not user_uuid:
                    status_code = 400
                    raise ServiceException('Не задан user_uuid')

            oauth_dict = request.data.get("oauth")
            if not oauth_dict:
                raise ServiceException("Не задан oauth")
            oauth_result = Oauth.check_token(oauth_dict)
            if oauth_result['message']:
                status_code = oauth_result['code']
                raise ServiceException(oauth_result['message'])
            try:
                oauth = Oauth.objects.get(
                    provider=oauth_dict['provider'],
                    uid=oauth_result['uid'],
                )
            except Oauth.DoesNotExist:
                oauth = None

            user = None
            if oauth:
                user = oauth.user
            else:
                key_type_title = oauth_result.get('key_type_title')
                key_owner = None
                if key_type_title:
                    try:
                        user = key_owner = Key.objects.get(
                            type__title=key_type_title,
                            value=oauth_result['uid'],
                            owner__isnull=False,
                        ).owner
                        # Если существует пользователь с таким ключом,
                        # то что при signup регистрируем, а при
                        # signin проверяем user_uuid
                    except Key.DoesNotExist:
                        pass
                if signup:
                    if not user:
                        user = self.create_user(
                            last_name=oauth_result.get('last_name', ''),
                            first_name=oauth_result.get('first_name', ''),
                            email=oauth_result.get('email', ''),
                        )
                        if not user:
                            raise ServiceException(CreateUserMixin.MSG_FAILED_CREATE_USER)
                    if key_type_title and not key_owner:
                        try:
                            keytype = KeyType.objects.get(title=key_type_title)
                            Key.objects.create(
                                owner=user,
                                type=keytype,
                                value=oauth_result['uid'],
                            )
                        except KeyType.DoesNotExist:
                            pass
            if signin:
                if user:
                    if str(user.profile.uuid) != user_uuid:
                        status_code = 401
                        raise ServiceException('Не совпадает user_uuid')
                else:
                    status_code = 401
                    raise ServiceException('Не найден пользователь c таким Id от %s' % oauth_dict['provider'])

            if not oauth:
                # Даже при signin, если user есть в ключах,
                # возможно его нет в oauth
                oauth = Oauth.objects.create(
                    provider=oauth_dict['provider'],
                    uid=oauth_result['uid'],
                    user=user,
                )
            token, created_ = Token.objects.get_or_create(user=user)
            data = dict(token=token.key,)
            if signup:
                self.update_oauth(oauth, oauth_result)
                data.update(
                    user_uuid=str(user.profile.uuid),
                    last_name=user.last_name,
                    first_name=user.first_name,
                    middle_name=user.profile.middle_name,
                    photo=user.profile.choose_photo(),
                )
            status_code = 200
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            if status_code == 200:
                status_code = 400
        return Response(data=data, status=status_code)

api_auth_signup = ApiAuthSignUp.as_view()

class ApiAuthDummy(APIView):

    def get(self, request):
        data = {
            "iss": "https://accounts.google.com",
            "azp": "dummy",
            "aud": "dummy",
            "sub": "100407860688573256455",
            "email": "someone@gmail.com",
            "email_verified": "true",
            "name": "dummy",
            "picture": "https://lh5.googleusercontent.com/dummy/photo3.jpg",
            "given_name": "Сергей",
            "family_name": "Неизвестный",
            "locale": "ru",
            "iat": "1587538141",
            "exp": "1587541741",
            "alg": "RS256",
            "kid": "dummy",
            "typ": "JWT"
        }
        return Response(data=data, status=200)

api_auth_dummy = ApiAuthDummy.as_view()

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

class ApiGetUsers(APIView):

    def post(self, request):
        """
        Получение списка пользователей

        Возвращает список пользователей.
        Пользователи должны быть отфильтрованы по filter.text.
        Совпадения необходимо искать в first_name и last_name без учета регистра
        (типо такого: ...WHERE first_name LIKE ‘%’+filter+’%’ or last_name LIKE ‘%’+filter+’%’).
        Пользователи должны быть отсортированы по алфавиту сначала
        по last_name потом по first_name
        (... ORDER BY last_name ASK, first_name ASK).
        Filter.text может быть пустым, тогда нужно вернуть всех пользователей.
        Нужно вернуть count записей начиная с записи from

        Пример вызова:
        {
            "filter": {
                "text": "ivan"
            },
            "from": 2,
            "count": 34
        }

        Пример возвращаемых данных:
            {
            "users": [
                {
                "uuid": "9d2f21b3-2401-43e9-8409-eb3bcb780fe9",
                "last_name": "Ivanov",
                "first_name": "Ivan",
                "photo": "/url/photo",
                "fame": 32,
                "sum_thanks_count": 32,
                "trustless_count": 12
                },
            ...
            ]
        }
        """

        try:
            text = ""
            try:
                text = request.data.get('filter', {})['text']
            except KeyError:
                raise ServiceException("Не задан filter.text")
            q = Q(is_superuser=False)
            if text:
                q &= Q(last_name__icontains=text) | Q(first_name__icontains=text)
            qs = User.objects.filter(q).select_related('profile').distinct(
                ).order_by('last_name', 'first_name',)
            from_ = request.data.get("from", 0)
            count = request.data.get("count")
            if count:
                qs = qs[from_ : from_ + count]
            else:
                qs = qs[from_:]
            users = []
            for user in qs:
                profile = user.profile
                users.append(dict(
                    uuid=profile.uuid,
                    last_name=user.last_name,
                    first_name=user.first_name,
                    photo=profile.choose_photo(),
                    fame=profile.fame,
                    sum_thanks_count=profile.sum_thanks_count,
                    trustless_count=profile.trustless_count,
                ))
            data = dict(users=users)
            status_code = 200
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = 400
        return Response(data=data, status=status_code)

api_get_users = ApiGetUsers.as_view()
