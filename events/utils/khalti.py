import requests
from django.conf import settings
from django.urls import reverse
from django.core.exceptions import ValidationError


class KhaltiPayment:
    @staticmethod
    def get_api_url():
        """Return the appropriate Khalti API URL based on mode"""
        if settings.KHALTI_MODE == "live":
            return "https://khalti.com/api/v2/"
        return "https://dev.khalti.com/api/v2/"

    @staticmethod
    def initiate_payment(request, ticket, return_view_name):
        """Initiate payment with Khalti"""
        api_url = f"{KhaltiPayment.get_api_url()}epayment/initiate/"

        # Calculate amount in paisa (Khalti uses smallest currency unit)
        amount = int(ticket.tier.price * ticket.quantity * 100)  # Convert to paisa

        payload = {
            "return_url": request.build_absolute_uri(
                reverse(return_view_name, kwargs={"ticket_id": ticket.id})
            ),
            "website_url": request.build_absolute_uri("/"),
            "amount": amount,
            "purchase_order_id": str(ticket.id),
            "purchase_order_name": f"Ticket for {ticket.tier.event.title}",
            "customer_info": {
                "name": ticket.user.get_full_name() or ticket.user.username,
                "email": ticket.user.email,
                "phone": getattr(ticket.user.userprofile, "phone_number", ""),
            },
        }

        headers = {
            "Authorization": f"Key {settings.KHALTI_SECRET_KEY}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(api_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise ValidationError(f"Payment initiation failed: {str(e)}")

    @staticmethod
    def verify_payment(pidx):
        """Verify payment with Khalti"""
        api_url = f"{KhaltiPayment.get_api_url()}epayment/lookup/"

        headers = {
            "Authorization": f"Key {settings.KHALTI_SECRET_KEY}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(api_url, json={"pidx": pidx}, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise ValidationError(f"Payment verification failed: {str(e)}")
