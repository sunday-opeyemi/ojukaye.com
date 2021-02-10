from pathlib import Path
import os
# Import socket to read host name
import socket

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
# BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '*t*0ir%p)p%=17%l4ho$$l%85e3&3^(5r9vonkufc%462lrsn&'

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'ojukaye.newsapp',
    'ojukaye.userportalapp',
    'ojukaye.adminapp',
    'bootstrapform',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'ojukaye.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['%s/templates/' % (PROJECT_DIR),],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ojukaye.wsgi.application'

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# If the host name starts with 'live', DJANGO_HOST = "production"
if socket.gethostname().startswith('live'):
    DJANGO_HOST = "production"
# Else if host name starts with 'test', set DJANGO_HOST = "test"
elif socket.gethostname().startswith('test'): 
    DJANGO_HOST = "testing"
else:
# If host doesn't match, assume it's a development server, set DJANGO_HOST = "development"
    DJANGO_HOST = "development"

# Define general behavior variables for DJANGO_HOST and all others
if DJANGO_HOST == "production":
    # SECURITY WARNING: don't run with debug turned on in production!
    DEBUG = False

    ALLOWED_HOSTS = [
        'www.ojukaye.com',
    ]

    # Database
    # https://docs.djangoproject.com/en/3.1/ref/settings/#databases

    DATABASES = {
        'default': {
            'ENGINE': 'mysql.connector.django',
            'NAME': 'sundayopeyemi$ojukaye',
            'USER': 'sundayopeyemi',
            'PASSWORD': 'sundayschool',
            'HOST': 'sundayopeyemi.mysql.pythonanywhere-services.com',
            'PORT': '3306',
            'OPTIONS': {
                'autocommit': True,
            },
        }
    }

    # Define EMAIL_BACKEND variable for DJANGO_HOST
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.gmail.com' # mail service smtp
    EMAIL_HOST_USER = 'sunday.opeyemi2018@gmail.com' # email id
    EMAIL_HOST_PASSWORD = 'sundayschool123' #password
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True

else: 
    # SECURITY WARNING: don't run with debug turned on in production!
    DEBUG = True

    ALLOWED_HOSTS = [ ]
    
    # Database
    # https://docs.djangoproject.com/en/3.1/ref/settings/#databases

    DATABASES = {
        'default': {
            'ENGINE': 'mysql.connector.django',
            'NAME': 'ojukaye',
            'USER': 'root',
            'PASSWORD': '',
            'HOST': '127.0.0.1',                     
            'PORT': '3306',
            'OPTIONS': {
                'autocommit': True,
            },   
        }
    }
    if DJANGO_HOST == "testing":
        # Nullify output on DJANGO_HOST test
        EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
    else:
        # Output to console for all others
        EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'# Import socket to read host name
    
# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

STATIC_URL = '/static/'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
MEDIA_URL = 'media/'

LOGIN_REDIRECT_URL = 'homenewsfeed'
LOGOUT_REDIRECT_URL = 'index'
