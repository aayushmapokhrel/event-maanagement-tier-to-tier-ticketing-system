from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, Event, TicketTier, Review


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
            UserProfile.objects.create(
                user=user,
                phone_number=self.cleaned_data.get("phone_number", ""),
                address=self.cleaned_data.get("address", ""),
            )
        return user


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("phone_number", "address", "profile_picture")


class EventForm(forms.ModelForm):
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
            "venue": forms.TextInput(attrs={"placeholder": "Enter venue location"}),
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
            "venue": "Specify the location where the event will be held.",
            "date": "Select the event date.",
            "time": "Select the start time of the event.",
            "capacity": "Enter the maximum number of attendees.",
            "image": "Upload an image for your event (recommended size: 800x600 pixels).",
        }


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
