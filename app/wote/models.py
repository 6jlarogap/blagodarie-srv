from django.db import models

from app.models import BaseModelInsertUpdateTimestamp, BaseModelInsertTimestamp


class Video(BaseModelInsertTimestamp):

    SOURCE_YOUTUBE = 'yt'
    SOURCE_RUTUBE = 'rt'
    SOURCE_VKONTAKTE = 'vk'
    SOURCE_BASTYON = 'bn'

    VIDEO_SOURCES = (
        (SOURCE_YOUTUBE, 'Google'),
        (SOURCE_RUTUBE, 'RuTube'),
        (SOURCE_VKONTAKTE, 'ВКонтакте'),
        (SOURCE_BASTYON, 'Bastyon'),
    )

    creator = models.ForeignKey('auth.User', verbose_name='Владелец', on_delete=models.CASCADE,)
    source = models.CharField('Источник', max_length=2, choices=VIDEO_SOURCES)
    # Ссылка для авторизации через tg bot имеет вид:
    # start=wote-rt-<videoid>, не длинне 64 символов,
    # отсюда и макс длина videoid = 50
    videoid = models.CharField('Видео Id', max_length=50)

    class Meta:
        unique_together = ('source', 'videoid',)

    def data_dict(self, request=None):
        return dict(
            source=self.source,
            videoid=self.videoid,
            insert_timestamp=self.insert_timestamp,
        )

    def __str__(self):
        return '%s-%s' % (self.source, self.videoid,)

class Vote(BaseModelInsertUpdateTimestamp):

    VOTE_YES = 'yes'
    VOTE_NO = 'no'
    VOTE_NOT = 'not'

    VOTES = (
        (VOTE_YES, 'Да'),
        (VOTE_NO, 'Нет'),
        (VOTE_NOT, 'Не ясно'),
    )

    user = models.ForeignKey('auth.User', verbose_name='Пользователь', on_delete=models.CASCADE,)
    video = models.ForeignKey(Video, verbose_name='Видео', on_delete=models.CASCADE,)
    time = models.PositiveIntegerField('Время', default=0)
    button = models.CharField('Кнопка', max_length=10, choices=VOTES)

    class Meta:
        unique_together = ('user', 'video', 'time', )

    def data_dict(self, request=None, put_video=False):
        result = dict(
            user=dict(
                uuid=self.user.profile.uuid,
            ),
            time=self.time,
            button=self.button,
            insert_timestamp=self.insert_timestamp,
            update_timestamp=self.update_timestamp,
        )
        if put_video:    
            result.update(video=self.video.data_dict(request))
        return result

    def __str__(self):
        return '%s: %s-%s, %s: %s' % (
            self.user.first_name,
            self.video.source,
            self.video.videoid,
            self.time,
            self.button,
        )
