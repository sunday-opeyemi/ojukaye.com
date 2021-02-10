from django import forms

class Saysomething_form(forms.Form):
    userpost = forms.CharField(max_length=5000, label='', widget=forms.TextInput(
        attrs={'placeholder': 'What would you like to say?'}))
              
class Addmedia_form(forms.Form):
    userpost = forms.CharField(max_length=5000, label='', widget=forms.TextInput(
        attrs={'placeholder': 'Add some comments'}))
    picture = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'multiple': True}), max_length=5000)
    video = forms.FileField(required=False)
    audio = forms.FileField(required=False)

class Reply_form(forms.Form):
    comment = forms.CharField(widget=forms.Textarea())
    picture = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'multiple': True}), max_length=2000)
    video = forms.FileField(required=False)
    audio = forms.FileField(required=False)
