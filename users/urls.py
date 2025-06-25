from django.urls import path
from users.views import indexView

app_name="users"

urlpatterns=[
    path('', indexView, name='indexView'),
    path('accounts/profile', indexView, name='profileOverridenView'),
]