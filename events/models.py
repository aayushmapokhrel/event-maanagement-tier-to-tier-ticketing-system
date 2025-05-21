from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
import qrcode
from io import BytesIO
from django.core.files import File
from PIL import Image, ImageDraw
from django.db.models import Sum

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=15, blank=True)
    address = models.CharField(max_length=200, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True)
    
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
        ('MUSIC', 'Music'),
        ('EDUCATION', 'Education'),
        ('SPORTS', 'Sports'),
        ('COMMUNITY', 'Community'),
        ('OTHER', 'Other'),
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    organizer = models.ForeignKey(User, on_delete=models.CASCADE)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    venue = models.CharField(max_length=200)
    date = models.DateField()
    time = models.TimeField()
    capacity = models.PositiveIntegerField()
    image = models.ImageField(upload_to='event_images/')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.title
    
    @property
    def is_past_event(self):
        event_datetime = timezone.make_aware(
            timezone.datetime.combine(self.date, self.time)
        )
        return event_datetime < timezone.now()
        
    @property
    def total_tickets_sold(self):
        """Calculate total number of tickets sold for this event, considering quantity"""
        return Ticket.objects.filter(
            tier__event=self,
            status='SOLD'
        ).aggregate(
            total=Sum('quantity')
        )['total'] or 0

class TicketTier(models.Model):
    TIER_CHOICES = [
        ('VIP', 'VIP'),
        ('GENERAL', 'General Admission'),
        ('EARLY_BIRD', 'Early Bird'),
    ]
    
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='ticket_tiers')
    name = models.CharField(max_length=50, choices=TIER_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    description = models.TextField()
    
    def __str__(self):
        return f"{self.event.title} - {self.name}"
    
    @property
    def available_tickets(self):
        sold = self.tickets.filter(status='SOLD').aggregate(
            total_sold=models.Sum('quantity')
        )['total_sold'] or 0
        return self.quantity - sold
    
    def decrease_available_tickets(self, quantity):
        """Decrease available tickets when tickets are purchased"""
        if self.available_tickets >= quantity:
            return True
        return False

class Ticket(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SOLD', 'Sold'),
        ('CANCELLED', 'Cancelled'),
        ('USED', 'Used'),
    ]
    
    tier = models.ForeignKey(TicketTier, on_delete=models.CASCADE, related_name='tickets')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    purchase_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True)
    payment_id = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    check_in_time = models.DateTimeField(null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    
    def __str__(self):
        return f"{self.tier.event.title} - {self.tier.name} - {self.user.username}"
    
    def generate_qr_code(self):
        if not self.id:
            return  # Skip QR code generation if ticket hasn't been saved yet
            
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        # Add ticket information to QR code
        qr_data = f"""
        Event: {self.tier.event.title}
        Ticket Type: {self.tier.name}
        Ticket ID: {self.id}
        Holder: {self.user.get_full_name() or self.user.username}
        Status: {self.status}
        Quantity: {self.quantity}
        """
        
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        qr_image = qr.make_image(fill_color="black", back_color="white")
        
        # Create a BytesIO object to temporarily hold the image
        stream = BytesIO()
        qr_image.save(stream, format='PNG')
        
        # Save the QR code image to the model's ImageField
        filename = f'ticket_qr_{self.id}.png'
        self.qr_code.save(filename, File(stream), save=False)
    
    def check_in(self):
        """Mark the ticket as used and record the check-in time"""
        if self.status == 'SOLD':
            self.status = 'USED'
            self.check_in_time = timezone.now()
            self.save()
            return True
        return False
    
    def save(self, *args, **kwargs):
        # Generate QR code if ticket is marked as sold and doesn't have one
        if self.status == 'SOLD' and not self.qr_code:
            super().save(*args, **kwargs)  # Save first to ensure we have an ID
            self.generate_qr_code()
        
        super().save(*args, **kwargs)

    def get_total_price(self):
        """Calculate total price for this ticket (price * quantity)"""
        return self.tier.price * self.quantity

class Review(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.event.title} - {self.user.username} - {self.rating}★"
