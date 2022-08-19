import datetime, time, re
from skyfield.api import load
from skyfield.framelib import ecliptic_frame

from django.conf import settings

class ServiceException(Exception):
    """
    Чтобы не плодить цепочки if (try) else ... if (try) ... else
    
    Пример:
    try:
        if not condition1:
            raise ServiceException('Condition 1 failed')
        try:
            # some code
        except SomeException:
            raise ServiceException('Condition 2 failed')
        # all good, going further
    except ServiceException as excpt:
        print excpt.args[0]
    else:
        # all good
    """
    pass

class SkipException(Exception):
    """
    Чтобы обойти дальнейший код и выйти в окончание view
    
    Пример:
    try:
        data, status_code = self.func(request)
        raise SkipException
        много
                строк
                        кода
    except SkipException:
        pass
    return Response(data, status_code)
    """
    pass

class SQL_Mixin(object):
    """
    Для raw- вызовов
    """

    def dictfetchall(self, cursor):
        "Return all rows from a cursor as a dict"
        columns = [col[0] for col in cursor.description]
        return [
            dict(list(zip(columns, row)))
            for row in cursor.fetchall()
        ]

    def sql_like_value(self, s):
        """
        Escape a sring for sql like expression
        """
        return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

def get_moon_day(utc_time=None):
    """
    Из unix timestamp получить номер дня по лунному календарю, 0 - 27
    """

    if not utc_time:
        utc_time = int(time.time())

    ts = load.timescale()
    d = datetime.datetime.utcfromtimestamp(utc_time)
    t = ts.utc(d.year, d.month, d.day, d.hour, d.minute, d.second)

    eph = load('de421.bsp')
    sun, moon, earth = eph['sun'], eph['moon'], eph['earth']

    e = earth.at(t)
    _, slon, _ = e.observe(sun).apparent().frame_latlon(ecliptic_frame)
    _, mlon, _ = e.observe(moon).apparent().frame_latlon(ecliptic_frame)
    phase = (mlon.degrees - slon.degrees) % 360.0
    if phase >= 360:
        phase = phase % 360.
    elif phase < 0:
        phase = 0
    return int(phase * 30 / 360)

class FrontendMixin(object):

    def get_frontend_url(self, request, path='', ending_slash='/'):
        """
        Получить полный путь к path на front-end

        Если задан settings.FRONTEND_ROOT:
            имя хоста берем оттуда
        Иначе:
            Полагаем, что это апи вызывается по http(s)://api.some.site,
            где 'api' - обязательно
        """
        if settings.FRONTEND_ROOT:
            fe_site = settings.FRONTEND_ROOT.rstrip('/')
        else:
            host = request.get_host()
            m = re.search(r'^api\.(\S+)$', host, flags=re.I)
            if m:
                host = m.group(1).lower()
            # else
                # Затычка: frontend == backend.
                # Невозможная ситуация в реальной работе
            fe_site = '%(https)s://%(host)s' % dict(
                https='https' if request.is_secure() else 'http',
                host=host,
            )
        fe_path = path.strip('/')
        if not fe_path or '?' in path:
            ending_slash = ''
        return "%(fe_site)s/%(fe_path)s%(ending_slash)s" % dict(
            fe_site=fe_site,
            fe_path=fe_path,
            ending_slash=ending_slash,
        )

    def get_frontend_name(self, request):
        """
        Получить имя хоста front-end, без :цифры, если они есть

        Для отправки туда кук
        """
        return re.sub(r'\:\d+$', '',
            re.sub(r'^https?://', '', self.get_frontend_url(request).rstrip('/'))
        )

class ThumbnailSimpleMixin(object):

    def get_thumbnail_path(self, file_field, width=64, height=64, method='crop'):
        result = ''
        if file_field:
            try:
                result = '%s%s/%sx%s~%s~12.jpg'  % (settings.THUMBNAILS_STORAGE_BASE_PATH, 
                                                     file_field, width, height, method)
            except:
                pass
        return result
