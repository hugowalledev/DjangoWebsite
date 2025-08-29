from allauth.account.forms import SignupForm, LoginForm 

class CustomSignupForm(SignupForm):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)  # remove request from kwargs
        super().__init__(*args, **kwargs)

class CustomLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
