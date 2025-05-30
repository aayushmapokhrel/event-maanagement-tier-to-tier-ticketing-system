from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, Event, TicketTier, Review, Venue


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=15, required=False)
    address = forms.CharField(max_length=200, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        
        if commit:
            user.save()
            # Use get_or_create to prevent duplicate profiles
            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'phone_number': self.cleaned_data.get("phone_number", ""),
                    'address': self.cleaned_data.get("address", "")
                }
            )
        return user


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("phone_number", "address", "profile_picture")
class EventAdminForm(forms.ModelForm):
    use_custom_venue = forms.BooleanField(
        required=False,
        label="Use a custom venue",
        help_text="Check this if you want to specify a venue not in our system"
    )
    custom_venue = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Enter custom venue details"})
    )

    class Meta:
        model = Event
        fields = (
            "title",
            "description",
            "category",
            "venue",
            "date",
            "time",
            "capacity",
            "image",
            "is_active",
            "status"
        )
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Enter event title"}),
            "description": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Describe your event"}
            ),
            "venue": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}),
            "capacity": forms.NumberInput(
                attrs={"min": "1", "placeholder": "Enter maximum capacity"}
            ),
        }
        help_texts = {
            "title": "Choose a clear, descriptive title for your event.",
            "description": "Provide detailed information about your event.",
            "category": "Select the category that best fits your event.",
            "venue": "Select a venue from our available venues or specify a custom venue.",
            "date": "Select the event date.",
            "time": "Select the start time of the event.",
            "capacity": "Enter the maximum number of attendees.",
            "image": "Upload an image for your event (recommended size: 800x600 pixels).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show available venues in the dropdown
        self.fields['venue'].queryset = Venue.objects.filter(is_available=True)
        self.fields['venue'].required = False  # Make venue not required initially

    def clean(self):
        cleaned_data = super().clean()
        use_custom_venue = cleaned_data.get('use_custom_venue')
        venue = cleaned_data.get('venue')
        custom_venue = cleaned_data.get('custom_venue')

        if use_custom_venue:
            if not custom_venue:
                raise forms.ValidationError("Please provide custom venue details.")
            cleaned_data['venue'] = None
        else:
            if not venue:
                raise forms.ValidationError("Please select a venue from the list.")
            cleaned_data['custom_venue'] = ''

        return cleaned_data

class EventForm(forms.ModelForm):
    use_custom_venue = forms.BooleanField(
        required=False,
        label="Use a custom venue",
        help_text="Check this if you want to specify a venue not in our system"
    )
    custom_venue = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "Enter custom venue details"})
    )

    class Meta:
        model = Event
        fields = (
            "title",
            "description",
            "category",
            "venue",
            "date",
            "time",
            "capacity",
            "image",
        )
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Enter event title"}),
            "description": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Describe your event"}
            ),
            "venue": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}),
            "capacity": forms.NumberInput(
                attrs={"min": "1", "placeholder": "Enter maximum capacity"}
            ),
        }
        help_texts = {
            "title": "Choose a clear, descriptive title for your event.",
            "description": "Provide detailed information about your event.",
            "category": "Select the category that best fits your event.",
            "venue": "Select a venue from our available venues or specify a custom venue.",
            "date": "Select the event date.",
            "time": "Select the start time of the event.",
            "capacity": "Enter the maximum number of attendees.",
            "image": "Upload an image for your event (recommended size: 800x600 pixels).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show available venues in the dropdown
        self.fields['venue'].queryset = Venue.objects.filter(is_available=True)
        self.fields['venue'].required = False  # Make venue not required initially

    def clean(self):
        cleaned_data = super().clean()
        use_custom_venue = cleaned_data.get('use_custom_venue')
        venue = cleaned_data.get('venue')
        custom_venue = cleaned_data.get('custom_venue')

        if use_custom_venue:
            if not custom_venue:
                raise forms.ValidationError("Please provide custom venue details.")
            cleaned_data['venue'] = None
        else:
            if not venue:
                raise forms.ValidationError("Please select a venue from the list.")
            cleaned_data['custom_venue'] = ''

        return cleaned_data


class TicketTierForm(forms.ModelForm):
    class Meta:
        model = TicketTier
        fields = ("name", "price", "quantity", "description")
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Describe what this ticket tier includes",
                }
            ),
            "price": forms.NumberInput(
                attrs={"min": "0", "step": "0.01", "placeholder": "Enter ticket price"}
            ),
            "quantity": forms.NumberInput(
                attrs={"min": "1", "placeholder": "Enter number of tickets available"}
            ),
        }
        help_texts = {
            "name": "Select the type of ticket tier.",
            "price": "Set the price for this ticket tier (in Rs.).",
            "quantity": "Specify how many tickets are available in this tier.",
            "description": "Describe the benefits and features included in this ticket tier.",
        }


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("rating", "comment")
        widgets = {
            "rating": forms.RadioSelect(attrs={"class": "star-rating"}),
            "comment": forms.Textarea(attrs={"rows": 4}),
        }
