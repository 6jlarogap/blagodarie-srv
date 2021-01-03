import datetime, time
from skyfield.api import load
from skyfield.framelib import ecliptic_frame

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

def dictfetchall(cursor):
    "Return all rows from a cursor as a dict"
    columns = [col[0] for col in cursor.description]
    return [
        dict(list(zip(columns, row)))
        for row in cursor.fetchall()
    ]

def get_moon_day(utc_time=None):
    """
    Из unix timestamp получить номер дня по лунному календарю, 0 - 27
    """

    if not utc_time:
        utc_time = int(time.time())

    ts = load.timescale(builtin=True)
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
