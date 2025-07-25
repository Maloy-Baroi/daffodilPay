# digital_wallet/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from rest_framework.authentication import SessionAuthentication, TokenAuthentication

schema_view = get_schema_view(
    openapi.Info(
        title="DaffodilPay API",
        default_version='v1',
        description="Digital Wallet API Documentation",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="contact@daffodilpay.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
    authentication_classes=(SessionAuthentication, TokenAuthentication),
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('wallet.urls')),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Admin site headers
admin.site.site_header = "Digital Wallet Administration"
admin.site.site_title = "Digital Wallet Admin Portal"
admin.site.index_title = "Welcome to Digital Wallet Administration Portal"
