"""
URL configuration for f2c project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path

from .api import api

# Admin branding. templates/admin/base_site.html renders site_header beside the brand
# badge, so this is the wordmark in the header rather than just a page title.
admin.site.site_header = 'Cultivators Collective'
admin.site.site_title = 'Cultivators Collective admin'
admin.site.index_title = 'Members and access'

urlpatterns = [
    path('admin/', admin.site.urls),
    # All page rendering lives in the Next.js frontend; Django serves JSON only.
    path('api/', api.urls),
]

# Club document PDFs, when no blob container is configured and they are on disk.
# Development only: runserver's static handler is the only thing serving them,
# and a deployment either has a container behind the CDN or a web server on this
# path. See the storage settings and documents/storage.py.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
