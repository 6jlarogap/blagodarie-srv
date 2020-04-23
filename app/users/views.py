from django.shortcuts import render
from django.db import IntegrityError, transaction, connection
from django.contrib.auth import login, logout, authenticate

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from app.utils import ServiceException

from users.models import Oauth, CreateUserMixin
from contact.models import Key, KeyType

class ApiAuthSignUp(CreateUserMixin, APIView):
    """
    Регистрация пользователя

    Исходные данные
    {
    "oauth": {
        "provider":"google",
        "id":"234234234234234231413",
        "token":"ajjjkelr8k4234msfsdf898fs6fs3sd8"
    }
    Возвращает JSON:
    {
        "user_id":2,
        "token":"po4r4i9340tut4093uirf9340fi9340it"
    }
    """
    
    @transaction.atomic
    def post(self, request):
        try:
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
                    except Key.DoesNotExist:
                        pass
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
            if not oauth:
                oauth = Oauth.objects.create(
                    provider=oauth_dict['provider'],
                    uid=oauth_result['uid'],
                    user=user,
                )
            self.update_oauth(oauth, oauth_result)
            token, created_ = Token.objects.get_or_create(user=user)
            data = dict(
                user_id=user.pk,
                token=token.key,
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
            "sub": "115029697887025630610",
            "email": "someone@gmail.com",
            "email_verified": "true",
            "name": "dummy",
            "picture": "https://lh5.googleusercontent.com/dummy/photo.jpg",
            "given_name": "Сергей",
            "family_name": "dummy",
            "locale": "ru",
            "iat": "1587538141",
            "exp": "1587541741",
            "alg": "RS256",
            "kid": "dummy",
            "typ": "JWT"
        }
        return Response(data=data, status=200)

api_auth_dummy = ApiAuthDummy.as_view()
