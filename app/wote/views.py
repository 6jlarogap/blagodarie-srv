import time

from django.db import transaction
from django.db.models import Count

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated

from app.utils import ServiceException

from wote.models import Video, Vote

class ApiWoteVideoMixin(object):

    def check_input_video(self, request):
        if not request.data.get('source') or \
            request.data['source'] not in dict(Video.VIDEO_SOURCES) or \
            not request.data.get('videoid'):
            raise ServiceException('Не задан(ы) или не верн(ы) параметры source, videoid')


class ApiWoteVote(ApiWoteVideoMixin, APIView):

    @transaction.atomic
    def post(self, request):
        """
        Отдать голос для видео. Требует аутентификации.

        Аутентификация достигается передачей вместе с запросом
        заголовка Authorization: Token <auth_token из куки auth_datа>

        http(s)://<api-host>/api/wote/vote/
        Post запрос. На входе json. Например:
        {
            // video source: возможны yt, rt, vk, bn.
            // И ничто другое, кроме как в ./models.py:Video.VIDEO_SOURCES
            "source": "yt",
            "videoid": "Ac5cEy5llr4",
            
            // Название кнопки: возможны yes, no, not
            // И ничто другое, кроме как в ./models.py:Vote.VOTES
            "button": "yes",

            // Время от старта видео
            "time": 50,
        }
        Если видео с source, videoid не существует, то создается.
        Если успешно, возвращает json {}, статус: HTTP_200_OK

        Если запрос анонимный, то статус ответа HTTP_401_UNAUTHORIZED
        Если ошибка в переданных параметрах source, videoid, time,
        то статус HTTP_400_BAD_REQUEST,
        текст json: { "message": "<сообщение об ошибке>" }
        """
        if not request.user.is_authenticated:
            raise NotAuthenticated
        try:
            self.check_input_video(request)

            if not (button :=  request.data.get('button')) or \
               button not in dict(Vote.VOTES):
                raise ServiceException('Не задан или не верен параметры button')
            err_mes_time = 'Не задан или не верен параметр time'
            try:
                time_ = int(request.data.get('time'))
            except (TypeError, ValueError):
                raise ServiceException(err_mes_time)
            if time_ < 0:
                raise ServiceException(err_mes_time)

            video, created_video = Video.objects.get_or_create(
                source=request.data['source'],
                videoid=request.data['videoid'],
                defaults=dict(creator=request.user),
            )
            vote, created_vote = Vote.objects.select_for_update().get_or_create(
                user=request.user,
                video=video,
                time=time_,
                defaults=dict(button=button)
            )
            if not created_vote:
                vote.update_timestamp = int(time.time())
                vote.button = button
                vote.save(update_fields=('update_timestamp', 'button',))
            data = {}
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            transaction.set_rollback(True)
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

    def delete(self, request):
        """
        Удалить голос для видео. Требует аутентификации.

        Аутентификация достигается передачей вместе с запросом
        заголовка Authorization: Token <auth_token из куки auth_datа>

        http(s)://<api-host>/api/wote/vote/
        Delete запрос. На входе json. Например:
        {
            // video source: возможны yt, rt, vk, bn.
            // И ничто другое, кроме как в ./models.py:Video.VIDEO_SOURCES
            "source": "yt",
            "videoid": "Ac5cEy5llr4",
            
            // Время от старта видео
            "time": 50,
        }
        Если успешно, возвращает json {}, статус: HTTP_200_OK

        Если запрос анонимный, то статус ответа HTTP_401_UNAUTHORIZED
        Если не найдено видео или не найден такой голос этого юзера или
        если ошибка в переданных параметрах source, videoid, time,
        то статус HTTP_400_BAD_REQUEST,
        текст json: { "message": "<сообщение об ошибке>" }
        """
        if not request.user.is_authenticated:
            raise NotAuthenticated
        try:
            self.check_input_video(request)
            try:
                vote = Vote.objects.get(
                    user=request.user,
                    video__source=request.data['source'],
                    video__videoid=request.data['videoid'],
                    time=int(request.data['time']),
                )
            except (TypeError, ValueError, KeyError, Vote.DoesNotExist, ):
                raise ServiceException('Не найдено видео или голос')
            vote.delete()
            data = {}
            status_code = status.HTTP_200_OK
        except ServiceException as excpt:
            data = dict(message=excpt.args[0])
            status_code = status.HTTP_400_BAD_REQUEST
        return Response(data=data, status=status_code)

    def get(self, request):
        '''
        Показать все голоса по видео.

        Get запрос. Например:
        http(s)://<api-host>/api/wote/vote/?source=yt&videoid=Ac5cEy5llr4

        Возвращает json (пример):
        {
            "video": {
                "source": "yt",
                "videoid": "Ac5cEy5llr4",
                "insert_timestamp": 1684751776
            },
            "votes": [
                {
                    "user": {
                        "uuid": "8f686101-c5a2-46d0-a5ee-ffffffffffff"
                    },
                    "time": 40,
                    "button": "no",
                    "insert_timestamp": 1684751776,
                    "update_timestamp": 1685527009
                },
                ...
            ],
            "users": [
                {
                    "uuid": "8f686101-c5a2-46d0-a5ee-ffffffffffff",
                    "first_name": "Иван Иванов",
                    "photo": "https://path/to/photo.jpg"
                }
            ]
        }
        Возвратит json { "video": null, "votes": [], "users": [] } со статусом 404,
        если не заданы или заданы неверные source, videoid,
        или не найдено видео с source, videoid.
        '''
        
        votes = []
        users = []
        try:
            video = Video.objects.get(
                source=request.GET.get('source', ''),
                videoid=request.GET.get('videoid', ''),
            )
        except Video.DoesNotExist:
            status_code = status.HTTP_404_NOT_FOUND
            video_dict = None
        else:
            video_dict = video.data_dict(request)
            user_pks = []
            for vote in Vote.objects.select_related(
                    'user', 'user__profile'
                ).filter(video=video).order_by('time'):
                votes.append(vote.data_dict(request, put_video=False))
                if vote.user.pk not in user_pks:
                    user_pks.append(vote.user.pk)
                    users.append(dict(
                        uuid=vote.user.profile.uuid,
                        first_name=vote.user.first_name,
                        photo=vote.user.profile.choose_photo(request) if request else '',
                    ))
            status_code = status.HTTP_200_OK
        data = dict(video=video_dict, votes=votes, users=users)
        return Response(data=data, status=status_code)

api_wote_vote = ApiWoteVote.as_view()

class ApiWoteVoteSums(APIView):

    def get(self, request):
        '''
        Показать суммы голосов по видео по каждой кнопке по времени ее нажатия.

        Get запрос. Например:
        http(s)://<api-host>/api/wote/vote/sums/?source=yt&videoid=Ac5cEy5llr4

        Возвращает json (пример):
        {
            // Обозначения кнопок
            "yes": [
                { "time": 42, "count": 1 },
                { "time": 50, "count": 2 }
            ],
            "no": [
                { "time": 10, "count": 2 }
            ],
            "not": [
                { "time": 20, "count": 3 }
            ]
        }
        Если видео не найдено, или нет голосов по существующему видео,
        то результат: { "yes": [], "no": [], "not": [] }
        '''

        data = dict()
        for button in dict(Vote.VOTES):
            data[button] = []
        # В Django annotate + distinct not implemented.
        # Так что такой ход. Это один запрос в базу
        distinct_votes = Vote.objects.filter(
                video__source=request.GET.get('source', ''),
                video__videoid=request.GET.get('videoid', '')
            ).distinct('user', 'time', 'button')
        for rec in Vote.objects.values(
                'time', 'button'
           ).annotate(count=Count('id')
           ).filter(id__in=distinct_votes
           ).order_by('time'):
            try:
                data[rec['button']].append(dict(time=rec['time'], count=rec['count']))
            except KeyError:
                # fool proof: вдруг какие кнопки будут удалены из системы?
                pass
        return Response(data=data, status=status.HTTP_200_OK)

api_wote_vote_sums = ApiWoteVoteSums.as_view()
