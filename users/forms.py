from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class UserProfileForm(forms.ModelForm):
    """Form allowing users to update their personal profile information."""

    first_name = forms.CharField(
        max_length=150,
        required=True,
        label=_("First Name"),
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm',
            'placeholder': _("Enter first name"),
        })
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label=_("Last Name"),
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm',
            'placeholder': _("Enter last name"),
        })
    )
    email = forms.EmailField(
        required=True,
        label=_("Email Address"),
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm',
            'placeholder': _("Enter email address"),
        })
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if not email:
            raise ValidationError(_("Email address cannot be empty."))

        # Check for uniqueness across other users
        existing = User.objects.exclude(pk=self.instance.pk).filter(email__iexact=email)
        if existing.exists():
            raise ValidationError(_("This email address is already in use by another account."))
        return email


class UserPasswordChangeForm(PasswordChangeForm):
    """Custom password change form with Tailwind CSS styling."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm',
            })
