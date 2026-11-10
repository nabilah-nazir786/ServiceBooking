from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager
from datetime import datetime

class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(username, email, password, **extra_fields)

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('user', 'User'),
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='user')
    full_name = models.CharField(max_length=150, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    objects = CustomUserManager()

    @property
    def unique_vehicles(self):
        seen_numbers = set()
        vehicles = []
        for b in self.bookings.all():
            v_num = b.vehicle_number.strip().upper() if b.vehicle_number else ''
            if v_num and v_num not in seen_numbers:
                seen_numbers.add(v_num)
                vehicles.append({
                    'model': b.vehicle_model,
                    'number': v_num
                })
        return vehicles

    def __str__(self):
        return self.full_name if self.full_name else self.username


class Service(models.Model):
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=100)
    description = models.TextField()
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='service_images/', blank=True, null=True)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} (₹{self.base_price})"


class GalleryItem(models.Model):
    title = models.CharField(max_length=150)
    category = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='gallery/', blank=True, null=True)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.category})"


class Announcement(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to='announcements/', blank=True, null=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_active(self):
        from django.utils import timezone
        today = timezone.localdate()
        if not self.is_visible:
            return False
        if self.start_date and self.start_date > today:
            return False
        if self.end_date and self.end_date < today:
            return False
        return True

    @property
    def is_upcoming(self):
        from django.utils import timezone
        today = timezone.localdate()
        return bool(self.start_date and self.start_date > today)

    @property
    def is_expired(self):
        from django.utils import timezone
        today = timezone.localdate()
        return bool(self.end_date and self.end_date < today)

    def __str__(self):
        return self.title


class TimeSlot(models.Model):
    SLOT_TYPE_CHOICES = (
        ('ALL', 'Every Day (Daily Recurring)'),
        ('MON_SAT', 'Monday to Saturday'),
        ('WEEKDAYS', 'Weekdays Only (Mon - Fri)'),
        ('WEEKENDS', 'Weekends Only (Sat & Sun)'),
        ('MONDAY', 'Monday Only'),
        ('TUESDAY', 'Tuesday Only'),
        ('WEDNESDAY', 'Wednesday Only'),
        ('THURSDAY', 'Thursday Only'),
        ('FRIDAY', 'Friday Only'),
        ('SATURDAY', 'Saturday Only'),
        ('SUNDAY', 'Sunday Only'),
        ('SPECIFIC', 'Specific Scheduled Date'),
        ('HOLIDAY_DATE', 'Holiday / Closed (Specific Date)'),
        ('HOLIDAY_RECURRING', 'Holiday / Weekly Closed Day'),
    )
    slot_type = models.CharField(max_length=25, choices=SLOT_TYPE_CHOICES, default='ALL')
    date = models.DateField(blank=True, null=True)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    max_bookings = models.PositiveIntegerField(default=1)
    is_available = models.BooleanField(default=True)
    is_holiday = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_frequency(self):
        if self.is_holiday or self.slot_type in ['HOLIDAY_DATE', 'HOLIDAY_RECURRING']:
            if (self.slot_type in ['SPECIFIC', 'HOLIDAY_DATE']) and self.date:
                return f"🏖️ Holiday ({self.date.strftime('%b %d, %Y')})"
            dict_choices = dict(self.SLOT_TYPE_CHOICES)
            freq_name = dict_choices.get(self.slot_type, 'Holiday')
            return f"🏖️ Holiday ({freq_name})"

        if self.slot_type == 'SPECIFIC' and self.date:
            return self.date.strftime('%b %d, %Y')
        dict_choices = dict(self.SLOT_TYPE_CHOICES)
        return dict_choices.get(self.slot_type, 'Every Day')

    def applies_to_date(self, target_date):
        if not self.is_available:
            return False
        
        if not target_date:
            return False
            
        if isinstance(target_date, str):
            try:
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return False
        
        is_match = False
        if self.slot_type == 'ALL':
            is_match = True
        elif self.slot_type in ['SPECIFIC', 'HOLIDAY_DATE']:
            is_match = (self.date == target_date)
        else:
            w = target_date.weekday() # 0 = Mon, 1 = Tue, 2 = Wed, 3 = Thu, 4 = Fri, 5 = Sat, 6 = Sun
            if self.slot_type == 'MON_SAT' and w <= 5:
                is_match = True
            elif self.slot_type == 'WEEKDAYS' and w < 5:
                is_match = True
            elif self.slot_type == 'WEEKENDS' and w >= 5:
                is_match = True
            elif self.slot_type == 'MONDAY' and w == 0:
                is_match = True
            elif self.slot_type == 'TUESDAY' and w == 1:
                is_match = True
            elif self.slot_type == 'WEDNESDAY' and w == 2:
                is_match = True
            elif self.slot_type == 'THURSDAY' and w == 3:
                is_match = True
            elif self.slot_type == 'FRIDAY' and w == 4:
                is_match = True
            elif self.slot_type == 'SATURDAY' and w == 5:
                is_match = True
            elif self.slot_type == 'SUNDAY' and w == 6:
                is_match = True

        if is_match and (self.is_holiday or self.slot_type in ['HOLIDAY_DATE', 'HOLIDAY_RECURRING']):
            return False # Closed/Holiday on this date
        return is_match

    @classmethod
    def is_workshop_closed(cls, target_date):
        """Check if workshop has a holiday/closed day scheduled for target_date"""
        if not target_date:
            return False
        if isinstance(target_date, str):
            try:
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                return False

        holiday_slots = cls.objects.filter(
            is_available=True
        ).filter(
            models.Q(is_holiday=True) | models.Q(slot_type__in=['HOLIDAY_DATE', 'HOLIDAY_RECURRING'])
        )

        for h_slot in holiday_slots:
            if h_slot.slot_type in ['SPECIFIC', 'HOLIDAY_DATE']:
                if h_slot.date == target_date:
                    return True
            else:
                w = target_date.weekday()
                if h_slot.slot_type in ['HOLIDAY_RECURRING', 'ALL']:
                    return True
                if h_slot.slot_type == 'MON_SAT' and w <= 5:
                    return True
                if h_slot.slot_type == 'WEEKDAYS' and w < 5:
                    return True
                if h_slot.slot_type == 'WEEKENDS' and w >= 5:
                    return True
                day_map = {0: 'MONDAY', 1: 'TUESDAY', 2: 'WEDNESDAY', 3: 'THURSDAY', 4: 'FRIDAY', 5: 'SATURDAY', 6: 'SUNDAY'}
                if h_slot.slot_type == day_map.get(w):
                    return True
        return False

    def booked_count_for_date(self, target_date):
        """Get count of active bookings for target_date"""
        if isinstance(target_date, str):
            try:
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                pass
        return self.bookings.filter(
            booking_date=target_date
        ).exclude(status='CANCELLED').count()

    def is_full_for_date(self, target_date):
        """Check if this slot has reached max_bookings capacity on target_date"""
        if not self.max_bookings:
            return False
        return self.booked_count_for_date(target_date) >= self.max_bookings

    def __str__(self):
        freq = self.display_frequency
        if self.start_time and self.end_time:
            return f"{freq} | {self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"
        return f"{freq} | Full Day / Holiday"


class Booking(models.Model):
    PAYMENT_OPTION_CHOICES = (
        ('PAY_NOW', 'Pay Online / Now'),
        ('PAY_AFTER', 'Pay After Service'),
    )
    PAYMENT_STATUS_CHOICES = (
        ('UNPAID', 'Unpaid / Pending'),
        ('PENDING_VERIFICATION', 'Payment Verification Pending'),
        ('PAID_ONLINE', 'Paid Online'),
        ('PAID_CASH', 'Paid Cash at Workshop'),
        ('PAID_UPI_CARD', 'Paid UPI / Card at Workshop'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    )

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='bookings')
    vehicle_number = models.CharField(max_length=50)
    vehicle_model = models.CharField(max_length=100)
    services = models.ManyToManyField(Service, related_name='bookings')
    booking_date = models.DateField()
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    special_instructions = models.TextField(blank=True, null=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    additional_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_option = models.CharField(max_length=20, choices=PAYMENT_OPTION_CHOICES, default='PAY_AFTER')
    payment_status = models.CharField(max_length=25, choices=PAYMENT_STATUS_CHOICES, default='UNPAID')
    transaction_id = models.CharField(max_length=100, blank=True, null=True)
    payment_screenshot = models.ImageField(upload_to='payment_screenshots/', blank=True, null=True)
    payment_submitted_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    admin_remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    PAID_STATUSES = ['PAID_ONLINE', 'PAID_CASH', 'PAID_UPI_CARD']

    @property
    def is_paid(self):
        return self.payment_status in self.PAID_STATUSES

    @property
    def has_feedback(self):
        return hasattr(self, 'feedback')

    @property
    def grand_total(self):
        return self.total_amount + self.additional_charge

    @property
    def upi_payment_url(self):
        """Returns standard UPI scheme payment string for mobile payment apps and QR code generation"""
        return f"upi://pay?pa=0740020A0055730@paytm&pn=COUSINS%20CAR%20CARE&am={self.grand_total:.2f}&cu=INR&tn=Booking%20BK-{self.id}"

    @property
    def can_customer_cancel(self):
        """Customer can only cancel BEFORE the scheduled work date and if not cancelled/completed."""
        from django.utils import timezone
        if self.status in ['CANCELLED', 'COMPLETED']:
            return False
        today = timezone.localdate()
        return self.booking_date > today

    @property
    def slot_number(self):
        """Returns which sequential slot position (1, 2, 3...) this booking holds for its time_slot on booking_date"""
        if not self.time_slot or not self.booking_date:
            return None
        earlier_count = Booking.objects.filter(
            time_slot=self.time_slot,
            booking_date=self.booking_date,
            id__lte=self.id
        ).exclude(status='CANCELLED').count()
        return earlier_count if earlier_count > 0 else 1

    def save(self, *args, **kwargs):
        if self.vehicle_number:
            self.vehicle_number = self.vehicle_number.upper().strip()
        super().save(*args, **kwargs)

    def __str__(self):
        user_name = self.user.full_name or self.user.username
        return f"Booking #{self.id} - {user_name} ({self.vehicle_number})"


class AdditionalCostItem(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='additional_cost_items')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.description} - ₹{self.amount} (Booking #{self.booking.id})"


class Feedback(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='feedback')
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='feedbacks')
    rating = models.PositiveSmallIntegerField(default=5)
    comments = models.TextField(blank=True, null=True)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Feedback for Booking #{self.booking.id} - {self.rating} Stars"







