from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
import qrcode
from io import BytesIO
from django.core.files import File
from PIL import Image, ImageDraw
from django.db.models import Sum
import shortuuid
import uuid
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import secrets


class Venue(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField()
    capacity = models.PositiveIntegerField()
    description = models.TextField()
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.address} - {self.capacity} capacity"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.CharField(max_length=200, blank=True)
    profile_picture = models.ImageField(upload_to="profile_pics/", blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

    @receiver(post_save, sender=User)
    def create_user_profile(sender, instance, created, **kwargs):
        """Create a UserProfile instance for all newly created User instances."""
        if created:
            UserProfile.objects.create(user=instance)

    @receiver(post_save, sender=User)
    def save_user_profile(sender, instance, **kwargs):
        """Save the UserProfile instance whenever the User instance is saved."""
        try:
            instance.userprofile.save()
        except UserProfile.DoesNotExist:
            UserProfile.objects.create(user=instance)


class Event(models.Model):
    CATEGORY_CHOICES = [
        ("MUSIC", "Music"),
        ("EDUCATION", "Education"),
        ("SPORTS", "Sports"),
        ("COMMUNITY", "Community"),
        ("OTHER", "Other"),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    date = models.DateField()
    time = models.TimeField()
    venue = models.ForeignKey(Venue, on_delete=models.SET_NULL, null=True, blank=True)
    custom_venue = models.CharField(max_length=200, null=True, blank=True)
    capacity = models.IntegerField()
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    image = models.ImageField(upload_to='event_images/', null=True, blank=True)
    organizer = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_notes = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.title

    @property
    def total_tickets_sold(self):
        return Ticket.objects.filter(tier__event=self, status='SOLD').aggregate(
            total=Sum('quantity')
        )['total'] or 0


class TicketTier(models.Model):
    TIER_CHOICES = [
        ("VIP", "VIP"),
        ("GENERAL", "General Admission"),
        ("EARLY_BIRD", "Early Bird"),
    ]

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="ticket_tiers"
    )
    name = models.CharField(max_length=50, choices=TIER_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    description = models.TextField()
    sold_quantity = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.event.title} - {self.name}"

    @property
    def available_tickets(self):
        return self.quantity - self.sold_quantity

    def decrease_available_tickets(self, quantity):
        """Decrease available tickets when tickets are purchased"""
        if self.available_tickets >= quantity:
            self.sold_quantity += quantity
            self.save()
            return True
        return False

    def create_tickets(self, user, quantity, payment_method="KHALTI"):
        """Create multiple individual tickets for each quantity"""
        tickets = []
        for _ in range(quantity):
            ticket = Ticket.objects.create(
                tier=self,
                user=user,
                status="SOLD" if payment_method != "CASH" else "PENDING",
                payment_method=payment_method,
                quantity=1,  # Each ticket represents 1 quantity
            )
            if payment_method != "CASH":
                ticket.generate_qr_code()
                ticket.save()
            tickets.append(ticket)
        return tickets


class Ticket(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("SOLD", "Sold"),
        ("RESERVED", "Reserved"),
        ("CANCELLED", "Cancelled"),
        ("USED", "Used"),
    ]
    PAYMENT_METHOD_CHOICES = [
        ("KHALTI", "Khalti"),
        ("CASH", "Cash"),
    ]

    tier = models.ForeignKey(
        TicketTier, on_delete=models.CASCADE, related_name="tickets"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purchase_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    qr_code = models.ImageField(upload_to="qr_codes/", blank=True)
    payment_id = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    check_in_time = models.DateTimeField(null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    payment_method = models.CharField(
        max_length=10, choices=PAYMENT_METHOD_CHOICES, default="KHALTI"
    )
    cash_payment_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_tickets",
    )
    verification_date = models.DateTimeField(null=True, blank=True)
    cash_verification_code = models.CharField(
        max_length=8, blank=True, null=True, unique=True
    )
    is_parent_ticket = models.BooleanField(default=True)
    # New field to link child tickets to parent
    parent_ticket = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="child_tickets",
    )
    unique_code = models.CharField(max_length=12, unique=True, blank=True)

    def __str__(self):
        return f"{self.tier.event.title} - {self.tier.name} - {self.user.username}"

    def generate_qr_code(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )

        # Generate a unique code if not exists
        if not self.unique_code:
            self.unique_code = shortuuid.uuid()[:12].upper()

        qr_data = f"""
        Event: {self.tier.event.title}
        Ticket ID: {self.id}
        Type: {self.tier.name}
        Holder: {self.user.get_full_name() or self.user.username}
        Unique Code: {self.unique_code}
        Status: {self.status}
        """

        qr.add_data(qr_data)
        qr.make(fit=True)

        qr_image = qr.make_image(fill_color="black", back_color="white")
        stream = BytesIO()
        qr_image.save(stream, format="PNG")
        filename = f"ticket_{self.id}_{self.unique_code}.png"
        self.qr_code.save(filename, File(stream), save=False)

    def create_child_tickets(self):
        """Create individual child tickets for each quantity"""
        if not self.is_parent_ticket:
            return

        # Create N-1 child tickets (since parent ticket counts as 1)
        for i in range(1, self.quantity):
            child_ticket = Ticket.objects.create(
                tier=self.tier,
                user=self.user,
                status=self.status,
                payment_method=self.payment_method,
                cash_payment_verified=self.cash_payment_verified,
                verified_by=self.verified_by,
                verification_date=self.verification_date,
                cash_verification_code=self.cash_verification_code,
                is_parent_ticket=False,
                parent_ticket=self,
                quantity=1,  # Each child ticket represents 1 quantity
            )
            child_ticket.generate_qr_code()
            child_ticket.save()

    def check_in(self):
        """Mark the ticket as used and record the check-in time"""
        if self.status == "SOLD":
            self.status = "USED"
            self.check_in_time = timezone.now()
            self.save()
            return True
        return False

    def verify_cash_payment(self, verified_by_user):
        """Mark a cash payment as verified"""
        if self.payment_method == "CASH" and self.status == "PENDING":
            if self.tier.decrease_available_tickets(self.quantity):
                self.status = "SOLD"
                self.cash_payment_verified = True
                self.verified_by = verified_by_user
                self.verification_date = timezone.now()
                self.generate_qr_code()
                self.save()
                return True
        return False

    def save(self, *args, **kwargs):
        # Generate QR code if ticket is marked as sold and doesn't have one
        if (self.status == "SOLD" and not self.qr_code) or (
            self.payment_method == "CASH" and self.cash_payment_verified
        ):
            super().save(*args, **kwargs)  # Save first to ensure we have an ID
            self.generate_qr_code()

        super().save(*args, **kwargs)

    def get_total_price(self):
        """Calculate total price for this ticket (price * quantity)"""
        return self.tier.price * self.quantity

    def get_all_tickets_in_group(self):
        """Return all tickets in this group (parent + children)"""
        if self.is_parent_ticket:
            return [self] + list(self.child_tickets.all())
        elif self.parent_ticket:
            return [self.parent_ticket] + list(self.parent_ticket.child_tickets.all())
        return [self]


class Review(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.event.title} - {self.user.username} - {self.rating}★"


@receiver(pre_save, sender=Ticket)
def generate_ticket_unique_code(sender, instance, **kwargs):
    if not instance.unique_code:
        instance.unique_code = str(uuid.uuid4())[:12].upper()


class EmailVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.email} - {'Verified' if self.is_verified else 'Not Verified'}"

    @classmethod
    def generate_token(cls):
        return secrets.token_urlsafe(32)
