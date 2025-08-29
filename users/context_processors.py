from .forms import CustomSignupForm, CustomLoginForm

def auth_forms(request):
    return {
        "signup_form": CustomSignupForm(request=request),
        "login_form": CustomLoginForm(request=request),
    }
