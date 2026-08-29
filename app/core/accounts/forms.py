"""Admin forms for the custom user model.

Django's stock user forms assume a ``username`` field and know nothing about a
number that lives in the database encrypted. Both assumptions are replaced
here.

The ID-number field is write-only on purpose. Rendering a member's identity
number into an admin page puts it in the browser cache, the proxy logs and
anyone's shoulder view, for no operational gain -- staff need to *set* it and
to confirm *which* one is on file, not to read it back. The last four digits
are enough for the second, and code that genuinely needs the number reads
``user.id_number``.

The three identity keys -- the address, the identity number and the mobile
number -- are each checked for a clash here as well as in the database. The
database is what enforces them; this is what turns the enforcement into a
sentence beside the field instead of an IntegrityError page. Django catches the
address itself, because ``email`` is ``unique=True`` on the column. It does not
catch the other two: the identity number is unique on a blind index Django knows
nothing about, and the mobile constraint carries a condition, which
``ModelForm`` validation does not reach. So they are checked by hand.

The nickname was the third of these and is no longer on this form at all. C27
moved it to ``membership.ClubMembership``, and the clash check moved with it --
``membership.admin.ClubMembershipAdminForm``, over the index that actually
governs it.
"""
from django import forms
from django.contrib.auth.forms import BaseUserCreationForm
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm
from django.core.exceptions import ValidationError

from app.core.common.validators import (
    normalise_id_number,
    validate_sa_id_number,
    validate_sa_mobile_number,
)

from .models import User


class ContactClashMixin(forms.ModelForm):
    """Turns the mobile number's constraint into a field-level error.

    It is enforced by a partial unique index on ``User``; without this the
    admin would reach the database and return a 500 to a member of staff who
    made an ordinary mistake. The nickname was handled here too until C27 moved
    it onto ``ClubMembership``.

    The mobile number is normalised before it is compared, because the
    constraint is over the normalised column: ``082 123 4567`` and
    ``+27821234567`` are one handset, and comparing the raw text would let the
    second past the form and into an IntegrityError.
    """

    def clean_mobile(self):
        value = self.cleaned_data.get('mobile')
        if not value:
            return ''
        # Raises with the validator's own message if it is not a mobile number
        # at all, which is a different complaint from it being taken.
        normalised = validate_sa_mobile_number(value)

        clash = User.objects.by_mobile(normalised)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError(
                'Another account already holds that mobile number.',
                code='mobile_taken',
            )
        # The normalised form, so what the form saves is what the constraint
        # indexes.
        return normalised

ID_NUMBER_HELP = (
    'Leave blank to keep the number already on file. A 13-digit entry is '
    'validated as a South African ID and fills in the date of birth; anything '
    'else is stored as given (a passport, say).'
)


class IdNumberMixin(forms.ModelForm):
    """Adds a write-only ``id_number`` field backed by the model property."""

    id_number = forms.CharField(
        required=False,
        max_length=64,
        strip=True,
        label='Set ID number',
        help_text=ID_NUMBER_HELP,
    )
    clear_id_number = forms.BooleanField(
        required=False,
        label='Remove the stored ID number',
        help_text='Deletes it outright. It cannot be recovered afterwards.',
    )

    def clean(self):
        cleaned = super().clean()
        value = normalise_id_number(cleaned.get('id_number'))
        clearing = cleaned.get('clear_id_number')

        if value and clearing:
            raise ValidationError(
                'Choose one: enter a new ID number, or remove the existing one.'
            )
        if not value:
            return cleaned

        # Only a 13-digit entry is treated as an RSA ID. Foreign documents have
        # no checksum to test, so they are taken at face value.
        if len(value) == 13 and value.isdigit():
            validate_sa_id_number(value)

        # The blind index enforces this at the database level too, but a form
        # error is a better answer than an IntegrityError page.
        clash = User.objects.by_id_number(value)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError(
                {'id_number': 'Another account already holds that ID number.'}
            )
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        value = normalise_id_number(self.cleaned_data.get('id_number'))

        if self.cleaned_data.get('clear_id_number'):
            user.id_number = ''
        elif value:
            if len(value) == 13 and value.isdigit():
                # Fills date_of_birth and date_of_birth_verified_at from the
                # document, so staff cannot record a birth date that disagrees
                # with the ID they just checked.
                user.capture_sa_id_number(value)
            else:
                user.id_number = value

        if commit:
            user.save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()
        return user


class UserCreationForm(ContactClashMixin, IdNumberMixin, BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = (
            'email', 'first_name', 'last_name', 'mobile', 'status',
        )


class UserChangeForm(ContactClashMixin, IdNumberMixin, BaseUserChangeForm):
    class Meta(BaseUserChangeForm.Meta):
        model = User
        fields = '__all__'
