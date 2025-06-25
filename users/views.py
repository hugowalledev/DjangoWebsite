from django.shortcuts import render
from django.http import HttpResponse

def indexView(request):
   if request.user.is_authenticated:
      return HttpResponse("""
         <span style='color: green;'>Logged in</span>
         """)
   else:
      return HttpResponse("""
         <span style='color: red;'>Not logged in</span>
         """)