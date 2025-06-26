from allauth.account.forms import LoginForm, SignupForm

def auth_forms(request):
    return {
        'login_form': LoginForm(),
        'signup_form': SignupForm(),
    }