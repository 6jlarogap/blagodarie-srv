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

    def get_frontend_url(self, path='', ending_slash='/'):
        """
        Получить полный путь к path на front-end
        """
        fe_site = settings.FRONTEND_ROOT.rstrip('/')
        fe_path = path.strip('/')
        if not fe_path:
            ending_slash = ''
        return "%(fe_site)s/%(fe_path)s%(ending_slash)s" % dict(
            fe_site=fe_site,
            fe_path=fe_path,
            ending_slash=ending_slash,
        )

    def get_frontend_name(self):
        """
        Получить полный путь к path на front-end
        """
        return re.sub(r'\:\d+$', '',
            re.sub(r'^https?://', '', settings.FRONTEND_ROOT.rstrip('/'))
        )
