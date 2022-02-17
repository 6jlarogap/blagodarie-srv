#! /bin/bash

# Процедура обновления по изменении кода API

PROJECT_='/home/www-data/django/api_blagodarie_org'
APP='app'
TELEGRAM_BOT_SERVICE='telegram-bot'

TTY_=`tty`
cd "$PROJECT_/$APP"
sudo -u www-data -H git pull
sudo -u www-data ./manage.py migrate --noinput --no-color
sudo -u www-data ./manage.py loaddata fixtures.json

sudo -u www-data ./manage.py collectstatic --noinput | \
tee $TTY_ | \
egrep -i '^[1-9][0-9]* static files? copied' > /dev/null && \
echo 'Static file(s) changed. Touching static folder.' && \
sudo -u www-data touch static

sudo service apache2 reload

echo ""
sudo service $TELEGRAM_BOT_SERVICE status > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Restart $TELEGRAM_BOT_SERVICE"
    sudo service $TELEGRAM_BOT_SERVICE restart && echo "... restarted" || echo "... FAILED to restart"
else
    echo "$TELEGRAM_BOT_SERVICE not running. Not restarting it"
fi
