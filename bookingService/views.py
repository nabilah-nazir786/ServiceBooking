import re
import io
import qrcode
from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_protect
from django.db import models
from django.utils import timezone
from .models import CustomUser, Service, GalleryItem, Announcement, TimeSlot, Booking, AdditionalCostItem, Feedback

def validate_full_name(full_name):
    if not full_name:
        return "Full name is required."
    if not re.match(r'^[a-zA-Z\s]+$', full_name):
        return "Full name must contain only letters and spaces."
    if len(full_name) < 2:
        return "Full name must be at least 2 characters long."
    return None

def validate_phone_number(phone_number):
    if not phone_number:
        return "Phone number is required."
    clean_phone = phone_number.replace(' ', '').replace('-', '')
    if not re.match(r'^\d{10}$', clean_phone):
        return "Phone number must be exactly 10 digits."
    return None

def validate_email_address(email):
    if not email:
        return "Email address is required."
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return "Please enter a valid email address."
    return None

def validate_transaction_id(txnid):
    if not txnid:
        return "Transaction ID / UTR reference number is required."
    clean_txn = str(txnid).strip()
    if not re.match(r'^\d{12}$', clean_txn):
        return "Transaction ID / UTR must be exactly 12 numeric digits (e.g. 426801928475)."
    return None

def validate_password_strength(password):
    if not password or len(password) < 8:
        return "Password must be at least 8 characters long."
    if not re.search(r'[A-Z]', password):
        return "Password must contain at least one uppercase letter (A-Z)."
    if not re.search(r'[0-9]', password):
        return "Password must contain at least one number (0-9)."
    if not re.search(r'[^a-zA-Z0-9]', password):
        return "Password must contain at least one special character (e.g. @#$%^&*!)."
    return None

def logout_view(request):
    logout(request)
    return redirect('bookingService:home')

@ensure_csrf_cookie
def home_view(request):
    services = Service.objects.filter(is_visible=True).order_by('-created_at')
    gallery_items = GalleryItem.objects.filter(is_visible=True).order_by('-created_at')
    timeslots = TimeSlot.objects.filter(is_available=True).order_by('slot_type', 'date', 'start_time')
    feedbacks = Feedback.objects.filter(is_visible=True).select_related('user', 'booking').order_by('-created_at')
    
    today = timezone.localdate()
    announcements = [a for a in Announcement.objects.filter(is_visible=True).order_by('-created_at') if a.is_active]

    return render(request, 'startup/home.html', {
        'services': services,
        'gallery_items': gallery_items,
        'timeslots': timeslots,
        'feedbacks': feedbacks,
        'announcements': announcements,
        'today_date': today,
    })

@login_required
def dashboard_redirect(request):
    if request.user.role == 'admin':
        return redirect('bookingService:admin_dashboard')
    else:
        return redirect('bookingService:user_dashboard')

@login_required
@ensure_csrf_cookie
def admin_dashboard_view(request):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')
    
    services = Service.objects.all().order_by('-created_at')
    gallery_items = GalleryItem.objects.all().order_by('-created_at')
    announcements = Announcement.objects.all().order_by('-created_at')
    timeslots = TimeSlot.objects.all().order_by('slot_type', 'date', 'start_time')
    
    grouped_map = {}
    for slot in timeslots:
        key = (slot.slot_type, slot.date if slot.slot_type in ['SPECIFIC', 'HOLIDAY_DATE'] else None, slot.is_holiday)
        if key not in grouped_map:
            grouped_map[key] = {
                'slot_type': slot.slot_type,
                'date': slot.date,
                'is_holiday': slot.is_holiday,
                'display_frequency': slot.display_frequency,
                'slots': []
            }
        grouped_map[key]['slots'].append(slot)
    
    grouped_timeslots = list(grouped_map.values())
    bookings = Booking.objects.all().order_by('-created_at')

    pending_bookings = Booking.objects.filter(status='PENDING').order_by('-created_at')
    approved_bookings = Booking.objects.filter(status='APPROVED').order_by('-created_at')

    today = timezone.localtime().date()
    previous_pending_bookings = Booking.objects.filter(
        booking_date__lt=today
    ).exclude(
        status__in=['COMPLETED', 'CANCELLED']
    ).select_related('time_slot', 'user').prefetch_related('services').order_by('booking_date', 'time_slot__start_time', 'id')

    ongoing_bookings = Booking.objects.filter(
        booking_date__lte=today,
        status__in=['APPROVED', 'IN_PROGRESS', 'COMPLETED']
    ).exclude(
        booking_date__lt=today,
        status='COMPLETED'
    ).select_related('time_slot', 'user').prefetch_related('services').order_by('booking_date', 'time_slot__start_time', 'id')

    # Group ongoing bookings based on time slots and capacity
    slot_map = {}
    for b in ongoing_bookings:
        slot_key = (b.booking_date, b.time_slot.id if b.time_slot else 0)
        if slot_key not in slot_map:
            max_cap = b.time_slot.max_bookings if b.time_slot else 1
            slot_map[slot_key] = {
                'booking_date': b.booking_date,
                'time_slot': b.time_slot,
                'max_capacity': max_cap,
                'bookings': []
            }
        slot_map[slot_key]['bookings'].append(b)

    for slot in timeslots:
        if slot.applies_to_date(today):
            slot_key = (today, slot.id)
            if slot_key not in slot_map:
                slot_map[slot_key] = {
                    'booking_date': today,
                    'time_slot': slot,
                    'max_capacity': slot.max_bookings,
                    'bookings': []
                }

    ongoing_slot_groups = []
    total_available_slots_today = 0
    full_bays_count = 0

    for key, group in slot_map.items():
        occupied = len(group['bookings'])
        max_cap = group['max_capacity']
        available = max(0, max_cap - occupied)
        pct = min(100, int((occupied / max_cap) * 100)) if max_cap > 0 else 0
        
        group['occupied_count'] = occupied
        group['available_count'] = available
        group['capacity_pct'] = pct
        group['is_full'] = (occupied >= max_cap and max_cap > 0)

        if group['booking_date'] == today:
            total_available_slots_today += available
            if group['is_full']:
                full_bays_count += 1

        ongoing_slot_groups.append(group)

    ongoing_slot_groups.sort(key=lambda g: (
        g['booking_date'] or today,
        g['time_slot'].start_time if (g['time_slot'] and g['time_slot'].start_time) else datetime.min.time()
    ))

    completed_bookings_today = Booking.objects.filter(
        status='COMPLETED',
        updated_at__date=today
    ).select_related('time_slot', 'user').prefetch_related('services').order_by('-updated_at')

    paid_statuses = ['PAID_ONLINE', 'PAID_CASH', 'PAID_UPI_CARD']
    paid_revenue = sum(b.grand_total for b in bookings if b.payment_status in paid_statuses and b.status != 'CANCELLED')
    unpaid_revenue = sum(b.grand_total for b in bookings if b.payment_status not in paid_statuses and b.status != 'CANCELLED')
    total_revenue = paid_revenue + unpaid_revenue

    customers = CustomUser.objects.filter(role='user').prefetch_related('bookings').order_by('-date_joined')
    feedbacks = Feedback.objects.all().select_related('booking', 'user').order_by('-created_at')
    avg_rating_val = feedbacks.aggregate(models.Avg('rating'))['rating__avg'] or 0.0
    avg_rating = round(float(avg_rating_val), 1)
    visible_feedbacks_count = feedbacks.filter(is_visible=True).count()

    return render(request, 'admin/admin_dashboard.html', {
        'today_date': timezone.localtime().strftime('%Y-%m-%d'),
        'services': services,
        'active_services_count': services.count(),
        'gallery_items': gallery_items,
        'gallery_count': gallery_items.count(),
        'announcements': announcements,
        'announcements_count': announcements.count(),
        'timeslots': timeslots,
        'grouped_timeslots': grouped_timeslots,
        'timeslots_count': timeslots.count(),
        'bookings': bookings,
        'bookings_count': bookings.count(),
        'pending_bookings': pending_bookings,
        'pending_count': pending_bookings.count(),
        'approved_bookings': approved_bookings,
        'approved_count': approved_bookings.count(),
        'ongoing_bookings': ongoing_bookings,
        'ongoing_count': ongoing_bookings.exclude(status='COMPLETED').count(),
        'previous_pending_bookings': previous_pending_bookings,
        'previous_pending_count': previous_pending_bookings.count(),
        'ongoing_slot_groups': ongoing_slot_groups,
        'total_available_slots_today': total_available_slots_today,
        'full_bays_count': full_bays_count,
        'completed_bookings_today': completed_bookings_today,
        'completed_today_count': completed_bookings_today.count(),
        'total_revenue': total_revenue,
        'paid_revenue': paid_revenue,
        'unpaid_revenue': unpaid_revenue,
        'customer_count': customers.count(),
        'customers': customers,
        'feedbacks': feedbacks,
        'feedback_count': feedbacks.count(),
        'visible_feedbacks_count': visible_feedbacks_count,
        'avg_rating': avg_rating
    })

@login_required
@csrf_protect
def approve_booking_view(request, booking_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    booking = get_object_or_404(Booking, id=booking_id)
    booking.status = 'APPROVED'
    booking.save()
    messages.success(request, f'Booking #{booking.id} for {booking.user.full_name or booking.user.username} has been APPROVED!')
    return redirect('bookingService:admin_dashboard')

@login_required
@csrf_protect
def reject_booking_view(request, booking_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    booking = get_object_or_404(Booking, id=booking_id)
    booking.status = 'CANCELLED'
    if not booking.admin_remarks:
        booking.admin_remarks = 'Booking request rejected by workshop.'
    booking.save()
    messages.success(request, f'Booking #{booking.id} for {booking.user.full_name or booking.user.username} has been REJECTED.')
    return redirect('bookingService:admin_dashboard')

@login_required
@ensure_csrf_cookie
def user_dashboard_view(request):
    if request.user.role == 'admin':
        return redirect('bookingService:admin_dashboard')
    
    user_bookings = Booking.objects.filter(user=request.user).select_related('time_slot', 'feedback').prefetch_related('services').order_by('-created_at')
    active_bookings = user_bookings.exclude(status='CANCELLED').exclude(status='COMPLETED', feedback__isnull=False)
    history_bookings = user_bookings.filter(models.Q(status='CANCELLED') | models.Q(status='COMPLETED', feedback__isnull=False))
    unreviewed_completed = user_bookings.filter(status='COMPLETED', feedback__isnull=True)
    
    services = Service.objects.filter(is_visible=True).order_by('-created_at')
    timeslots = TimeSlot.objects.filter(is_available=True).order_by('slot_type', 'date', 'start_time')

    if active_bookings.exists():
        current_booking = active_bookings.first()
    elif unreviewed_completed.exists():
        current_booking = unreviewed_completed.first()
    else:
        current_booking = None

    profile_error = request.session.pop('profile_error', None)
    password_error = request.session.pop('password_error', None)

    active_announcements = [a for a in Announcement.objects.filter(is_visible=True).order_by('-created_at') if a.is_active]

    return render(request, 'user/user_dashboard.html', {
        'services': services,
        'timeslots': timeslots,
        'announcements': active_announcements,
        'user_bookings': user_bookings,
        'user_bookings_count': user_bookings.count(),
        'active_bookings': active_bookings,
        'active_count': active_bookings.count(),
        'history_bookings': history_bookings,
        'history_count': history_bookings.count(),
        'current_booking': current_booking,
        'profile_error': profile_error,
        'password_error': password_error,
    })

@login_required
@csrf_protect
def update_profile_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        email = request.POST.get('email', '').strip()

        name_err = validate_full_name(full_name)
        phone_err = validate_phone_number(phone_number)
        email_err = validate_email_address(email)

        if name_err:
            request.session['profile_error'] = name_err
        elif phone_err:
            request.session['profile_error'] = phone_err
        elif email_err:
            request.session['profile_error'] = email_err
        elif CustomUser.objects.exclude(id=request.user.id).filter(email__iexact=email).exists():
            request.session['profile_error'] = 'Another account already exists with that email address.'
        else:
            request.user.full_name = full_name
            request.user.phone_number = phone_number
            request.user.email = email
            request.user.username = email
            request.user.save()
            messages.success(request, 'Profile details updated successfully!')

    return redirect('bookingService:user_dashboard')

@login_required
@csrf_protect
def change_password_view(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        pwd_error = validate_password_strength(new_password)
        if not old_password or not new_password or not confirm_password:
            request.session['password_error'] = 'Please fill in all password fields.'
        elif not request.user.check_password(old_password):
            request.session['password_error'] = 'Current password is incorrect.'
        elif pwd_error:
            request.session['password_error'] = pwd_error
        elif new_password != confirm_password:
            request.session['password_error'] = 'New password and confirmation password do not match.'
        else:
            request.user.set_password(new_password)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, 'Password changed successfully!')

    return redirect('bookingService:user_dashboard')

@login_required
@csrf_protect
def create_booking_view(request):
    if request.user.role == 'admin':
        return redirect('bookingService:admin_dashboard')

    if request.method == 'POST':
        vehicle_number = request.POST.get('vehicle_number', '').upper().strip()
        vehicle_model = request.POST.get('vehicle_model', '').strip()
        service_ids = request.POST.getlist('services')
        booking_date = request.POST.get('booking_date', '').strip()
        time_slot_id = request.POST.get('time_slot_id', '').strip()
        special_instructions = request.POST.get('special_instructions', '').strip()
        payment_option = request.POST.get('payment_option', 'PAY_AFTER').strip()

        if vehicle_number and vehicle_model and service_ids and booking_date:
            # 0. Check past date restriction
            try:
                b_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
                today = timezone.localdate()
                if b_date < today:
                    messages.error(request, 'Bookings cannot be scheduled for past dates. Please select today or a future date.')
                    return redirect('bookingService:user_dashboard')
            except (ValueError, TypeError):
                messages.error(request, 'Invalid date selected.')
                return redirect('bookingService:user_dashboard')
            # 1. Check if workshop is closed on this date
            if TimeSlot.is_workshop_closed(booking_date):
                messages.error(request, f'Workshop is CLOSED on {booking_date} (Holiday / Off Day). Please select another date.')
                return redirect('bookingService:user_dashboard')

            time_slot = TimeSlot.objects.filter(id=time_slot_id).first() if time_slot_id else None

            # 2. Validate time slot applicability & capacity if chosen
            if time_slot:
                if b_date == today and time_slot.start_time:
                    if time_slot.start_time <= timezone.localtime().time():
                        messages.error(request, 'This time slot has already passed for today. Please select a future time slot.')
                        return redirect('bookingService:user_dashboard')

                if not time_slot.applies_to_date(b_date):
                    messages.error(request, 'Selected time slot is not valid for the chosen date.')
                    return redirect('bookingService:user_dashboard')
                
                if time_slot.is_full_for_date(b_date):
                    messages.error(request, f'Time slot "{time_slot.display_frequency}" is fully booked for {booking_date}. Please pick a different slot or date.')
                    return redirect('bookingService:user_dashboard')

            selected_services = Service.objects.filter(id__in=service_ids)
            total_amount = sum(s.base_price for s in selected_services)

            transaction_id = request.POST.get('transaction_id', '').strip()
            payment_screenshot = request.FILES.get('payment_screenshot')

            payment_status = 'UNPAID'
            submitted_at = None
            if payment_option == 'PAY_NOW':
                txn_err = validate_transaction_id(transaction_id)
                if txn_err:
                    messages.error(request, txn_err)
                    return redirect('bookingService:user_dashboard')

                if not payment_screenshot:
                    messages.error(request, 'Payment screenshot proof is required when selecting Pay Now option.')
                    return redirect('bookingService:user_dashboard')

                payment_status = 'PENDING_VERIFICATION'
                submitted_at = timezone.now()

            booking = Booking.objects.create(
                user=request.user,
                vehicle_number=vehicle_number,
                vehicle_model=vehicle_model,
                booking_date=booking_date,
                time_slot=time_slot,
                special_instructions=special_instructions,
                total_amount=total_amount,
                payment_option=payment_option,
                payment_status=payment_status,
                transaction_id=transaction_id if payment_option == 'PAY_NOW' else None,
                payment_screenshot=payment_screenshot if payment_option == 'PAY_NOW' else None,
                payment_submitted_at=submitted_at,
                status='PENDING'
            )
            booking.services.set(selected_services)

            if payment_status == 'PENDING_VERIFICATION':
                messages.success(request, f'Booking #{booking.id} submitted with payment proof! Your booking and payment are under admin verification.')
            else:
                messages.success(request, f'Booking #{booking.id} submitted successfully! Your booking is pending admin approval.')
            return redirect('bookingService:user_dashboard')
        else:
            messages.error(request, 'Please fill in all required vehicle details, date, and select at least one service.')

    return redirect('bookingService:user_dashboard')

@login_required
@csrf_protect
def submit_feedback_view(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, user=request.user)
    if booking.status != 'COMPLETED':
        messages.error(request, 'Feedback can only be submitted once the booking is completed.')
        return redirect('bookingService:user_dashboard')

    if request.method == 'POST':
        rating_val = request.POST.get('rating', '5')
        comments = request.POST.get('comments', '').strip()

        try:
            rating = int(rating_val)
            if rating < 1 or rating > 5:
                rating = 5
        except (ValueError, TypeError):
            rating = 5

        Feedback.objects.update_or_create(
            booking=booking,
            defaults={
                'user': request.user,
                'rating': rating,
                'comments': comments
            }
        )
        messages.success(request, f'Thank you for rating your service for Booking #{booking.id}!')

    return redirect('bookingService:user_dashboard')

@login_required
@csrf_protect
def add_service_view(request):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category = request.POST.get('category', '').strip()
        description = request.POST.get('description', '').strip()
        base_price = request.POST.get('base_price', '').strip()
        is_visible = request.POST.get('is_visible') == 'on'
        image = request.FILES.get('image')

        if name and category and description and base_price:
            Service.objects.create(
                name=name,
                category=category,
                description=description,
                base_price=base_price,
                image=image,
                is_visible=is_visible
            )
            messages.success(request, 'Service package added successfully!')
        else:
            messages.error(request, 'Please fill in all required fields.')

    return redirect('bookingService:admin_dashboard')

@login_required
@ensure_csrf_cookie
@csrf_protect
def edit_service_view(request, service_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')
        
    service = get_object_or_404(Service, id=service_id)
    
    if request.method == 'POST':
        service.name = request.POST.get('name', '').strip()
        service.category = request.POST.get('category', '').strip()
        service.description = request.POST.get('description', '').strip()
        service.base_price = request.POST.get('base_price', '').strip()
        service.is_visible = request.POST.get('is_visible') == 'on'
        
        if 'image' in request.FILES:
            service.image = request.FILES['image']
            
        if service.name and service.category and service.description and service.base_price:
            service.save()
            messages.success(request, 'Service package updated successfully!')
            return redirect('bookingService:admin_dashboard')
        else:
            messages.error(request, 'Please fill in all required fields.')
            
    return render(request, 'admin/edit_service.html', {'service': service})

@login_required
@csrf_protect
def delete_service_view(request, service_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    service = get_object_or_404(Service, id=service_id)
    service.delete()
    messages.success(request, 'Service package deleted.')
    return redirect('bookingService:admin_dashboard')

@login_required
@csrf_protect
def add_gallery_item_view(request):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        category = request.POST.get('category', '').strip()
        description = request.POST.get('description', '').strip()
        is_visible = request.POST.get('is_visible') == 'on'
        image = request.FILES.get('image')

        if title and category:
            GalleryItem.objects.create(
                title=title,
                category=category,
                description=description,
                image=image,
                is_visible=is_visible
            )
            messages.success(request, 'Gallery item added successfully!')
        else:
            messages.error(request, 'Please provide both title and category.')

    return redirect('bookingService:admin_dashboard')

@login_required
@ensure_csrf_cookie
@csrf_protect
def edit_gallery_item_view(request, item_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')
        
    item = get_object_or_404(GalleryItem, id=item_id)
    
    if request.method == 'POST':
        item.title = request.POST.get('title', '').strip()
        item.category = request.POST.get('category', '').strip()
        item.description = request.POST.get('description', '').strip()
        item.is_visible = request.POST.get('is_visible') == 'on'
        
        if 'image' in request.FILES:
            item.image = request.FILES['image']
            
        if item.title and item.category:
            item.save()
            messages.success(request, 'Gallery item updated successfully!')
            return redirect('bookingService:admin_dashboard')
        else:
            messages.error(request, 'Please provide both title and category.')
            
    return render(request, 'admin/edit_gallery_item.html', {'item': item})

@login_required
@csrf_protect
def delete_gallery_item_view(request, item_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    item = get_object_or_404(GalleryItem, id=item_id)
    item.delete()
    messages.success(request, 'Gallery item deleted.')
    return redirect('bookingService:admin_dashboard')


@login_required
def get_slots_for_date_api(request):
    date_str = request.GET.get('date', '').strip()
    if not date_str:
        return JsonResponse({'error': 'Date parameter is required.'}, status=400)

    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid date format.'}, status=400)

    day_name = target_date.strftime('%A')
    formatted_date = target_date.strftime('%b %d, %Y')

    # 1. Check if workshop is closed on target_date
    if TimeSlot.is_workshop_closed(target_date):
        return JsonResponse({
            'is_closed': True,
            'day_name': day_name,
            'date_str': formatted_date,
            'message': f'🏖️ Workshop is CLOSED on {formatted_date} ({day_name} - Holiday / Off Day). No booking slots available.',
            'slots': []
        })

    # 2. Fetch all active non-holiday slots
    all_slots = TimeSlot.objects.filter(
        is_available=True,
        is_holiday=False
    ).exclude(
        slot_type__in=['HOLIDAY_DATE', 'HOLIDAY_RECURRING']
    ).order_by('start_time')

    applicable_slots = []
    today = timezone.localdate()
    now_time = timezone.localtime().time()

    for slot in all_slots:
        if slot.applies_to_date(target_date):
            if target_date == today and slot.start_time:
                if slot.start_time <= now_time:
                    continue  # Skip slots that have already started or passed today

            is_full = slot.is_full_for_date(target_date)
            booked_count = slot.booked_count_for_date(target_date)
            max_cap = slot.max_bookings
            current_slot_number = min(booked_count + 1, max_cap) if (max_cap and max_cap > 0) else (booked_count + 1)
            remaining_slots = max(0, max_cap - booked_count) if (max_cap is not None and max_cap > 0) else None

            time_label = ""
            if slot.start_time and slot.end_time:
                time_label = f"{slot.start_time.strftime('%I:%M %p')} - {slot.end_time.strftime('%I:%M %p')}"
            else:
                time_label = "Full Day Window"

            applicable_slots.append({
                'id': slot.id,
                'time_display': time_label,
                'frequency': slot.display_frequency,
                'is_full': is_full,
                'max_bookings': max_cap,
                'booked_count': booked_count,
                'current_slot_number': current_slot_number,
                'remaining_slots': remaining_slots
            })

    return JsonResponse({
        'is_closed': False,
        'day_name': day_name,
        'date_str': formatted_date,
        'slots_count': len(applicable_slots),
        'slots': applicable_slots
    })


@login_required
@csrf_protect
def add_timeslot_view(request):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    if request.method == 'POST':
        slot_type = request.POST.get('slot_type', 'ALL').strip()
        raw_date = request.POST.get('date', '').strip()
        date = raw_date if (slot_type in ['SPECIFIC', 'HOLIDAY_DATE'] and raw_date) else None
        start_time = request.POST.get('start_time', '').strip()
        end_time = request.POST.get('end_time', '').strip()
        max_bookings = request.POST.get('max_bookings', '1').strip()
        is_available = request.POST.get('is_available') == 'on'
        is_holiday = request.POST.get('is_holiday') == 'on' or slot_type in ['HOLIDAY_DATE', 'HOLIDAY_RECURRING']

        if is_holiday:
            if not start_time: start_time = "00:00:00"
            if not end_time: end_time = "23:59:59"

        if (start_time and end_time) and (slot_type not in ['SPECIFIC', 'HOLIDAY_DATE'] or date):
            TimeSlot.objects.create(
                slot_type=slot_type,
                date=date,
                start_time=start_time,
                end_time=end_time,
                max_bookings=int(max_bookings) if max_bookings.isdigit() else 1,
                is_available=is_available,
                is_holiday=is_holiday
            )
            if is_holiday:
                messages.success(request, 'Holiday / Closed day configured successfully!')
            else:
                messages.success(request, 'Time slot created successfully!')
        else:
            messages.error(request, 'Please fill in all required time slot fields.')

    return redirect('bookingService:admin_dashboard')

@login_required
@ensure_csrf_cookie
@csrf_protect
def edit_timeslot_view(request, slot_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')
        
    timeslot = get_object_or_404(TimeSlot, id=slot_id)
    
    if request.method == 'POST':
        slot_type = request.POST.get('slot_type', 'ALL').strip()
        raw_date = request.POST.get('date', '').strip()
        date = raw_date if (slot_type in ['SPECIFIC', 'HOLIDAY_DATE'] and raw_date) else None
        start_time = request.POST.get('start_time', '').strip()
        end_time = request.POST.get('end_time', '').strip()
        max_bookings = request.POST.get('max_bookings', '1').strip()
        timeslot.is_available = request.POST.get('is_available') == 'on'
        timeslot.is_holiday = request.POST.get('is_holiday') == 'on' or slot_type in ['HOLIDAY_DATE', 'HOLIDAY_RECURRING']
        
        if timeslot.is_holiday:
            if not start_time: start_time = "00:00:00"
            if not end_time: end_time = "23:59:59"

        if (start_time and end_time) and (slot_type not in ['SPECIFIC', 'HOLIDAY_DATE'] or date):
            timeslot.slot_type = slot_type
            timeslot.date = date
            timeslot.start_time = start_time
            timeslot.end_time = end_time
            timeslot.max_bookings = int(max_bookings) if max_bookings.isdigit() else 1
            timeslot.save()
            messages.success(request, 'Time slot / Holiday updated successfully!')
            return redirect('bookingService:admin_dashboard')
        else:
            messages.error(request, 'Please fill in all required time slot fields.')
            
    return render(request, 'admin/edit_timeslot.html', {'timeslot': timeslot})

@login_required
@csrf_protect
def delete_timeslot_view(request, slot_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    timeslot = get_object_or_404(TimeSlot, id=slot_id)
    timeslot.delete()
    messages.success(request, 'Time slot / Holiday deleted successfully.')
    return redirect('bookingService:admin_dashboard')


@login_required
@csrf_protect
def admin_create_booking_view(request):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    if request.method == 'POST':
        user_id = request.POST.get('user_id', '').strip()
        vehicle_number = request.POST.get('vehicle_number', '').upper().strip()
        vehicle_model = request.POST.get('vehicle_model', '').strip()
        service_ids = request.POST.getlist('services')
        booking_date = request.POST.get('booking_date', '').strip()
        time_slot_id = request.POST.get('time_slot_id', '').strip()
        special_instructions = request.POST.get('special_instructions', '').strip()
        custom_amount = request.POST.get('total_amount', '').strip()
        payment_option = request.POST.get('payment_option', 'PAY_AFTER').strip()
        status = request.POST.get('status', 'CONFIRMED').strip()

        customer = CustomUser.objects.filter(id=user_id).first() if user_id else request.user

        if vehicle_number and vehicle_model and service_ids and booking_date:
            try:
                b_date = datetime.strptime(booking_date, '%Y-%m-%d').date()
                today = timezone.localdate()
                if b_date < today:
                    messages.error(request, 'Bookings cannot be scheduled for past dates. Please select today or a future date.')
                    return redirect('bookingService:admin_dashboard')
            except (ValueError, TypeError):
                messages.error(request, 'Invalid date selected.')
                return redirect('bookingService:admin_dashboard')

            if TimeSlot.is_workshop_closed(booking_date):
                messages.warning(request, f'Notice: Workshop is marked CLOSED on {booking_date} (Holiday / Off Day).')

            time_slot = TimeSlot.objects.filter(id=time_slot_id).first() if time_slot_id else None
            if time_slot:
                if b_date == today and time_slot.start_time:
                    if time_slot.start_time <= timezone.localtime().time():
                        messages.error(request, 'This time slot has already passed for today. Please select a future time slot.')
                        return redirect('bookingService:admin_dashboard')

                if time_slot.is_full_for_date(booking_date):
                    messages.warning(request, f'Notice: Time slot "{time_slot.display_frequency}" had reached maximum capacity for {booking_date}. Booking created via Admin override.')

            selected_services = Service.objects.filter(id__in=service_ids)
            calculated_total = sum(s.base_price for s in selected_services)
            try:
                total_amount = Decimal(custom_amount) if custom_amount else calculated_total
            except (InvalidOperation, TypeError):
                total_amount = calculated_total

            if status == 'COMPLETED' and payment_option == 'PAY_AFTER':
                messages.error(request, 'Cannot create a COMPLETED booking with payment set to "Pay After Service". Please set payment to Pay Online or update status to Confirmed/In Progress.')
                return redirect('bookingService:admin_dashboard')

            transaction_id = request.POST.get('transaction_id', '').strip()
            payment_screenshot = request.FILES.get('payment_screenshot')

            payment_status = 'UNPAID'
            submitted_at = None
            if payment_option == 'PAY_NOW':
                txn_err = validate_transaction_id(transaction_id)
                if txn_err:
                    messages.error(request, txn_err)
                    return redirect('bookingService:admin_dashboard')

                if not payment_screenshot:
                    messages.error(request, 'Payment screenshot proof is required when selecting Pay Now option.')
                    return redirect('bookingService:admin_dashboard')

                payment_status = 'PENDING_VERIFICATION'
                submitted_at = timezone.now()

            booking = Booking.objects.create(
                user=customer,
                vehicle_number=vehicle_number,
                vehicle_model=vehicle_model,
                booking_date=booking_date,
                time_slot=time_slot,
                special_instructions=special_instructions,
                total_amount=total_amount,
                payment_option=payment_option,
                status=status,
                payment_status=payment_status,
                transaction_id=transaction_id if payment_option == 'PAY_NOW' else None,
                payment_screenshot=payment_screenshot if payment_option == 'PAY_NOW' else None,
                payment_submitted_at=submitted_at
            )
            booking.services.set(selected_services)
            messages.success(request, f'Admin created Booking #{booking.id} successfully!')
        else:
            messages.error(request, 'Please complete all required fields when creating a manual booking.')

    return redirect('bookingService:admin_dashboard')

@login_required
@csrf_protect
def update_booking_status_view(request, booking_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    if request.method == 'POST':
        booking = get_object_or_404(Booking, id=booking_id)
        new_status = request.POST.get('status', '').strip()
        valid_statuses = [choice[0] for choice in Booking.STATUS_CHOICES]
        if new_status in valid_statuses:
            if new_status == 'COMPLETED' and not booking.is_paid:
                messages.error(request, f'Cannot mark Booking #BK-{booking.id} as COMPLETED without payment! Payment status is currently UNPAID. Please update payment mode before completing work.')
            else:
                booking.status = new_status
                booking.save()
                messages.success(request, f'Booking #{booking.id} status updated to {booking.get_status_display()}.')
        else:
            messages.error(request, 'Invalid status selection.')

    return redirect('bookingService:admin_dashboard')

@login_required
def delete_booking_view(request, booking_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    booking = get_object_or_404(Booking, id=booking_id)
    booking_ref = f"#BK-{booking.id}"
    booking.delete()
    messages.success(request, f'Booking {booking_ref} has been permanently deleted.')
    return redirect('bookingService:admin_dashboard')

@login_required
@csrf_protect
def user_delete_booking_view(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id, user=request.user)

    if not booking.can_customer_cancel:
        today = timezone.localdate()
        if booking.booking_date <= today:
            messages.error(request, f'Booking #BK-{booking.id} cannot be cancelled on or after the scheduled work date ({booking.booking_date.strftime("%b %d, %Y")}). Customer cancellations are allowed only before the work date.')
        else:
            messages.error(request, f'Booking #BK-{booking.id} cannot be cancelled because it is already {booking.get_status_display().lower()}.')
        return redirect('bookingService:user_dashboard')

    booking_ref = f"#BK-{booking.id}"
    booking.status = 'CANCELLED'
    booking.save()
    messages.success(request, f'Your Booking {booking_ref} has been cancelled successfully and is now marked as CANCELLED.')
    return redirect('bookingService:user_dashboard')


@login_required
@ensure_csrf_cookie
@csrf_protect
def update_ongoing_work_view(request, booking_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    booking = get_object_or_404(Booking, id=booking_id)

    if request.method == 'POST':
        new_status = request.POST.get('status', '').strip()
        total_amount_input = request.POST.get('total_amount', '').strip()
        payment_status = request.POST.get('payment_status', '').strip()
        admin_remarks = request.POST.get('admin_remarks', '').strip()

        valid_statuses = [c[0] for c in Booking.STATUS_CHOICES]
        valid_pay_statuses = [c[0] for c in Booking.PAYMENT_STATUS_CHOICES]

        target_payment_status = payment_status if payment_status in valid_pay_statuses else booking.payment_status
        is_target_paid = target_payment_status in Booking.PAID_STATUSES

        if new_status == 'COMPLETED' and not is_target_paid:
            messages.error(request, f'Cannot mark Booking #BK-{booking.id} as COMPLETED without payment! Payment status is currently UNPAID. Please select a valid paid status (Paid Cash, Paid UPI/Card, or Paid Online) before completing work.')
            return redirect('bookingService:admin_dashboard')

        if new_status in valid_statuses:
            booking.status = new_status
        if payment_status in valid_pay_statuses:
            booking.payment_status = payment_status

        if total_amount_input:
            try:
                booking.total_amount = Decimal(total_amount_input)
            except (InvalidOperation, TypeError, ValueError):
                pass

        if 'admin_remarks' in request.POST:
            booking.admin_remarks = admin_remarks

        # Handle itemized additional cost lines (only when posted from full edit form)
        if 'item_description[]' in request.POST or 'item_amount[]' in request.POST:
            item_descriptions = request.POST.getlist('item_description[]')
            item_amounts = request.POST.getlist('item_amount[]')

            booking.additional_cost_items.all().delete()
            total_additional = Decimal('0.00')

            for desc, amt_str in zip(item_descriptions, item_amounts):
                desc_clean = desc.strip()
                if desc_clean:
                    try:
                        amt_dec = Decimal(amt_str.strip())
                        if amt_dec >= Decimal('0.00'):
                            AdditionalCostItem.objects.create(
                                booking=booking,
                                description=desc_clean,
                                amount=amt_dec
                            )
                            total_additional += amt_dec
                    except (InvalidOperation, TypeError, ValueError):
                        pass

            booking.additional_charge = total_additional

        booking.save()
        messages.success(request, f'Work details & remarks for Booking #{booking.id} updated! Status: {booking.get_status_display()}, Additional Items Total: ₹{booking.additional_charge}, Grand Total: ₹{booking.grand_total}.')
        return redirect('bookingService:admin_dashboard')

    return render(request, 'admin/update_ongoing_work.html', {
        'booking': booking,
        'status_choices': Booking.STATUS_CHOICES,
        'payment_status_choices': Booking.PAYMENT_STATUS_CHOICES,
    })


@ensure_csrf_cookie
@csrf_protect
def login_view(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('bookingService:admin_dashboard')
        return redirect('bookingService:home')

    if request.method == 'POST':
        email_or_user = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')

        error = None
        if not email_or_user or not password:
            error = 'Please enter both email and password.'
        else:
            user_obj = CustomUser.objects.filter(
                models.Q(email__iexact=email_or_user) | models.Q(username__iexact=email_or_user)
            ).first()

            if user_obj:
                user = authenticate(request, username=user_obj.username, password=password)
            else:
                user = None

            if user is not None:
                login(request, user)
                if user.role == 'admin':
                    messages.success(request, f"Welcome back, Administrator!")
                    return redirect('bookingService:admin_dashboard')
                messages.success(request, f"Welcome back, {user.full_name}!")
                return redirect('bookingService:home')
            else:
                error = 'Invalid email address or password.'

        return render(request, 'startup/login.html', {'error': error, 'email': email_or_user})

    return render(request, 'startup/login.html')

@ensure_csrf_cookie
@csrf_protect
def register_view(request):
    if request.user.is_authenticated:
        if request.user.role == 'admin':
            return redirect('bookingService:admin_dashboard')
        return redirect('bookingService:home')

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        error_message = None
        name_err = validate_full_name(full_name)
        phone_err = validate_phone_number(phone_number)
        email_err = validate_email_address(email)
        pwd_error = validate_password_strength(password)

        if not full_name or not phone_number or not email or not password:
            error_message = 'All fields are required.'
        elif name_err:
            error_message = name_err
        elif phone_err:
            error_message = phone_err
        elif email_err:
            error_message = email_err
        elif pwd_error:
            error_message = pwd_error
        elif password != confirm_password:
            error_message = 'Passwords do not match.'
        elif CustomUser.objects.filter(email__iexact=email).exists():
            error_message = 'An account with this email already exists.'

        if error_message:
            return render(request, 'startup/register.html', {
                'error': error_message,
                'full_name': full_name,
                'phone_number': phone_number,
                'email': email
            })

        user = CustomUser.objects.create_user(
            username=email,
            email=email,
            password=password,
            full_name=full_name,
            phone_number=phone_number,
            role='user'
        )
        login(request, user)
        return redirect('bookingService:home')

    return render(request, 'startup/register.html')

@login_required
@csrf_protect
def toggle_feedback_visibility_view(request, feedback_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')
    
    feedback = get_object_or_404(Feedback, id=feedback_id)
    feedback.is_visible = not feedback.is_visible
    feedback.save()
    status_str = "visible on homepage" if feedback.is_visible else "hidden from homepage"
    messages.success(request, f"Review #{feedback.id} is now {status_str}.")
    return redirect('bookingService:admin_dashboard')

@login_required
@csrf_protect
def add_announcement_view(request):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        start_date = request.POST.get('start_date', '').strip()
        end_date = request.POST.get('end_date', '').strip()
        is_visible = request.POST.get('is_visible') == 'on'
        image = request.FILES.get('image')

        if title and description and start_date and end_date:
            try:
                s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                if e_date < s_date:
                    messages.error(request, 'End date cannot be earlier than start date.')
                    return redirect('bookingService:admin_dashboard')
            except (ValueError, TypeError):
                messages.error(request, 'Invalid date format.')
                return redirect('bookingService:admin_dashboard')

            Announcement.objects.create(
                title=title,
                description=description,
                start_date=start_date,
                end_date=end_date,
                image=image,
                is_visible=is_visible
            )
            messages.success(request, 'Announcement / Promotion added successfully!')
        else:
            messages.error(request, 'Please fill in all required fields.')

    return redirect('bookingService:admin_dashboard')

@login_required
@ensure_csrf_cookie
@csrf_protect
def edit_announcement_view(request, announcement_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')
        
    announcement = get_object_or_404(Announcement, id=announcement_id)
    
    if request.method == 'POST':
        announcement.title = request.POST.get('title', '').strip()
        announcement.description = request.POST.get('description', '').strip()
        start_date = request.POST.get('start_date', '').strip()
        end_date = request.POST.get('end_date', '').strip()
        announcement.is_visible = request.POST.get('is_visible') == 'on'
        
        if 'image' in request.FILES:
            announcement.image = request.FILES['image']
            
        if announcement.title and announcement.description and start_date and end_date:
            try:
                s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                if e_date < s_date:
                    messages.error(request, 'End date cannot be earlier than start date.')
                    return render(request, 'admin/edit_announcement.html', {'announcement': announcement})
            except (ValueError, TypeError):
                messages.error(request, 'Invalid date format.')
                return render(request, 'admin/edit_announcement.html', {'announcement': announcement})

            announcement.start_date = start_date
            announcement.end_date = end_date
            announcement.save()
            messages.success(request, 'Announcement updated successfully!')
            return redirect('bookingService:admin_dashboard')
        else:
            messages.error(request, 'Please fill in all required fields.')
            
    return render(request, 'admin/edit_announcement.html', {'announcement': announcement})

@login_required
@csrf_protect
def delete_announcement_view(request, announcement_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    announcement = get_object_or_404(Announcement, id=announcement_id)
    announcement.delete()
    messages.success(request, 'Announcement deleted successfully.')
    return redirect('bookingService:admin_dashboard')

@login_required
def booking_qr_code_view(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.user.role != 'admin' and booking.user != request.user:
        return HttpResponse("Unauthorized", status=403)
        
    upi_url = booking.upi_payment_url
    qr_img = qrcode.make(upi_url)
    
    buf = io.BytesIO()
    qr_img.save(buf)
    buf.seek(0)
    return HttpResponse(buf.getvalue(), content_type='image/png')

@login_required
@csrf_protect
def submit_payment_proof_view(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    if request.user.role != 'admin' and booking.user != request.user:
        messages.error(request, 'Unauthorized action.')
        return redirect('bookingService:user_dashboard')

    if request.method == 'POST':
        transaction_id = request.POST.get('transaction_id', '').strip()
        screenshot = request.FILES.get('payment_screenshot')

        txn_err = validate_transaction_id(transaction_id)
        if txn_err:
            messages.error(request, txn_err)
            return redirect('bookingService:user_dashboard')

        if not screenshot:
            messages.error(request, 'Payment screenshot proof is required.')
            return redirect('bookingService:user_dashboard')

        booking.payment_option = 'PAY_NOW'
        booking.transaction_id = transaction_id
        booking.payment_screenshot = screenshot
        booking.payment_submitted_at = timezone.now()
        booking.payment_status = 'PENDING_VERIFICATION'
        booking.save()

        messages.success(request, f'Payment details for Booking #{booking.id} submitted! Your payment is now under admin verification.')
    
    return redirect('bookingService:user_dashboard')

@login_required
@csrf_protect
def verify_payment_view(request, booking_id):
    if request.user.role != 'admin':
        return redirect('bookingService:user_dashboard')

    booking = get_object_or_404(Booking, id=booking_id)
    if request.method == 'POST':
        action = request.POST.get('action', 'approve')
        status_choice = request.POST.get('payment_status', 'PAID_ONLINE')
        remarks = request.POST.get('admin_remarks', '').strip()

        if action == 'approve':
            booking.payment_status = status_choice
            if remarks:
                booking.admin_remarks = remarks
            booking.save()
            messages.success(request, f'Payment for Booking #{booking.id} verified as {booking.get_payment_status_display()}.')
        elif action == 'reject':
            booking.payment_status = 'UNPAID'
            booking.status = 'CANCELLED'
            if remarks:
                booking.admin_remarks = f"Payment Verification Rejected: {remarks}"
            else:
                booking.admin_remarks = "Payment verification rejected by admin."
            booking.save()
            messages.warning(request, f'Payment proof for Booking #{booking.id} rejected and booking status set to Cancelled.')

    return redirect('bookingService:admin_dashboard')

