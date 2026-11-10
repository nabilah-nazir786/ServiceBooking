from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'bookingService'

urlpatterns = [
    # Startup URLs
    path('', views.home_view, name='home'),
    path('startup/login/', views.login_view, name='login'),
    path('startup/register/', views.register_view, name='register'),
    
    # User URLs
    path('user/dashboard/', views.user_dashboard_view, name='user_dashboard'),
    path('user/update-profile/', views.update_profile_view, name='update_profile'),
    path('user/change-password/', views.change_password_view, name='change_password'),
    path('user/create-booking/', views.create_booking_view, name='create_booking'),
    path('user/submit-feedback/<int:booking_id>/', views.submit_feedback_view, name='submit_feedback'),
    path('user/delete-booking/<int:booking_id>/', views.user_delete_booking_view, name='user_delete_booking'),
    path('user/submit-payment/<int:booking_id>/', views.submit_payment_proof_view, name='submit_payment_proof'),
    path('user/booking-qr/<int:booking_id>/', views.booking_qr_code_view, name='booking_qr_code'),
    
    # Admin URLs
    path('admin/dashboard/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin/add-service/', views.add_service_view, name='add_service'),
    path('admin/edit-service/<int:service_id>/', views.edit_service_view, name='edit_service'),
    path('admin/delete-service/<int:service_id>/', views.delete_service_view, name='delete_service'),
    path('admin/add-gallery-item/', views.add_gallery_item_view, name='add_gallery_item'),
    path('admin/edit-gallery-item/<int:item_id>/', views.edit_gallery_item_view, name='edit_gallery_item'),
    path('admin/delete-gallery-item/<int:item_id>/', views.delete_gallery_item_view, name='delete_gallery_item'),
    path('admin/add-timeslot/', views.add_timeslot_view, name='add_timeslot'),
    path('admin/edit-timeslot/<int:slot_id>/', views.edit_timeslot_view, name='edit_timeslot'),
    path('admin/delete-timeslot/<int:slot_id>/', views.delete_timeslot_view, name='delete_timeslot'),
    path('admin/add-booking/', views.admin_create_booking_view, name='admin_create_booking'),
    path('admin/update-booking-status/<int:booking_id>/', views.update_booking_status_view, name='update_booking_status'),
    path('admin/verify-payment/<int:booking_id>/', views.verify_payment_view, name='verify_payment'),
    path('admin/delete-booking/<int:booking_id>/', views.delete_booking_view, name='delete_booking'),
    path('admin/reject-booking/<int:booking_id>/', views.reject_booking_view, name='reject_booking'),
    path('admin/approve-booking/<int:booking_id>/', views.approve_booking_view, name='approve_booking'),
    path('admin/update-ongoing-work/<int:booking_id>/', views.update_ongoing_work_view, name='update_ongoing_work'),
    path('admin/toggle-feedback-visibility/<int:feedback_id>/', views.toggle_feedback_visibility_view, name='toggle_feedback_visibility'),
    path('admin/add-announcement/', views.add_announcement_view, name='add_announcement'),
    path('admin/edit-announcement/<int:announcement_id>/', views.edit_announcement_view, name='edit_announcement'),
    path('admin/delete-announcement/<int:announcement_id>/', views.delete_announcement_view, name='delete_announcement'),

    # Authentication & Utilities
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_redirect, name='dashboard_redirect'),
    path('api/get-slots-for-date/', views.get_slots_for_date_api, name='get_slots_for_date'),
]
