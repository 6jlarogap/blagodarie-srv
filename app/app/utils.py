
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
