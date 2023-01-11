install-readme.txt
------------------

Установка Django проекта project на сервер Apache в Ubuntu Linux.
----------------------------------------------------------------

    (Здесь каталог app)

    * Полагаем:

        Пусть project - это:

            - имя проекта на github.com
                Полагаем, что проект там хранится. Возможен другой ресурс,
                например, bitbucket.org
            - имя каталога кода проекта
            - имя каталога медии проекта (загружаемых данных пользователями сайта):
                /home/www-data/django/MEDIA/project
            - имя базы данных проекта
            - имя сайта: project.org
            - каталог, где сертификаты на сайт https://project.org,
                /home/www-data/ssl-certificates/sslforfree/project.org/
              получаемые от https://www.sslforfree.com/
        
        - ~/venv/project:        
                                        virtual environment проекта.
                                        Пусть будет в домашнем каталоге установщика.

        - /home/www-data/django/project:
                                        код проекта

        - /home/www-data/django/MEDIA/project:
                                        медиа проекта (загружаемые пользователями данные)

        - USERNAME_GIT:                 имя пользователя на github.com:
                                        ресурсе, где хранится git копия проекта

        - USERNAME_LINUX                имя пользователя в ОС Linux

        - ubuntu:                       ubuntu server 18.04
 
    * Д.б. установлено на Linux:
        - средства разработки:
            * python3.6, не ниже:
                  * sudo apt install python3-all-dev
                  * sudo apt install python3-virtualenv python3-pycurl virtualenv

         - postgresql,
            * в т.ч. для разработчика:
              sudo apt install postgresql postgresql-server-dev-all
            полагаем, что используется база postgresql на localhost,
            в которой postgres- пользователь blagodarie будет владельцем
            базы данных blagodarieвсё дозволено. Это достигается в

            /etc/postgresql/<версия-postgresql>/main/

            добавлением строки в начале:
                local all blagodarie password
            с перезагрузкой postgresql (service postgresql restart)
            sudo -u postgres psql -U postgres
            CREATE USER blagodarie CREATEDB;
            ALTER USER blagodarie WITH PASSWORD 'пароль';
            \q
                пароль должен быть в local_settings.py, в
                DATABASE['default']['password']
            createdb -U blagodarie blagodarie_dev

         - web сервер apache2:
            sudo apt install apache2  apache2-utils

         - redis-server:
            для кэшировния запросов к апи

         -git
            sudo apt install git

    * Должен быть запущен postgresql сервер

    * mkdir -p ~/venv; cd ~/venv
    * virtualenv -p `which python3` project
    *   sudo mkdir -p /home/www-data/django/
        cd /home/www-data/django/
        sudo mkdir -p MEDIA/project
        sudo chown USERNAME_LINUX:USERNAME_LINUX .
    * git clone https://USERNAME@github.com/USERNAME_GIT/project.git
    * cd /home/www-data/django/project
    * source ~/venv/project/bin/activate
    * pip install -r pip-app.txt
    * deactivate
    * cd /home/www-data/django/project/app/app
    * cp local_settings.py.example local_settings.py
    * внести правки в local_settings.py, в особенности:
        ! SECRET_KEY = '50-значный случайный набор ascii- символов'
        - MEDIA_ROOT = '/home/www-data/django/MEDIA/project'
        - возможно, надо поправить и другие настройки
    * cd /home/www-data/django/project
      ln -s /home/LINUX-USER-NAME/venv/project ENV
            : virtual env, запускаемое из ./manage.py

    *   Инициализация базы данных и статических файлов для Apache
        createdb -U postgres project
        ./manage.py migrate
        ./manage.py createsuperuser
        ./manage.py collectstatic
    
    !!! Проверим работу сервера разработчика:
        cd /home/www-data/django/project/app
        ./manage.py runserver 0.0.0.0:8000
            http://site.name:8000 : что-то должно быть
        Ctrl-C
    
    * Загрузка данных для вычисления фаз луны
        cd /home/www-data/django/project/app
        ./manage.py shell
        load.timescale(builtin=False)
        load('de421.bsp')
        exit()

    * chown -R www-data:www-data ~/venv/project
      chmod 0600 /home/www-data/django/project/app/local_settings.py
      chown -R www-data:www-data /home/www-data/django/project
      chown -R www-data:www-data /home/www-data/django/MEDIA/project

Настройка сервера Apache:

    * Должны быть установлены mod_wsgi и mod_xsendfile.
        sudo apt install libapache2-mod-wsgi-py3

    * sudo a2enmod ssl rewrite wsgi

    * пример настройки виртуального хоста Apache

    <VirtualHost *:80>
        ServerName project.org

        # Здесь, в папку /.well-known/acme-challenge/,
        # кладем контрольные файлы при формировании
        # сертификатов от https://www.sslforfree.com/.
        # При любом другом запросе, нежели
        # в /.well-known/acme-challenge/,
        # идем на htps://
        #
        DocumentRoot /home/www-data/ssl-for-free
        <Directory /home/www-data/ssl-for-free>
            Require all granted
        </Directory>

        RewriteEngine On
        RewriteCond %{REQUEST_URI} !^/\.well-known/acme-challenge/
        RewriteRule (.*) https://%{HTTP_HOST}%{REQUEST_URI}
    </VirtualHost>

    <VirtualHost *:443>

        ServerName project.org

        SSLEngine on
        SSLProtocol all -SSLv2
        SSLCipherSuite ALL:!ADH:!EXPORT:!SSLv2:RC4+RSA:+HIGH:+MEDIUM

        SSLCertificateFile /home/www-data/ssl-certificates/sslforfree/project.org/certificate.crt
        SSLCertificateKeyFile /home/www-data/ssl-certificates/sslforfree/project.org/private.key
        SSLCertificateChainFile /home/www-data/ssl-certificates/sslforfree/project.org/ca_bundle.crt

        Alias /media/           /home/www-data/django/MEDIA/project/
        <Directory /home/www-data/django/MEDIA/project/>
            Require all granted
        </Directory>

        <IfModule mod_deflate.c>
            AddOutputFilterByType DEFLATE application/json
        </IfModule>

        Alias /static/          /home/www-data/django/project/app/static/
        <Directory /home/www-data/django/project/app/static/>
            Require all granted
        </Directory>
        Alias /robots.txt       /home/www-data/django/project/app/static/system/robots.txt

        # После maximum-request wsgi- application reloads, во избежание потребления
        # слишком много памяти. Reloads только когда wsgi- application не активно
        # и этого момента ждет graceful-timeout секунд. Если wsgi- application зависло
        # в течение deadlock-timeout, перезагружать его
        #
        WSGIDaemonProcess project.org display-name=%{GROUP} threads=16 maximum-requests=10000 graceful-timeout=7200 deadlock-timeout=60 home=/home/www-data/django/project/app

        WSGIProcessGroup  project.org
        WSGIScriptAlias / /home/www-data/django/project/app/app/wsgi.py

        # Во избежание ошибок: premature end of script headers wsgi.py
        #
        WSGIApplicationGroup %{GLOBAL}

        WSGIPassAuthorization On

        <FilesMatch "wsgi\.py$">
            Require all granted
        </FilesMatch>

    </VirtualHost>]

    * Добавить в конфигурацию (/etc/apache2/conf-enabled) .conf-файл, например,
      с именем reqtimeout.conf следующего содержания:

        # Minimize IOError request data read exeptions when posting data
        #
        # http://stackoverflow.com/questions/3823280/ioerror-request-data-read-error
        # http://httpd.apache.org/docs/2.2/mod/mod_reqtimeout.html
        #
        RequestReadTimeout header=90,MinRate=500 body=90,MinRate=500

        - выполнить sudo a2enmod reqtimeout

    * Очистка "мусора"
      В /etc/crontab такого типа строки:
          15 2 * * * www-data   cd /home/www-data/django/project/app && ./manage.py clearsessions

Установка Websockets server на сервер Apache в Ubuntu Linux.
----------------------------------------------------------------

    (Здесь каталог websockets-server)

    mkdir -p ~/venv; cd ~/venv
    virtualenv -p `which python3` websocket-server
    cd websocket-server
    source ./bin/activate
    pip install -r /путь/к/pip-websockets-server.txt
    deactivate
    sudo chown -R www-data:www-data .

    #   В git каталоге:
    cd websockets-server
    sudo ln -s /home/LINUX-USER-NAME/venv/websocket-server ENV
    sudo chown -R www-data:www-data .
    # В local_settings.py, возможно, надо подправить SERVER_PORT,
    # полагаем его 6789

    # Запуск websocket-server через systemd
    # -------------------------------------
    #
    cd /etc/systemd/system
    # Создать там файл с именем websocket-prod.service 
    [Unit]
    Description=Start websocket server for blagodarie.org
    After=network.target
    Before=apache2.service

    [Service]
    Type=simple
    Restart=always
    User=www-data
    ExecStart=/home/www-data/django/api_blagodarie_org/websockets-server/ENV/bin/python3 /home/www-data/django/api_blagodarie_org/websockets-server/websockets-server.py
    
    # /home/www-data/django/api_blagodarie_org/websockets-server/ENV/bin/python3 :
    #   путь и python в виртуальном окружении
    #
    # /home/www-data/django/api_blagodarie_org/websockets-server/websockets-server.py :
    #   исполняемый файл сервиса

    [Install]
    WantedBy=multi-user.target

    
    
    # Настройка apache2 на работу c websocket-server
    # ----------------------------------------------
    #
    # Файл конфигурации виртуального хоста apache2
    #
    <VirtualHost *:443>
        ServerName wss.blagodarie.org

        SSLEngine on
        SSLProtocol all -SSLv2
        SSLCipherSuite ALL:!ADH:!EXPORT:!SSLv2:RC4+RSA:+HIGH:+MEDIUM

        SSLCertificateFile /home/www-data/ssl-certificates/sslforfree/wildcard.blagodarie.org/certificate.crt
        SSLCertificateKeyFile /home/www-data/ssl-certificates/sslforfree/wildcard.blagodarie.org/private.key
        SSLCertificateChainFile /home/www-data/ssl-certificates/sslforfree/wildcard.blagodarie.org/ca_bundle.crt

        ProxyPass "/" "ws://127.0.0.1:6789/"
        ProxyPassReverse "/" "ws://127.0.0.1:6789/"

    </VirtualHost>

Установка Telegram Bot Server на сервер Apache в Ubuntu Linux.
----------------------------------------------------------------

    (Здесь каталог telegram-bot)

    mkdir -p ~/venv; cd ~/venv
    virtualenv -p `which python3` telegram-bot
    cd telegram-bot
    source ./bin/activate
    pip install -r /путь/к/pip-telegram-bot.txt
    deactivate
    sudo chown -R www-data:www-data .

    #   В git каталоге:
    cd telegram-bot
    sudo ln -s /home/LINUX-USER-NAME/venv/telegram-bot ENV
    sudo chown -R www-data:www-data .
    # В local_settings.py подправить параметры
    sudo chmod 0600 local_settings.py

    # Запуск telegram-bot-server через systemd
    # ----------------------------------------
    #
    cd /etc/systemd/system
    # Создать там файл с именем telegram-bot-prod.service 
    [Unit]
    Description=Start telegram-bot server for blagodarie.org
    After=network.target
    Before=apache2.service

    [Service]
    Type=simple
    Restart=always
    User=www-data
    ExecStart=/home/www-data/django/api_blagodarie_org/telegram-bot/ENV/bin/python3 /home/www-data/django/api_blagodarie_org/telegram-bot/bot_run.py
    
    # /home/www-data/django/api_blagodarie_org/telegram-bot/ENV/bin/python3 :
    #   путь и python в виртуальном окружении
    #
    # /home/www-data/django/api_blagodarie_org/telegram-bot/bot_run.py :
    #   исполняемый файл сервиса

    [Install]
    WantedBy=multi-user.target
    
    # Настройка apache2 на работу c telegram-bot
    # ------------------------------------------
    #
    # Файл конфигурации виртуального хоста apache2
    #
    <VirtualHost *:443>
        ServerName bot.blagodarie.org

        SSLEngine on
        SSLProtocol all -SSLv2
        SSLCipherSuite ALL:!ADH:!EXPORT:!SSLv2:RC4+RSA:+HIGH:+MEDIUM

        SSLCertificateFile /home/www-data/ssl-certificates/sslforfree/wildcard.blagodarie.org/certificate.crt
        SSLCertificateKeyFile /home/www-data/ssl-certificates/sslforfree/wildcard.blagodarie.org/private.key
        SSLCertificateChainFile /home/www-data/ssl-certificates/sslforfree/wildcard.blagodarie.org/ca_bundle.crt

        SSLEngine On
        SSLProxyEngine On
        # Здесь порт 3001 должен быть согласован с local_settings.py
        ProxyPass / http://127.0.0.1:3001/
        ProxyPassReverse / http://127.0.0.1:3001/

    </VirtualHost>
