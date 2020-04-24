install-readme.txt
------------------

Установка Django проекта project на сервер Apache в Ubuntu Linux.

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
            * python3:
                  * sudo apt install python3-all-dev
                  * sudo apt install python3-virtualenv python3-pycurl virtualenv
                  * sudo apt-get install python3-matplotlib

         - postgresql,
            * в т.ч. для разработчика:
              sudo apt install postgresql postgresql-server-dev-all
            полагаем, что используется база postgresql на localhost,
            в которой пользователю postgres всё дозволено. Это достигается
            в /etc/postgresql/10/main/

            заменой строки:
                local all postgres peer
            на:
                local all postgres trust
            с перезагрузкой postgresql (service postgresql restart)

         - web сервер apache2:
            sudo apt install apache2  apache2-utils

         -git
            sudo apt install git

    * Должен быть запущен postgresql сервер

    * mkdir ~/venv; cd ~/venv
    * virtualenv -p `which python3` project
    *   sudo mkdir -p /home/www-data/django/
        cd /home/www-data/django/
        sudo mkdir -p MEDIA/project
        sudo chown USERNAME_LINUX:USERNAME_LINUX .
    * git clone https://USERNAME@github.com/USERNAME_GIT/project.git
    * cd /home/www-data/django/project
    * source ~/venv/project/bin/activate
    * pip install -r pip.txt
    * deactivate
    * cd /home/www-data/django/project/app/app
    * cp local_settings.py.example local_settings.py
    * внести правки в local_settings.py, но если необходимо.
      Например, прописать путь к медии:
          MEDIA_ROOT = '/home/www-data/django/MEDIA/project'
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
    
    * chown -R www-data:www-data ~/venv/project
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
