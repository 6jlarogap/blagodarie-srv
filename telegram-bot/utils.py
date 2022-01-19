import base64

import aiohttp
import asyncio

import settings

TIMEOUT = aiohttp.ClientTimeout(total=settings.HTTP_TIMEOUT)

class OperationType(object):
    THANK = 1
    MISTRUST = 2
    TRUST = 3
    NULLIFY_TRUST = 4
    TRUST_AND_THANK = 5

class KeyboardType(object):
    """
    Варианты клавиатур и служебный символ для call back data из кнопок клавиатур
    """
    # Багодарность, доверие, недоверие...
    #
    TRUST_THANK = 1

    # Разделитель данных в call back data
    #
    SEP = '~'

async def get_user_photo(bot, user):
    """
    Получить фото пользователя, base64-строку, фото размером не больше settings.PHOTO_MAX_SIZE, если возможно
    """
    result = None
    if not user:
        return result

    photos_output = await user.get_profile_photos()

    # Вытащить отсюда фото размером не больше settings.PHOTO_MAX_SIZE
    # Если несколько фоток, берм 1-е
    #[
    #('total_count', 1),
    #('photos', 
        #[
            #[
            #{'file_id': 'xxxAgACAgIAAxUAAWHMS13fLk09JXvGPzvJugABH-CbPQACh7QxG9OhYUv54uiD8-vioQEAAwIAA2EAAyME',
            #'file_unique_id': 'AQADh7QxG9OhYUsAAQ', 'file_size': 8377, 'width': 160, 'height': 160},
            #{'file_id': 'AgACAgIAAxUAAWHMS13fLk09JXvGPzvJugABH-CbPQACh7QxG9OhYUv54uiD8-vioQEAAwIAA2IAAyME',
            #'file_unique_id': 'AQADh7QxG9OhYUtn', 'file_size': 26057, 'width': 320, 'height': 320},
            #{'file_id': 'AgACAgIAAxUAAWHMS13fLk09JXvGPzvJugABH-CbPQACh7QxG9OhYUv54uiD8-vioQEAAwIAA2MAAyME',
            #'file_unique_id': 'AQADh7QxG9OhYUsB', 'file_size': 80575, 'width': 640, 'height': 640}
            #]
        #]
    #)
    #]

    file_id = None
    first = True
    for o in photos_output:
        if o[0] == 'photos':
            for p in o[1]:
                for f in p:
                    if first:
                        file_id = f['file_id']
                        first = False
                    elif f.get('width') and f.get('height') and f['width'] * f['height'] <= settings.PHOTO_MAX_SIZE:
                        file_id = f['file_id']
                break
    if file_id:
        photo_path = await bot.get_file(file_id)
        photo_path = photo_path and photo_path.file_path or ''
        photo_path = photo_path.rstrip('/') or None
    else:
        photo_path = None

    if photo_path:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.get(
                "https://api.telegram.org/file/bot%s/%s" % (settings.TOKEN, photo_path,),
            ) as resp:
                try:
                    status = int(resp.status)
                    if status == 200:
                        result = base64.b64encode(await resp.read()).decode('UTF-8')
                except ValueError:
                    pass
    return result

async def api_request(
        path,
        method='GET',
        data=None,
        json=None,
        response_type='json',
    ):
    """
    Запрос в апи.
    
    Если задана data, то это передача формы.
    Если задан json, то это json- запрос
    Ответ в соответствии с response_type:
        'json' или 'text'
    """
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        async with session.request(
            method.upper(),
            "%s%s" % (settings.API_HOST, path,),
            data=data,
            json=json,
        ) as resp:
            status = resp.status
            if response_type == 'json':
                response = await resp.json()
            elif response_type == 'text':
                response = await resp.text('UTF-8')
            return status, response
